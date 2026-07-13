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

_DIR = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}


def _walkable_grid(map_key: tuple[int, int]) -> tuple[set, int, int]:
    """Set of floor tiles (collision 0) on the map, plus its size."""
    from modules.map import get_map_data

    w, h = get_map_data(map_key, (0, 0)).map_size
    floor = set()
    for y in range(h):
        for x in range(w):
            try:
                if not get_map_data(map_key, (x, y)).collision:
                    floor.add((x, y))
            except Exception:
                pass
    return floor, w, h


def solve_boulder_puzzle(
    map_key: tuple[int, int],
    start: tuple[int, int],
    boulders: list[tuple[int, int]],
    switches: list[tuple[int, int]],
    fixed: frozenset = frozenset(),
    max_states: int = 400_000,
) -> list[str] | None:
    """BFS for a move sequence (list of 'Up'/'Down'/'Left'/'Right' steps) that
    lands a boulder on every switch tile. `fixed` boulders block movement but
    are never pushed (already-placed on other switches). Returns None if
    unsolved within the state budget.

    ponytail: plain BFS (shortest push-path); the per-switch decomposition in
    run_boulder_puzzle keeps each search small (one target, others fixed)."""
    floor, _w, _h = _walkable_grid(map_key)
    floor = floor | set(boulders) | set(fixed)  # boulder tiles are floor underneath
    switch_set = frozenset(switches)

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
                # push: boulder at nxt slides to beyond
                beyond = (nxt[0] + dx, nxt[1] + dy)
                if beyond not in floor or beyond in bs or beyond in fixed:
                    continue
                nbs = frozenset((beyond if b == nxt else b) for b in bs)
                nstate = (nxt, nbs)
            else:
                nstate = (nxt, bs)
            if nstate not in seen:
                seen.add(nstate)
                queue.append((nstate, [*path, d]))
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
        yield from wait_for_yes_no_question("Yes")  # "use STRENGTH?"
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")
        return
    raise SkillError(f"activate_strength: no adjacent tile at {boulder_xy}")


def _live_boulders(map_key: tuple[int, int]) -> list[tuple[int, int]]:
    from modules.map import get_map_objects

    return sorted(
        tuple(o.current_coords) for o in get_map_objects() if "isPlayer" not in o.flags
    )


def _step(direction: str) -> Generator:
    """One directional step (walk or push); True if the player advanced.
    Waits out the push animation before settling so the next solve reads a
    stable boulder state."""
    from modules.context import context
    from modules.player import get_player_avatar

    before = tuple(get_player_avatar().local_coordinates)
    moved = False
    for _ in range(90):
        context.emulator.press_button(direction)
        yield
        if tuple(get_player_avatar().local_coordinates) != before:
            moved = True
            break
    for _ in range(16):  # let the boulder slide + object coords settle
        yield
    return moved


def run_boulder_puzzle(map_enum, switches, activate_boulder=None) -> Generator:
    """Solve + execute a Strength-boulder puzzle, RE-SOLVING from live state
    whenever a step stalls (self-heals tape/reality divergence — boulder
    physics timing makes a blind replay brittle). Activates Strength first
    (on `activate_boulder`, or the boulder nearest the player if None)."""
    from modules.player import get_player_avatar

    map_key = map_enum.value
    if activate_boulder is None:
        px, py = get_player_avatar().local_coordinates
        activate_boulder = min(_live_boulders(map_key), key=lambda b: abs(b[0] - px) + abs(b[1] - py))
    yield from activate_strength(map_enum, activate_boulder)

    # Solve switches ONE AT A TIME (each a small search); boulders already on
    # done switches are FIXED so a later solve can't knock them off. A blind
    # replay is brittle (boulder-slide timing), so re-solve from live on any
    # stall.
    for switch in switches:
        for _resolve in range(12):
            boulders = _live_boulders(map_key)
            done = frozenset(b for b in boulders if b in set(switches) and b != switch) | {
                b for b in boulders if b == switch
            }
            if switch in boulders:
                break  # this switch already covered
            fixed = frozenset(b for b in boulders if b in set(switches))
            start = tuple(get_player_avatar().local_coordinates)
            movable = [b for b in boulders if b not in fixed]
            moves = solve_boulder_puzzle(map_key, start, movable, [switch], fixed=fixed)
            if moves is None:
                raise SkillError(f"switch {switch} unsolvable from {start} movable={movable} fixed={sorted(fixed)}")
            _log_event(skill="boulder_puzzle", status="executing", switch=switch, moves=len(moves), attempt=_resolve)
            for d in moves:
                moved = yield from _step(d)
                if not moved:
                    break  # diverged — re-read live state and re-solve
                if switch in _live_boulders(map_key):
                    break
            else:
                continue
            if switch in _live_boulders(map_key):
                break
        else:
            raise SkillError(f"run_boulder_puzzle: too many re-solves for switch {switch}")
    _log_event(skill="boulder_puzzle", status="solved", map=str(map_key))
