"""L1 navigate_to: cross-map, cross-warp navigation.

Upstream's `calculate_path`/`navigate_to` already do A* over walkable tiles
(collision, ledges, NPCs) across *connected* maps, and will follow a warp if it
is the final destination. What they cannot do is route *through* warps (doors,
stairs, caves). This module adds that: a BFS over the warp graph picks a
sequence of warps, and each leg is delegated to upstream navigation.
"""

from typing import Generator

from dexbot.runner import SkillError

# ponytail: BFS minimizes warp count, not walking distance; weight edges by
# leg length if routes ever look dumb.


def _map_level(map_group_and_number: tuple[int, int]) -> int:
    from modules.map_path import _get_all_maps_metadata

    return _get_all_maps_metadata()[tuple(map_group_and_number)].level


# Tile behaviours that actually trigger a warp when stepped on/into (FRLG names).
# Warp *events* on tiles without one of these (e.g. behaviour "Normal") are ignored
# by the game engine, so they must not become graph edges.
WARP_BEHAVIOURS = frozenset(
    {
        "Cave Door",
        "Ladder",
        "East Arrow Warp",
        "West Arrow Warp",
        "North Arrow Warp",
        "South Arrow Warp",
        "Fall Warp",
        "Regular Warp",
        "Door Warp",
        "Escalator Up",
        "Escalator Down",
        "Stair Warp Up/Right",
        "Stair Warp Up/Left",
        "Stair Warp Down/Right",
        "Stair Warp Down/Left",
        "Union Room Warp",
    }
)

_warp_edges: dict[int, list[tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]]] | None = None


def _get_warp_edges() -> dict:
    """level -> [(warp_map, warp_coords, dest_map, dest_coords)], built once from ROM map data."""
    global _warp_edges
    if _warp_edges is None:
        from modules.map import get_map_data
        from modules.map_path import _get_all_maps_metadata

        _warp_edges = {}
        for map_key, path_map in _get_all_maps_metadata().items():
            try:
                warps = get_map_data(map_key, (0, 0)).warps
            except Exception:
                continue
            for warp in warps:
                if get_map_data(map_key, warp.local_coordinates).tile_type not in WARP_BEHAVIOURS:
                    continue
                dest = warp.destination_location
                dest_key = (dest.map_group, dest.map_number)
                if dest_key == (127, 127) or dest_key not in _get_all_maps_metadata():
                    continue  # dynamic warps (elevators etc.) handled by story scripts, not navigation
                _warp_edges.setdefault(path_map.level, []).append(
                    (map_key, warp.local_coordinates, dest_key, dest.local_position)
                )
    return _warp_edges


_walkable_cache: set = set()  # proven-walkable pairs only — see below


def _walkable(source: tuple[tuple[int, int], tuple[int, int]], dest: tuple[tuple[int, int], tuple[int, int]]) -> bool:
    """Whether the A* finds a walking path between two positions (no player needed).

    Map "levels" are not internally connected (Kanto's outdoors is split by the
    forest, caves, ...), so warp-route planning verifies every same-level leg
    with the real pathfinder instead of trusting level identity.

    Only SUCCESSES are cached. `calculate_path` blocks the live NPCs' tiles, so
    a wandering NPC in a choke point makes every check from the walled-off side
    fail *transiently*; caching such a False poisons all future plans in the
    process ("No warp route" forever, even after the NPC moves on). Walkability
    that exists is static — failures must be recomputed each time.
    """
    from modules.map_path import calculate_path

    key = (source, dest)
    if key in _walkable_cache:
        return True
    try:
        calculate_path(source, dest)
        _walkable_cache.add(key)
        return True
    except Exception:
        return False


_WALKABLE_BUDGET = 2000  # max A* checks per plan; bounds worst-case planning time


def _global_coords(map_key: tuple[int, int], local: tuple[int, int]) -> tuple[int, int] | None:
    """Approximate global coordinates for cross-map distance heuristics."""
    from modules.map_path import _get_all_maps_metadata

    pm = _get_all_maps_metadata().get(tuple(map_key))
    if pm is None or pm.offset is None:
        return None
    return (local[0] + pm.offset[0], local[1] + pm.offset[1])


_nav_graphs: dict[int, dict | None] = {}  # epoch -> {tile: component_id} | None
_rebuild_attempted: set[int] = set()


def _load_nav_graph() -> dict | None:
    """The current story epoch's component map from data/nav_graph.json.

    Connectivity depends on story gates, so components are keyed by an epoch
    (= badge count). A missing epoch section is built in-process — pure
    calculate_path computation, ~10s, no frames advanced. None means graph
    planning is unavailable (build failed); callers fall back to live search.
    """
    from modules.memory import get_event_flag

    epoch = sum(1 for n in range(1, 9) if get_event_flag(f"BADGE{n:02d}_GET"))
    if epoch in _nav_graphs:
        return _nav_graphs[epoch]

    import json

    from dexbot import PROJECT_ROOT

    path = PROJECT_ROOT / "data" / "nav_graph.json"

    def read_section() -> dict | None:
        try:
            raw = json.loads(path.read_text())["epochs"][str(epoch)]
        except Exception:
            return None
        graph = {}
        for key, cid in raw.items():
            mg, mn, x, y = (int(v) for v in key.split(","))
            graph[((mg, mn), (x, y))] = cid
        return graph

    graph = read_section()
    if graph is None and epoch not in _rebuild_attempted:
        _rebuild_attempted.add(epoch)
        try:
            from dexbot.build_navgraph import build

            build(None)
            graph = read_section()
        except Exception:
            graph = None
    _nav_graphs[epoch] = graph
    return graph


def _find_component(position, graph, walkable, reverse: bool = False) -> int | None:
    """Which walk-component `position` belongs to, via live A* against one
    representative portal tile per component on its level (nearest first)."""
    level = _map_level(position[0])
    pos_global = _global_coords(position[0], position[1])

    def distance(tile) -> int:
        g = _global_coords(tile[0], tile[1])
        if g is None or pos_global is None:
            return 0
        return abs(g[0] - pos_global[0]) + abs(g[1] - pos_global[1])

    nearest_rep: dict[int, tuple] = {}
    for tile, cid in graph.items():
        if _map_level(tile[0]) != level:
            continue
        if cid not in nearest_rep or distance(tile) < distance(nearest_rep[cid]):
            nearest_rep[cid] = tile
    for cid, tile in sorted(nearest_rep.items(), key=lambda kv: distance(kv[1])):
        if walkable(tile, position) if reverse else walkable(position, tile):
            return cid
    return None


def _plan_via_graph(start, dest, blacklist, walkable) -> list | None:
    """Instant BFS over precomputed walk-components joined by warp edges.

    Returns the warp-tile route, or None to fall back to live planning (graph
    missing, stale story epoch, or start/dest not matched to a component).
    """
    from collections import deque

    graph = _load_nav_graph()
    if graph is None:
        return None
    start_cid = _find_component(start, graph, walkable)
    dest_cid = _find_component(dest, graph, walkable, reverse=True)
    if start_cid is None or dest_cid is None:
        return None
    if start_cid == dest_cid:
        return []
    # Component adjacency: each warp joins its source tile's component to its
    # landing tile's component, traversed by stepping on the source tile.
    adjacency: dict[int, list] = {}
    for elist in _get_warp_edges().values():
        for src_map, src_coords, dst_map, dst_coords in elist:
            src_tile = (src_map, src_coords)
            if src_tile in blacklist:
                continue
            a = graph.get(src_tile)
            b = graph.get((dst_map, dst_coords))
            if a is not None and b is not None and a != b:
                adjacency.setdefault(a, []).append((b, src_tile))
    queue = deque([(start_cid, [])])
    seen = {start_cid}
    while queue:
        cid, route = queue.popleft()
        for next_cid, src_tile in adjacency.get(cid, []):
            if next_cid in seen:
                continue
            if next_cid == dest_cid:
                return [*route, src_tile]
            seen.add(next_cid)
            queue.append((next_cid, [*route, src_tile]))
    return None  # no graph route (e.g. blacklisted bridge) — let live search try


def _plan_warp_route(
    start: tuple[tuple[int, int], tuple[int, int]],
    dest: tuple[tuple[int, int], tuple[int, int]],
    blacklist: frozenset = frozenset(),
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Plan the warp-tile route from `start` to `dest`.

    Fast path: BFS over the precomputed connectivity graph (a handful of live
    A* to place start/dest in components). Fallback: the live best-first
    search below, kept for a missing/stale graph.
    """
    route = _plan_via_graph(start, dest, frozenset(blacklist), _walkable)
    if route is not None:
        return route
    return _plan_warp_route_live(start, dest, blacklist)


def _plan_warp_route_live(
    start: tuple[tuple[int, int], tuple[int, int]],
    dest: tuple[tuple[int, int], tuple[int, int]],
    blacklist: frozenset = frozenset(),
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Best-first search over reachable warp endpoints; returns the warp tiles.

    Each candidate leg is A*-verified with `_walkable`, because map "levels" are
    NOT reliably walkable-contiguous: whole regions share a level yet are only
    linked through warps (Cerulean↔Vermilion via the Underground Path, Saffron
    gated between). A pure graph would emit a direct walk the executor can't
    follow. To stay fast we explore warps *best-first* by global-coordinate
    distance to the destination (heads toward the goal instead of opening every
    building door), backed by the `_walkable` cache and a per-plan A* budget.
    """
    import heapq

    edges = _get_warp_edges()
    checks = [0]

    def walkable(a, b) -> bool:
        checks[0] += 1
        if checks[0] > _WALKABLE_BUDGET:
            raise SkillError(f"Route planning budget exceeded from {start} to {dest}")
        return _walkable(a, b)

    dest_level = _map_level(dest[0])
    dest_map = tuple(dest[0])
    dest_global = _global_coords(dest[0], dest[1])
    if _map_level(start[0]) == dest_level and walkable(start, dest):
        return []

    # Fast path — direct entry into the destination MAP (e.g. a building door on
    # the current overworld level). Building interiors have no global offset, so
    # the distance heuristic can't rank their doors and the search would fan into
    # every building; check same-level warps that land in the target map first.
    for warp_map, warp_coords, warp_dest_map, warp_dest_coords in edges.get(_map_level(start[0]), []):
        if tuple(warp_dest_map) == dest_map and (warp_map, warp_coords) not in blacklist:
            if walkable(start, (warp_map, warp_coords)):
                return [(warp_map, warp_coords)]

    def priority(landing) -> int:
        g = _global_coords(landing[0], landing[1])
        if g is None or dest_global is None:
            return 0
        return abs(g[0] - dest_global[0]) + abs(g[1] - dest_global[1])

    visited: set = set()
    counter = 0
    # Priority: (warp-count so far, distance heuristic, tiebreak). Minimising the
    # number of warps first makes this a verified-walkable Dijkstra — it returns
    # the *shortest* real route (e.g. Cerulean→Vermilion via the 2-warp
    # Underground Path) instead of a convoluted building-weave the pure distance
    # heuristic would wander into (interiors have no global coords).
    heap: list = [(0, 0, 0, start, [])]  # (num_warps, heuristic, tiebreak, position, route)
    while heap:
        _, _, _, position, route = heapq.heappop(heap)
        for warp_map, warp_coords, warp_dest_map, warp_dest_coords in edges.get(_map_level(position[0]), []):
            key = (warp_map, warp_coords)
            if key in visited or key in blacklist:
                continue
            if not walkable(position, (warp_map, warp_coords)):
                continue
            visited.add(key)
            landing = (warp_dest_map, warp_dest_coords)
            if _map_level(warp_dest_map) == dest_level and walkable(landing, dest):
                return [*route, key]
            counter += 1
            heapq.heappush(heap, (len(route) + 1, priority(landing), counter, landing, [*route, key]))
    raise SkillError(f"No warp route from {start} to {dest}")


def navigate_to(map, coordinates: tuple[int, int], run: bool = True) -> Generator:
    """Walk the player to `coordinates` on `map`, routing through warps if needed.

    A generator skill: drive it with dexbot.runner.run_skill.
    """
    from modules.map_data import MapFRLG
    from modules.modes._interface import BotModeError
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar
    from modules.tasks import get_global_script_context

    if isinstance(map, MapFRLG):
        map = map.value

    interruptions = 0
    blacklist: set = set()
    current_target = None
    target_failures = 0
    cached_route: list | None = None  # plan once; re-plan only after a failure
    while True:
        avatar = get_player_avatar()
        position = (avatar.map_group_and_number, avatar.local_coordinates)
        try:
            # Planning is expensive across Kanto, so amortize it over the whole
            # journey: plan once, then consume warp legs in sequence. A failure
            # clears the cache to force a fresh plan (with any new blacklist).
            if cached_route is None:
                cached_route = _plan_warp_route(position, (tuple(map), tuple(coordinates)), frozenset(blacklist))
            if not cached_route:
                yield from navigate_same_level(map, coordinates, run=run)
                return
            # Step onto the next warp; upstream follows it (final waypoint).
            warp_map, warp_coords = cached_route[0]
            current_target = (warp_map, warp_coords)
            yield from navigate_same_level(warp_map, warp_coords, run=run)
            cached_route = cached_route[1:] or None  # consume; None re-plans final walk
            target_failures = 0
        except BotModeError as e:
            # One-time overworld triggers (tutorial NPCs, etc.) interrupt walking.
            # Mash through the script, then re-plan from wherever we ended up.
            cached_route = None  # invalidate: re-plan from the new position
            interruptions += 1
            if interruptions > 30:
                raise
            if "Could not find a path" in str(e):
                # Either a wandering NPC (current + previous tile both count as
                # blocked) sitting in a choke point — wait it out — or the warp
                # is genuinely unreachable from this part of the level (levels
                # are not always internally connected): blacklist and re-plan.
                target_failures += 1
                if target_failures >= 3 and current_target is not None:
                    blacklist.add(current_target)
                    target_failures = 0
                    continue
                for _ in range(120):
                    yield
                continue
            if not (get_global_script_context() and get_global_script_context().is_active):
                # Not a script interruption — e.g. "player not controllable" right
                # after a menu/dialogue closed. Give it a moment and retry once.
                from modules.player import player_avatar_is_controllable

                for _ in range(120):
                    if player_avatar_is_controllable():
                        break
                    yield
                else:
                    raise
                continue
            from modules.context import context
            from modules.tasks import task_is_active

            # Upstream's error path can leave movement buttons held, and resuming
            # while an NPC's scripted walk is still in flight can re-trigger the
            # event and deadlock the game script. Clear both before re-planning.
            context.emulator.reset_held_buttons()
            frame = 0
            while get_global_script_context() and get_global_script_context().is_active:
                frame += 1
                if frame % 48 == 24:
                    # Some FRLG tutorial boxes (sign lady's "press START to open
                    # the MENU") only dismiss on Start — A/B are swallowed.
                    context.emulator.press_button("Start")
                elif frame % 8 == 0:
                    context.emulator.press_button("A")
                yield
            for frame in range(40):  # close a menu if a Start press opened one
                if frame % 10 == 0:
                    context.emulator.press_button("B")
                yield
            while task_is_active("ScriptMovement_MoveObjects"):
                yield
            yield from wait_for_player_avatar_to_be_controllable("A")
