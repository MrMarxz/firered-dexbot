"""Ground item collection: the visible Poké Ball items on maps are free
loot (balls, potions, TMs, Nuggets) the bot walked past for four badges.

Each item ball is a map object whose script symbol contains "EventScript_Item"
and whose flag is SET once collected — so remaining loot is enumerable and
idempotent to sweep.
"""

from typing import Generator

from dexbot.navigation import navigate_to
from dexbot.runner import SkillError


def uncollected_item_balls(map_key) -> list[tuple[int, tuple[int, int]]]:
    """(local_id, coords) of item balls on `map_key` not yet collected."""
    from modules.map import get_map_data
    from modules.memory import get_event_flag_by_number

    result = []
    try:
        objects = get_map_data(tuple(map_key), (0, 0)).objects
    except Exception:
        return result
    for obj in objects:
        script = str(getattr(obj, "script_symbol", ""))
        if "EventScript_Item" not in script:
            continue
        flag = getattr(obj, "flag_id", None)
        if flag and get_event_flag_by_number(flag):
            continue  # already collected
        result.append((obj.local_id, tuple(obj.local_coordinates)))
    return result


def collect_item_balls(map_key, limit: int = 10, only: list | None = None) -> Generator:
    """Pick up reachable item balls on `map_key`: stand adjacent, face, A.
    Unreachable ones (behind puzzles) are skipped, not fatal. `only` limits
    collection to balls at those coords (e.g. just the Secret Key)."""
    from modules.context import context
    from modules.map_data import MapFRLG
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable
    from modules.player import get_player_avatar

    from dexbot.navigation import _plan_via_graph, _walkable

    if isinstance(map_key, MapFRLG):
        map_key = map_key.value
    collected = 0
    for local_id, coords in uncollected_item_balls(map_key):
        if collected >= limit:
            return
        if only is not None and coords not in only:
            continue
        # Try the four adjacent stand tiles, nearest-plan first.
        for (dx, dy), facing in (((0, 1), "Up"), ((0, -1), "Down"), ((1, 0), "Left"), ((-1, 0), "Right")):
            stand = (coords[0] + dx, coords[1] + dy)
            if stand[0] < 0 or stand[1] < 0:
                continue
            # Cheap same-map reachability probe before the full planner: an
            # unreachable stand (switch door closed) otherwise burns minutes
            # of graph scans + live fallback A* — the B1F key-phase wedge.
            av = get_player_avatar()
            if tuple(av.map_group_and_number) == tuple(map_key) and not _walkable(
                (tuple(map_key), tuple(av.local_coordinates)), (tuple(map_key), stand), max_nodes=3_000
            ):
                continue
            try:
                yield from navigate_to(map_key, stand)
            except SkillError:
                continue
            yield from ensure_facing_direction(facing)
            context.emulator.press_button("A")
            yield
            yield from wait_for_no_script_to_run("B")
            yield from wait_for_player_avatar_to_be_controllable("B")
            collected += 1
            break
