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


from functools import lru_cache


@lru_cache(maxsize=4096)
def _walkable(source: tuple[tuple[int, int], tuple[int, int]], dest: tuple[tuple[int, int], tuple[int, int]]) -> bool:
    """Whether the A* finds a walking path between two positions (no player needed).

    Map "levels" are not internally connected (Kanto's outdoors is split by the
    forest, caves, ...), so warp-route planning verifies every same-level leg
    with the real pathfinder instead of trusting level identity.

    Cached: route planning re-tests the same (position, warp) pairs constantly.
    A stale hit (an NPC moved into a choke point, a story flag cleared a tile)
    is corrected by the navigation retry/blacklist machinery at execution time.
    """
    from modules.map_path import PathFindingError, calculate_path

    try:
        calculate_path(source, dest)
        return True
    except PathFindingError:
        return False
    except Exception:
        return False


def _plan_warp_route(
    start: tuple[tuple[int, int], tuple[int, int]],
    dest: tuple[tuple[int, int], tuple[int, int]],
    blacklist: frozenset = frozenset(),
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """BFS over the warp graph at *map-level* granularity; returns the warp tiles
    to step on, in order.

    Planning is pure graph traversal — no per-edge A* walkability check, which is
    far too slow across Kanto (a full `calculate_path` per warp × ~1000 warps).
    We assume a warp on the current level is reachable; `navigate_to`'s execution
    loop walks each leg with the real A* and blacklists any leg that turns out
    unwalkable (e.g. the Route 2 forest split), then re-plans. `blacklist`
    contains those failed (warp_map, warp_coords) edges.
    """
    edges = _get_warp_edges()
    start_level = _map_level(start[0])
    dest_level = _map_level(dest[0])
    if start_level == dest_level:
        return []
    visited: set = {start_level}
    queue: list = [(start_level, [])]
    while queue:
        level, route = queue.pop(0)
        for warp_map, warp_coords, warp_dest_map, warp_dest_coords in edges.get(level, []):
            key = (warp_map, warp_coords)
            if key in blacklist:
                continue
            dest_lvl = _map_level(warp_dest_map)
            new_route = [*route, key]
            if dest_lvl == dest_level:
                return new_route
            if dest_lvl not in visited:
                visited.add(dest_lvl)
                queue.append((dest_lvl, new_route))
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
    while True:
        avatar = get_player_avatar()
        position = (avatar.map_group_and_number, avatar.local_coordinates)
        try:
            route = _plan_warp_route(position, (tuple(map), tuple(coordinates)), frozenset(blacklist))
            if not route:
                yield from navigate_same_level(map, coordinates, run=run)
                return
            # Step onto the first warp of the route; upstream follows the warp
            # because it is the final waypoint. Then re-plan from the new position.
            warp_map, warp_coords = route[0]
            current_target = (warp_map, warp_coords)
            yield from navigate_same_level(warp_map, warp_coords, run=run)
            target_failures = 0
        except BotModeError as e:
            # One-time overworld triggers (tutorial NPCs, etc.) interrupt walking.
            # Mash through the script, then re-plan from wherever we ended up.
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
