"""Strength-boulder puzzle solver + executor (Victory Road, Seafoam, Mt Ember).

The pathfinder can't push boulders, and boulder-on-switch puzzles gate
mandatory progress. This solves them as sokoban: a logic-only BFS over
(player, boulders) states using the game's push rule (walk into a boulder
with Strength active → it slides one tile if the far side is clear), then
replays the winning move list as directional steps.

Mechanic (verified headless on VR 1F): activate Strength once per map by
facing any boulder + A + "use STRENGTH?" Yes; thereafter stepping into a
boulder pushes it and the player follows onto the boulder's old tile.
"""

from collections import deque
from typing import Generator

from dexbot.runner import SkillError, _log_event

# dx,dy plus the map_path Direction index (North=0,East=1,South=2,West=3) used
# to enter a tile moving that way — for one-way ledge checks.
_DIR = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}
_DIR_IDX = {"Up": 0, "Right": 1, "Down": 2, "Left": 3}


def _access_grid(map_key: tuple[int, int]) -> dict:
    """{tile: (accessible_from[N,E,S,W])} from the pathfinder's own per-tile,
    per-direction accessibility — captures ONE-WAY LEDGES (a tile enterable
    only from above) and elevation that the raw collision byte misses. Warp/
    hole tiles are excluded: cave floors have fall-throughs that read as floor
    but drop you a level; the intended stairs are warps too and the caller
    navigates to those separately after the switches are pressed."""
    from modules.map import get_map_data
    from modules.map_path import _get_all_maps_metadata

    holes = {tuple(wp.local_coordinates) for wp in get_map_data(map_key, (0, 0)).warps}
    pm = _get_all_maps_metadata()[map_key]
    return {
        tuple(t.local_coordinates): tuple(t.accessible_from_direction)
        for t in pm.tiles
        if any(t.accessible_from_direction) and tuple(t.local_coordinates) not in holes
    }


def solve_boulder_puzzle(
    map_key: tuple[int, int],
    start: tuple[int, int],
    boulders: list[tuple[int, int]],
    switches: list[tuple[int, int]],
    fixed: frozenset = frozenset(),
    blocked: frozenset = frozenset(),
    max_states: int = 400_000,
) -> list[str] | None:
    """BFS for a move sequence (list of 'Up'/'Down'/'Left'/'Right' steps) that
    lands a boulder on every switch tile. `fixed` boulders block movement but
    are never pushed (already-placed on other switches). Returns None if
    unsolved within the state budget.

    ponytail: plain BFS (shortest push-path); the per-switch decomposition in
    run_boulder_puzzle keeps each search small (one target, others fixed)."""
    access = _access_grid(map_key)
    floor = (set(access) | set(boulders) | set(fixed)) - set(blocked)
    switch_set = frozenset(switches)

    def can_enter(tile, d) -> bool:
        # Directional: entering `tile` moving `d` needs the game to allow that
        # side (one-way ledges). Boulder/fixed tiles have no access entry, so
        # treat them as omni-enterable floor (the boulder is what's there).
        acc = access.get(tile)
        return acc is None or acc[_DIR_IDX[d]]

    def won(bs: frozenset) -> bool:
        return switch_set <= bs

    start_state = (start, frozenset(boulders))
    seen = {start_state}
    queue: deque = deque([(start_state, [])])
    states = 0
    while queue:
        (ppos, bs), path = queue.popleft()
        if won(bs):
            return path
        states += 1
        if states > max_states:
            return None
        for d, (dx, dy) in _DIR.items():
            nxt = (ppos[0] + dx, ppos[1] + dy)
            if nxt not in floor or nxt in fixed:
                continue
            if nxt in bs:
                # push: boulder at nxt slides to beyond (must be plain floor
                # enterable from this push direction, no boulder/fixed there)
                beyond = (nxt[0] + dx, nxt[1] + dy)
                if beyond not in floor or beyond in bs or beyond in fixed or not can_enter(beyond, d):
                    continue
                nbs = frozenset((beyond if b == nxt else b) for b in bs)
                nstate = (nxt, nbs)
            else:
                if not can_enter(nxt, d):
                    continue
                nstate = (nxt, bs)
            if nstate not in seen:
                seen.add(nstate)
                queue.append((nstate, [*path, d]))
    return None


def _oracle_step(emu, direction: str) -> tuple[bool, tuple[int, int]]:
    """Synchronously press `direction` (up to a step+push animation), advancing
    the emulator directly. Returns (moved, new_player_tile). Ground truth — the
    real game decides walkability and whether a boulder shoved."""
    from modules.player import get_player_avatar

    before = tuple(get_player_avatar().local_coordinates)
    moved = False
    for _ in range(90):
        emu.press_button(direction)
        emu.run_single_frame()
        if tuple(get_player_avatar().local_coordinates) != before:
            moved = True
            break
    for _ in range(18):  # let a boulder slide finish before we read/branch
        emu.run_single_frame()
    return moved, tuple(get_player_avatar().local_coordinates)


def solve_boulder_puzzle_oracle(context, map_key, switches, max_states: int = 6000) -> list[str] | None:
    """Find a directional tape that lands a boulder on every switch, using the
    EMULATOR ITSELF as the physics oracle (savestate BFS) — no Python model of
    walkability/pushes, so it cannot diverge from the game. Boulder positions
    are inferred from real pushes (player entering a tracked boulder tile).
    The emulator must be parked at the puzzle with Strength already active.
    Returns the tape (or None if unsolved within the state budget).

    Directions are ordered by the cheap Python model's own solution first, so
    the oracle usually walks straight to the answer instead of flooding."""
    from collections import deque

    from modules.memory import GameState, get_game_state
    from modules.player import get_player_avatar

    emu = context.emulator
    switch_set = set(switches)
    root = emu.get_save_state()
    start = tuple(get_player_avatar().local_coordinates)
    boulders0 = frozenset(_initial_boulders(map_key))
    if switch_set <= boulders0:
        return []

    # Model hint: a candidate move-list (may be wrong on ledges, but orders
    # exploration toward the goal) — try its first move first at each ply.
    hint = solve_boulder_puzzle(map_key, start, list(boulders0), switches) or []

    seen = {(start, boulders0)}
    queue: deque = deque([(root, start, boulders0, [], 0)])
    states = 0
    while queue and states < max_states:
        state_bytes, ppos, bs, tape, depth = queue.popleft()
        states += 1
        dirs = list(_DIR)
        if depth < len(hint):  # bias toward the model's plan
            h = hint[depth]
            dirs = [h] + [d for d in dirs if d != h]
        for d in dirs:
            emu.load_save_state(state_bytes)
            emu.run_single_frame()
            dx, dy = _DIR[d]
            target = (ppos[0] + dx, ppos[1] + dy)
            moved, npos = _oracle_step(emu, d)
            if not moved or get_game_state() != GameState.OVERWORLD:
                continue  # blocked, or a trainer/script fired — dead branch
            nbs = bs
            if target in bs:  # pushed the boulder at `target` one tile further
                nbs = frozenset((target[0] + dx, target[1] + dy) if b == target else b for b in bs)
            key = (npos, nbs)
            if key in seen:
                continue
            seen.add(key)
            ntape = [*tape, d]
            if switch_set <= nbs:
                _log_event(skill="boulder_oracle", status="solved", states=states, moves=len(ntape))
                return ntape
            queue.append((emu.get_save_state(), npos, nbs, ntape, depth + 1))
    _log_event(skill="boulder_oracle", status="unsolved", states=states)
    return None


def activate_strength(map_enum, boulder_xy: tuple[int, int]) -> Generator:
    """Face the boulder at `boulder_xy` and use Strength (once per map)."""
    from modules.context import context
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable
    from modules.player import get_player_avatar

    from dexbot.navigation import navigate_to

    # Stand on an adjacent floor tile and face the boulder.
    px, py = boulder_xy
    for (dx, dy), facing in (((0, 1), "Up"), ((0, -1), "Down"), ((1, 0), "Left"), ((-1, 0), "Right")):
        stand = (px + dx, py + dy)
        if stand[0] < 0 or stand[1] < 0:
            continue
        try:
            yield from navigate_to(map_enum, stand)
        except SkillError:
            continue
        yield from ensure_facing_direction(facing)
        context.emulator.press_button("A")
        yield
        # "use STRENGTH?" appears ONLY if Strength isn't active yet. If it's
        # already active (another boulder pushed earlier this map-visit),
        # pressing A does nothing — don't block on a prompt that won't come.
        from modules.tasks import get_global_script_context

        for _ in range(90):
            script = get_global_script_context()
            if script and script.is_active:
                yield from wait_for_yes_no_question("Yes")
                yield from wait_for_no_script_to_run("B")
                break
            yield
        yield from wait_for_player_avatar_to_be_controllable("B")
        return
    raise SkillError(f"activate_strength: no adjacent tile at {boulder_xy}")


def _initial_boulders(map_key: tuple[int, int]) -> list[tuple[int, int]]:
    """All Strength-boulder start positions from the map's object templates.
    Unlike get_map_objects (which only returns objects loaded near the
    player — far boulders silently drop off), this sees every boulder."""
    from modules.map import get_map_data

    return sorted(
        tuple(o.local_coordinates)
        for o in get_map_data(map_key, (0, 0)).objects
        if "StrengthBoulder" in str(getattr(o, "script_symbol", ""))
    )


def _nearby_boulders(map_key: tuple[int, int]) -> set:
    """Currently-loaded boulder positions (near the player) — used only to
    confirm a push landed, never as the authoritative full set."""
    from modules.map import get_map_objects

    return {tuple(o.current_coords) for o in get_map_objects() if "isPlayer" not in o.flags}


def _pushes_from_moves(start, boulders, moves) -> list:
    """Replay a solved move list on the model, extracting the PUSHES:
    [(boulder_tile_before, direction), ...]. Walking between pushes is left
    to the game's real pathfinder (navigate_to), so the fragile part — my
    approximate walk model — never drives the emulator."""
    pos = start
    bs = set(boulders)
    pushes = []
    for d in moves:
        dx, dy = _DIR[d]
        nxt = (pos[0] + dx, pos[1] + dy)
        if nxt in bs:
            bs.discard(nxt)
            bs.add((nxt[0] + dx, nxt[1] + dy))
            pushes.append((nxt, d))
        pos = nxt
    return pushes


def _do_push(map_enum, boulder: tuple[int, int], direction: str) -> Generator:
    """Walk to the tile behind `boulder` (game pathfinder), face the push
    direction, take one step to shove it. Returns the boulder's new tile."""
    from modules.context import context
    from modules.modes.util.walking import ensure_facing_direction
    from modules.modes.util.walking import navigate_to as navigate_same_level
    from modules.player import get_player_avatar

    dx, dy = _DIR[direction]
    behind = (boulder[0] - dx, boulder[1] - dy)  # stand opposite the push direction
    # Single-map walk (NOT the warp-route navigate_to): repositioning around the
    # boulder is same-map, and the boulder (in blocked_coordinates when loaded)
    # can split the region into components — the warp planner then searches
    # fruitlessly for a 1-tile move and dies "Route planning budget exceeded"
    # (churned the live E4 run). navigate_same_level routes around the boulder
    # via calculate_path and fails cleanly instead of escalating.
    yield from navigate_same_level(map_enum.value, behind)
    yield from ensure_facing_direction(direction)
    before = tuple(get_player_avatar().local_coordinates)
    for _ in range(90):
        context.emulator.press_button(direction)
        yield
        if tuple(get_player_avatar().local_coordinates) != before:
            break
    for _ in range(16):  # boulder slide + object-coord settle
        yield


def push_boulder_sequence(map_enum, boulder_start, moves, activate=True) -> Generator:
    """Execute an EXACT hand-authored push sequence (from the canonical
    walkthrough) instead of searching. `moves` = [(direction, count), ...];
    each unit shoves the tracked boulder one tile. Straight runs need no
    repositioning (the player follows onto the boulder's old tile); at a
    direction change _do_push walks the player behind the boulder for the new
    direction. Returns the boulder's final tile.

    This sidesteps the logic solver entirely — used for Victory Road, where the
    pushes are known and the solver mis-models ledges/holes/spawn state."""
    if activate:
        yield from activate_strength(map_enum, boulder_start)
    pos = tuple(boulder_start)
    for direction, count in moves:
        dx, dy = _DIR[direction]
        for _ in range(count):
            yield from _do_push(map_enum, pos, direction)
            pos = (pos[0] + dx, pos[1] + dy)
    _log_event(skill="push_sequence", status="done", map=str(map_enum.value), final=list(pos))
    return pos


def run_boulder_puzzle(map_enum, switches, activate_boulder=None, activate=True) -> Generator:
    """Solve + execute a Strength-boulder puzzle. Plan WHICH pushes with the
    sokoban solver; execute each by walking to the push tile via the game's
    OWN pathfinder (handles ledges/elevation the solver model can't) and
    shoving once. Re-solve from live state after each switch and on any
    divergence. Activates Strength first (nearest boulder if unspecified)."""
    from modules.player import get_player_avatar

    map_key = map_enum.value
    # Authoritative boulder set (get_map_objects is range-limited); update it
    # ourselves as we push. A push near the player is confirmed against the
    # loaded objects; far boulders we trust our own tracking for.
    positions = set(_initial_boulders(map_key))
    if activate:
        if activate_boulder is None:
            px, py = get_player_avatar().local_coordinates
            activate_boulder = min(positions, key=lambda b: abs(b[0] - px) + abs(b[1] - py))
        yield from activate_strength(map_enum, activate_boulder)

    switch_set = set(switches)
    for switch in switches:
        for _resolve in range(20):
            if switch in positions:
                break
            start = tuple(get_player_avatar().local_coordinates)
            # Route exactly ONE boulder to this switch with every OTHER boulder
            # held FIXED — each switch in these puzzles has a dedicated boulder,
            # and freezing the rest stops switch 1 from scattering switch 2's
            # boulders (and shrinks each search to a single movable boulder).
            candidates = sorted(
                (b for b in positions if b not in switch_set),
                key=lambda b: abs(b[0] - switch[0]) + abs(b[1] - switch[1]),
            )
            moves = one = None
            for cand in candidates:
                fixed = frozenset(b for b in positions if b != cand)
                moves = solve_boulder_puzzle(map_key, start, [cand], [switch], fixed=fixed)
                if moves is not None:
                    one = cand
                    break
            if moves is None:
                raise SkillError(f"switch {switch} unsolvable from {start} (tried {len(candidates)} boulders)")
            movable = [one]
            pushes = _pushes_from_moves(start, movable, moves)
            _log_event(skill="boulder_puzzle", status="executing", switch=switch, pushes=len(pushes), attempt=_resolve)
            diverged = False
            for boulder, d in pushes:
                dx, dy = _DIR[d]
                dest = (boulder[0] + dx, boulder[1] + dy)
                yield from _do_push(map_enum, boulder, d)
                # If the boulder is loaded, confirm it actually reached dest;
                # otherwise trust the plan (far boulder, out of object range).
                near = _nearby_boulders(map_key)
                if boulder in near and dest not in near:
                    diverged = True
                    break
                positions.discard(boulder)
                positions.add(dest)
                if switch in positions:
                    break
            if switch in positions and not diverged:
                break
        else:
            raise SkillError(f"run_boulder_puzzle: too many re-solves for switch {switch}")
    _log_event(skill="boulder_puzzle", status="solved", map=str(map_key))
