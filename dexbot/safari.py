"""M8: Safari Zone catching — entry fee, 30 balls, 600-step budget, PA warp-out.

Reuses upstream's complete FRLG safari machinery: per-species hunting spots
(`SafariPokemon`), internal navigation paths, the documented bait/rock catch
policies (frlg_safari_catch_strategies YAMLs, consulted via CatchStrategy's
`decide_turn_in_safari_zone` — which our WeakeningCatchStrategy inherits, so
`make_catch_decider` works unchanged in safari battles; fleeing non-targets
is free). This module owns what upstream's interactive SafariMode can't give
us: unattended entry/re-entry/exit and the planner-facing skill shape.

Run acceptance: .venv/bin/python -m dexbot.safari <species> [fixture]
"""

from typing import Generator

from dexbot.runner import SkillError, _log_event

# One Safari entry costs 500 and gives 30 balls / 600 steps. A 4%-slot target
# yields 1-2 encounters per entry on average; the cap bounds a bad RNG streak
# without draining the wallet — the planner's defer/retry loop owns the rest.
_MAX_ENTRIES = 8


def _inside_safari() -> bool:
    from modules.map_data import is_safari_map

    return is_safari_map()


def safari_run(species_name: str) -> Generator:
    """Catch `species_name` in the Safari Zone: pay, walk to its documented
    hunting spot, spin (or fish) until caught — re-entering when the PA calls
    time or the balls run out. Drive with on_battle_started=make_catch_decider.
    """
    from modules.context import context
    from modules.items import get_item_by_name
    from modules.map_data import MapFRLG
    from modules.memory import GameState, get_game_state
    from modules.menuing import StartMenuNavigator
    from modules.modes.util.higher_level_actions import spin
    from modules.modes.util.tasks_scripts import wait_for_script_to_start_and_finish
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
        wait_for_player_avatar_to_be_standing_still,
    )
    from modules.player import get_player, get_player_avatar
    from modules.safari_strategy import (
        SafariHuntingMode,
        get_navigation_path,
        get_safari_balls_left,
        get_safari_pokemon,
        get_safari_zone_config,
    )

    from dexbot.catching import _species_is_owned
    from dexbot.navigation import navigate_to

    if _species_is_owned(species_name):
        return
    target = get_safari_pokemon(species_name)
    if target is None or not target.value.availability():
        raise SkillError(f"{species_name} has no FireRed safari spot")
    config = get_safari_zone_config(context.rom)

    def enter() -> Generator:
        if get_player().money < 500:
            raise SkillError("Not enough money for the Safari Zone entry fee")
        yield from navigate_to(config["map"], config["entrance_tile"])
        yield from ensure_facing_direction(config["facing_direction"])
        context.emulator.hold_button(config["facing_direction"])
        for _ in range(10):
            yield
        context.emulator.release_button(config["facing_direction"])
        yield
        yield from wait_for_script_to_start_and_finish(config["ask_script"], "A")
        yield from wait_for_script_to_start_and_finish(config["enter_script"], "A")
        yield from wait_for_player_avatar_to_be_controllable()

    def retire() -> Generator:
        yield from StartMenuNavigator("RETIRE").step()
        yield from wait_for_script_to_start_and_finish(config["exit_script"], "A")
        yield from wait_for_player_avatar_to_be_standing_still()

    hunt_map = target.value.map_location
    hunt_tile = target.value.tile_location

    for attempt in range(_MAX_ENTRIES):
        if _species_is_owned(species_name):
            break
        _log_event(skill="safari_run", status="phase", phase=f"entry_{attempt}")
        if not _inside_safari():
            yield from enter()
        # Internal legs: safari areas are plain connected maps once inside.
        for leg_map, leg_coords in get_navigation_path(hunt_map, hunt_tile):
            yield from navigate_same_level(leg_map, leg_coords)
            if not _inside_safari():
                break  # PA called time mid-walk — re-enter
        if not _inside_safari():
            continue

        def done() -> bool:
            return (
                _species_is_owned(species_name)
                or not _inside_safari()  # PA warp-out (steps exhausted)
                or get_safari_balls_left() == 0
            )

        if target.value.mode == SafariHuntingMode.FISHING:
            from dexbot.catching import _fish_until, _shore_tiles

            rod = target.value.hunting_object or "Super Rod"
            facing = dict(_shore_tiles(tuple(hunt_map.value))).get(tuple(hunt_tile))
            yield from _fish_until(rod, facing, done)
        else:
            yield from spin(stop_condition=done)

        if _species_is_owned(species_name):
            break
        if _inside_safari() and get_safari_balls_left() == 0:
            yield from retire()  # fresh 30 balls next entry

    if not _species_is_owned(species_name):
        raise SkillError(f"Safari: {species_name} not caught in {_MAX_ENTRIES} entries")
    if _inside_safari():
        yield from retire()
    _log_event(skill="safari_run", status="caught", species=species_name)


def main() -> None:
    import sys
    from pathlib import Path

    from dexbot import PROJECT_ROOT
    from dexbot.catching import make_catch_decider
    from dexbot.emulator import setup_headless_emulator
    from dexbot.runner import run_skill

    species = sys.argv[1]
    fixture = sys.argv[2] if len(sys.argv) > 2 else "m8_exp_share.ss1"
    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / fixture).read_bytes())
    context.emulator.run_single_frame()
    run_skill(safari_run(species), f"safari_{species}", timeout_frames=1_500_000,
              on_battle_started=make_catch_decider(species))
    print(f"{species} caught")
    (PROJECT_ROOT / "fixtures" / f"m8_safari_{species.lower()}.ss1").write_bytes(
        context.emulator.get_save_state()
    )


if __name__ == "__main__":
    main()
