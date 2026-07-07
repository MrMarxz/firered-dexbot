"""M7: gym battles. Each badge is a sub-milestone with its own savestate test.

The battle itself is upstream's DefaultBattleStrategy (damage-calc move choice,
switching). Our job per gym: precondition checks (level, type coverage), the
walk, the talk, and verifying the badge flag afterwards.

Run:  .venv/bin/python -m dexbot.gyms brock
"""

import sys
from typing import Generator

from dexbot import PROJECT_ROOT
from dexbot.catching import ensure_healthy
from dexbot.navigation import navigate_to
from dexbot.planner import grind_levels
from dexbot.runner import SkillError, run_skill


def beat_brock(min_level: int = 13) -> Generator:
    """Beat Brock (requires a healthy, sufficiently-leveled water lead)."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.pokemon_party import get_party

    if get_event_flag("BADGE01_GET"):
        return

    # Water is 4x effective against Geodude/Onix, Fighting 2x; the level floor is
    # the "projected to lose" guard for v1 (proper damage projection in later gyms).
    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)  # caller must run with a Fight policy
    good_moves = ("Bubble", "Water Gun", "Karate Chop", "Low Kick")
    if not any(get_party().has_pokemon_with_move(move) for move in good_moves):
        moves = [(p.species.name, p.level, [m.move.name for m in p.moves if m]) for p in get_party()]
        raise SkillError(f"No move that beats Rock-types in the party: {moves}")

    from modules.map_data import PokemonCenter

    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.PewterCity)

    yield from navigate_to(MapFRLG.PEWTER_CITY_GYM, (4, 3))  # in front of Brock
    yield from talk_to_npc(1)  # Brock
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("BADGE01_GET"):
        raise SkillError("Brock was not defeated (badge flag unset)")


def beat_misty(min_level: int = 29) -> Generator:
    """Beat Misty. Her Starmie L21 has Recover, and Water moves are resisted by
    her Water types — so we rely on the damage-calc strategy picking the best
    neutral move plus a level advantage to out-race the healing."""
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.pokemon_party import get_party

    if get_event_flag("BADGE02_GET"):
        return

    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)  # caller must run with a Fight policy

    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.CeruleanCity)

    yield from navigate_to(MapFRLG.CERULEAN_CITY_GYM, (8, 7))  # in front of Misty (obj at 8,6)
    yield from talk_to_npc(3)  # Misty
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("BADGE02_GET"):
        raise SkillError("Misty was not defeated (badge flag unset)")


def _cut_tree(map_enum, tree_tile: tuple[int, int], stand_tile: tuple[int, int], facing: str) -> Generator:
    """Cut the tree at `tree_tile` from `stand_tile` facing `facing` (needs a
    party member with Cut + Cascade Badge). FRLG flow: face tree → A → yes."""
    from modules.context import context
    from modules.map import get_map_objects
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable

    map_key = map_enum.value if hasattr(map_enum, "value") else map_enum
    if not any(
        o.map_group_and_number == map_key and o.current_coords == tree_tile and "isPlayer" not in o.flags
        for o in get_map_objects()
    ):
        # Tree object not live-loaded here: either we're far away (it will be
        # checked again after walking) or it's already cut. Walk first.
        pass
    yield from navigate_to(map_enum, stand_tile)
    if not any(o.current_coords == tree_tile and "isPlayer" not in o.flags for o in get_map_objects()):
        return  # already cut (object gone until map reload)
    yield from ensure_facing_direction(facing)
    context.emulator.press_button("A")
    yield
    yield from wait_for_yes_no_question("Yes")
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")


def _press_trash_can(can_id: int) -> Generator:
    """Press A on Vermilion gym trash can #can_id (1-15; 3 rows × 5 cans)."""
    from modules.context import context
    from modules.map_data import MapFRLG
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable

    x = 1 + 2 * ((can_id - 1) % 5)
    y = 10 + 2 * ((can_id - 1) // 5)
    yield from navigate_to(MapFRLG.VERMILION_CITY_GYM, (x, y + 1))
    yield from ensure_facing_direction("Up")
    context.emulator.press_button("A")
    yield
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")


def _escape_vermilion_gym_yard() -> Generator:
    """The gym yard is a pocket sealed by the cut tree, which RESPAWNS on map
    reload — leaving the gym after any interior trip strands the player there.
    If we're in the gym or the yard, cut our way out (from the yard side)."""
    from modules.map_data import MapFRLG
    from modules.modes.util.walking import navigate_to as navigate_same_level
    from modules.player import get_player_avatar

    avatar = get_player_avatar()
    if avatar.map_group_and_number == MapFRLG.VERMILION_CITY_GYM.value:
        yield from navigate_same_level(MapFRLG.VERMILION_CITY_GYM, (5, 19))  # exit warp → yard
        avatar = get_player_avatar()
    if avatar.map_group_and_number == MapFRLG.VERMILION_CITY.value:
        x, y = avatar.local_coordinates
        if 13 <= x <= 19 and 24 <= y <= 26:  # the fenced yard strip
            yield from _cut_tree(MapFRLG.VERMILION_CITY, (19, 24), (19, 25), "Up")
            yield from navigate_same_level(MapFRLG.VERMILION_CITY, (19, 23))


def beat_surge(min_level: int = 38) -> Generator:
    """Beat Lt. Surge (badge 3). Steps: cut the tree at the gym fence, solve the
    trash-can lock by READING the switch locations from VAR_TEMP_0/1 (set by
    SetVermilionTrashCans on map load — no guessing), cross the opened beam
    door blind (the pathfinder's tile cache still thinks it is a wall), fight."""
    from modules.context import context
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag, get_event_var
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.player import get_player_avatar
    from modules.pokemon_party import get_party

    if get_event_flag("BADGE03_GET"):
        return

    if not get_party().has_pokemon_with_move("Cut"):
        raise SkillError("No party member knows Cut — run get_hm_cut first")
    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)

    from dexbot.runner import _log_event

    yield from _escape_vermilion_gym_yard()  # no-op unless resuming from inside
    # Gym roster: the starter + HM mule only. Caught fodder like a Teleport-only
    # Abra becomes the active battler when the lead faints and the battle
    # strategy hard-errors on "no damaging moves".
    from dexbot.boxes import deposit_party_fodder

    yield from deposit_party_fodder(keep=1)
    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.VermilionCity)

    # Surge chains Selfdestruct + 2x Electric — the healing battle strategy
    # needs potions to out-last it (same lesson as the S.S. Anne rival).
    from modules.items import get_item_bag, get_item_by_name
    from modules.player import get_player

    if get_item_bag().quantity_of(get_item_by_name("Super Potion")) < 5:
        if get_player().money < 5 * 700 and get_item_bag().quantity_of(get_item_by_name("Nugget")) > 0:
            from dexbot.openings import sell_items

            yield from sell_items([("Nugget", 1)], MapFRLG.VERMILION_CITY_MART)
        affordable = get_player().money // 700
        if affordable > 0:
            from dexbot.openings import buy_items

            yield from buy_items([("Super Potion", min(8, affordable))], MapFRLG.VERMILION_CITY_MART)

    # Tree in the gym fence: the yard south of it is a pocket only the gym
    # door connects to — the cut is made from the city side, standing NORTH.
    _log_event(skill="beat_surge", status="phase", phase="cut_tree")
    yield from _cut_tree(MapFRLG.VERMILION_CITY, (19, 24), (19, 23), "Down")
    _log_event(skill="beat_surge", status="phase", phase="enter_gym")
    yield from navigate_to(MapFRLG.VERMILION_CITY_GYM, (5, 16))  # entrance hall

    _log_event(skill="beat_surge", status="phase", phase="trash_puzzle")
    for attempt in range(5):
        if get_event_flag("FOUND_BOTH_VERMILION_GYM_SWITCHES"):
            break
        # The correct cans are in temp vars; re-read after every press — a
        # wrong second can re-randomizes both.
        first = get_event_var("TEMP_0")
        if not 1 <= first <= 15:
            raise SkillError(f"Unexpected trash-can var TEMP_0={first}")
        yield from _press_trash_can(first)
        second = get_event_var("TEMP_1")
        if 1 <= second <= 15:
            yield from _press_trash_can(second)
    if not get_event_flag("FOUND_BOTH_VERMILION_GYM_SWITCHES"):
        raise SkillError("Could not open the gym locks (trash-can vars mismatched?)")

    # Top up before Surge: the hall trainers chip the lead, and a chipped
    # Wartortle loses to Raichu's 2x Electric. Beams stay open across map
    # reloads (ON_LOAD re-applies from the flag — verified), so a heal
    # round-trip is safe once the puzzle is solved.
    lead = get_party()[0]
    if lead.current_hp / lead.total_hp < 0.9:
        yield from _escape_vermilion_gym_yard()
        yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.VermilionCity)
        yield from _cut_tree(MapFRLG.VERMILION_CITY, (19, 24), (19, 23), "Down")

    # Cross the beam wall: pret's SetBeamsOff opens the MIDDLE columns (x=4-6,
    # y=6-7); the pathfinder's tile cache still thinks it's a wall, so step
    # blind up column 5 until we are in Surge's room (y <= 5).
    _log_event(skill="beat_surge", status="phase", phase="door")
    yield from navigate_to(MapFRLG.VERMILION_CITY_GYM, (5, 9))
    for _ in range(600):
        if get_player_avatar().local_coordinates[1] <= 5:
            break
        context.emulator.hold_button("Up")
        yield
    context.emulator.reset_held_buttons()
    if get_player_avatar().local_coordinates[1] > 5:
        raise SkillError("Beam door did not open (still south of Surge's room)")

    # In Surge's room the cache is walkable again; walk up to him manually
    # (navigate_to would try to path from a 'wall' tile — keep it simple).
    from modules.modes.util.walking import navigate_to as navigate_same_level

    _log_event(skill="beat_surge", status="phase", phase="fight")
    yield from navigate_same_level(MapFRLG.VERMILION_CITY_GYM, (5, 3))  # in front of Surge (obj at 5,2)
    yield from talk_to_npc(1)  # Lt. Surge
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")

    if not get_event_flag("BADGE03_GET"):
        raise SkillError("Surge was not defeated (badge flag unset)")

    # Walk back out through the beam gap (column 5): the pathfinder's cached
    # collision thinks Surge's room is walled in, so ANY later navigation
    # planned from inside would fail. Leave the player in the entrance hall.
    yield from navigate_same_level(MapFRLG.VERMILION_CITY_GYM, (5, 5))
    for _ in range(600):
        if get_player_avatar().local_coordinates[1] >= 8:
            break
        context.emulator.hold_button("Down")
        yield
    context.emulator.reset_held_buttons()
    if get_player_avatar().local_coordinates[1] < 8:
        raise SkillError("Could not walk back out of Surge's room")
    # Leave the gym AND the yard (the tree respawned when the city reloads) so
    # the skill ends in a normally-navigable spot.
    yield from _escape_vermilion_gym_yard()


GYMS = {"brock": beat_brock, "misty": beat_misty, "surge": beat_surge}
_DEFAULT_FIXTURE = {"brock": "m6_pre_brock_dex.ss1", "misty": "m7_ss_ticket.ss1", "surge": "m7_cerulean_sweep.ss1"}


def main() -> None:
    from dexbot.emulator import setup_headless_emulator

    which = sys.argv[1] if len(sys.argv) > 1 else "brock"
    fixture = sys.argv[2] if len(sys.argv) > 2 else _DEFAULT_FIXTURE.get(which, "m7_ss_ticket.ss1")
    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / fixture).read_bytes())
    context.emulator.run_single_frame()

    from dexbot.catching import fight_all_battles

    run_skill(GYMS[which](), f"beat_{which}", timeout_frames=900_000, on_battle_started=fight_all_battles)
    print(f"{which} defeated")
    (PROJECT_ROOT / "fixtures" / f"m7_badge_{which}.ss1").write_bytes(context.emulator.get_save_state())


if __name__ == "__main__":
    main()
