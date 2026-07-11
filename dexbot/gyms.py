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
    from dexbot.navigation import perform_cut

    yield from perform_cut(map_enum, tree_tile, stand_tile, facing)


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


def beat_erika(min_level: int = 40) -> Generator:
    """Beat Erika (badge 4, Celadon). Her Grass types resist Blastoise's Water,
    so the damage plan is neutral moves (Bite) plus a hard level lead; the
    healing battle strategy drinks Super Potions through Sleep Powder turns."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.player import get_player
    from modules.pokemon_party import get_party

    from dexbot.boxes import deposit_party_fodder
    from dexbot.planner import _nearest_mart
    from dexbot.runner import _log_event

    if get_event_flag("BADGE04_GET"):
        return

    yield from deposit_party_fodder(keep=1)
    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)
    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.CeladonCity)

    if get_item_bag().quantity_of(get_item_by_name("Super Potion")) < 5:
        affordable = get_player().money // 700
        if affordable > 0:
            from dexbot.openings import buy_items

            yield from buy_items([("Super Potion", min(8, affordable))], _nearest_mart())

    # Erika's garden is sealed by an interior cut hedge at (6,8) — a warp-less
    # pocket the nav graph cannot model, so enter the gym, cut, then walk.
    _log_event(skill="beat_erika", status="phase", phase="enter_gym")
    yield from navigate_to(MapFRLG.CELADON_CITY_GYM, (6, 9))  # below the hedge
    yield from _cut_tree(MapFRLG.CELADON_CITY_GYM, (6, 8), (6, 9), "Up")

    from modules.modes.util.walking import navigate_to as navigate_same_level

    _log_event(skill="beat_erika", status="phase", phase="fight")
    yield from navigate_same_level(MapFRLG.CELADON_CITY_GYM, (6, 5))  # in front of Erika (obj 7 @ 6,4)
    yield from talk_to_npc(7)
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")

    if not get_event_flag("BADGE04_GET"):
        raise SkillError("Erika was not defeated (badge flag unset)")


def beat_koga(min_level: int = 45) -> Generator:
    """Beat Koga (badge 5, Fuchsia). The gym's invisible walls are real
    collision in the map data, so A* threads the maze natively; the six
    trainers en route are line-of-sight ambushes handled by the battle
    listener. His Poison team leans on Toxic and Self-Destruct (Koffing),
    so we bring a full-HP lead and a hard level floor."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.player import get_player
    from modules.pokemon_party import get_party

    from dexbot.planner import _nearest_mart
    from dexbot.runner import _log_event

    if get_event_flag("BADGE05_GET"):
        return

    # Bring a diverse team (Koga is Poison), not a solo lead + L11 mule — one
    # faint on solo Blastoise sent the mule out and whited us out. assemble_party
    # keeps HM mules and fills with the best battlers.
    from dexbot.team import TeamObjective, assemble_party

    yield from assemble_party(
        TeamObjective(kind="gym", field_moves=("Cut",), prefer_offense_types=("Ground", "Psychic"),
                      avoid_defense_types=("Poison",))
    )
    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)
    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.FuchsiaCity)

    # Hyper Potions (200 HP) out-heal Toxic + Sludge where Super Potions (50)
    # can't; buy as many as affordable, fall back to Super if broke.
    from dexbot.openings import buy_items

    if get_item_bag().quantity_of(get_item_by_name("Hyper Potion")) < 15:
        # A full-stack loadout: the last attempt used all 6 Hyper Potions and
        # nearly cleared the gauntlet + Koga. Buy up to 15 (bag max ~99) so the
        # attrition can't outlast the supply.
        hyper = min(15, get_player().money // 1200)
        if hyper > 0:
            yield from buy_items([("Hyper Potion", hyper)], _nearest_mart())
    if get_item_bag().quantity_of(get_item_by_name("Hyper Potion")) < 4 and get_item_bag().quantity_of(
        get_item_by_name("Super Potion")
    ) < 5:
        supers = min(8, get_player().money // 700)
        if supers > 0:
            yield from buy_items([("Super Potion", supers)], _nearest_mart())

    _log_event(skill="beat_koga", status="phase", phase="enter_gym")
    yield from navigate_to(MapFRLG.FUCHSIA_CITY_GYM, (7, 14))  # below Koga (obj 7 @ 7,13)

    _log_event(skill="beat_koga", status="phase", phase="fight")
    yield from talk_to_npc(7)
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")

    if not get_event_flag("BADGE05_GET"):
        raise SkillError("Koga was not defeated (badge flag unset)")


def beat_sabrina(min_level: int = 45) -> Generator:
    """Beat Sabrina (badge 6, Saffron). The gym is a teleporter-pad maze —
    the pads are ordinary self-referencing warps, so the warp graph routes
    them natively (no locked doors, unlike Silph). Her Psychic team hits
    hard and fast; bring the full team + deep potions."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.player import get_player
    from modules.pokemon_party import get_party

    from dexbot.planner import _nearest_mart
    from dexbot.runner import _log_event

    if get_event_flag("BADGE06_GET"):
        return

    from dexbot.team import TeamObjective, assemble_party

    yield from assemble_party(
        TeamObjective(kind="gym", field_moves=("Cut",), avoid_defense_types=("Psychic",))
    )
    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)
    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.SaffronCity)

    from dexbot.openings import buy_items

    if get_item_bag().quantity_of(get_item_by_name("Hyper Potion")) < 10:
        hyper = min(10, get_player().money // 1200)
        if hyper > 0:
            yield from buy_items([("Hyper Potion", hyper)], _nearest_mart())

    _log_event(skill="beat_sabrina", status="phase", phase="enter_gym")
    yield from navigate_to(MapFRLG.SAFFRON_CITY_GYM, (14, 12))  # below Sabrina (obj 7 @ 14,11)

    _log_event(skill="beat_sabrina", status="phase", phase="fight")
    yield from talk_to_npc(7)
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")

    if not get_event_flag("BADGE06_GET"):
        raise SkillError("Sabrina was not defeated (badge flag unset)")


def beat_blaine(min_level: int = 47) -> Generator:
    """Beat Blaine (badge 7, Cinnabar). Entry needs the Mansion Secret Key.
    Six Yes/No quiz panels gate the room doors: a right answer opens the
    door, a wrong one makes the room's trainer battle you and the door opens
    after the win — so answering "Yes" everywhere always progresses. His
    Fire team (Arcanine L47) melts under Water: Blastoise/Lapras/Gyarados."""
    from modules.context import context
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player, get_player_avatar
    from modules.pokemon_party import get_party

    from dexbot.navigation import _walkable
    from dexbot.planner import _nearest_mart
    from dexbot.runner import _log_event

    if get_event_flag("BADGE07_GET"):
        return

    # A fresh Secret Key run ends inside the Mansion, whose switch-door maze
    # general navigation cannot plan out of — walk out explicitly first.
    from dexbot.story import _MANSION_MAPS, leave_mansion

    if tuple(get_player_avatar().map_group_and_number) in _MANSION_MAPS:
        _log_event(skill="beat_blaine", status="phase", phase="leave_mansion")
        yield from leave_mansion()

    from dexbot.team import TeamObjective, assemble_party

    yield from assemble_party(
        TeamObjective(kind="gym", field_moves=("Cut",), avoid_defense_types=("Fire",))
    )
    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)
    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.CinnabarIsland)

    from dexbot.openings import buy_items

    if get_item_bag().quantity_of(get_item_by_name("Hyper Potion")) < 10:
        hyper = min(10, get_player().money // 1200)
        if hyper > 0:
            yield from buy_items([("Hyper Potion", hyper)], _nearest_mart())

    _log_event(skill="beat_blaine", status="phase", phase="enter_gym")
    gym = MapFRLG.CINNABAR_ISLAND_GYM
    yield from navigate_to(gym, (25, 21))

    # Quiz panels (bg events, from ROM), one pair per door, in room order
    # from the entrance, each with its CORRECT answer (from the decomp's
    # goto_if_eq branches — a wrong answer battles the room trainer and the
    # door STAYS CLOSED; only the right answer sets the flag and opens it).
    # Answered panels are tracked by their FLAG, not per-session.
    quizzes = [
        ((23, 10), "CINNABAR_GYM_QUIZ_1", "Yes"),
        ((16, 2), "CINNABAR_GYM_QUIZ_2", "No"),
        ((13, 10), "CINNABAR_GYM_QUIZ_3", "No"),
        ((13, 17), "CINNABAR_GYM_QUIZ_4", "No"),
        ((1, 18), "CINNABAR_GYM_QUIZ_5", "Yes"),
        ((1, 10), "CINNABAR_GYM_QUIZ_6", "No"),
    ]
    for _ in range(len(quizzes) + 4):
        pos = tuple(get_player_avatar().local_coordinates)
        if _walkable((gym.value, pos), (gym.value, (5, 5)), max_nodes=3_000):
            break  # Blaine's room is open
        panel = next(
            (
                (q, answer)
                for q, flag, answer in quizzes
                if not get_event_flag(flag)
                and _walkable((gym.value, pos), (gym.value, (q[0], q[1] + 1)), max_nodes=3_000)
            ),
            None,
        )
        if panel is None:
            raise SkillError("beat_blaine: no reachable unanswered quiz panel, Blaine still sealed")
        (px, py), answer = panel
        _log_event(skill="beat_blaine", status="phase", phase=f"quiz_{px}_{py}")
        yield from navigate_same_level(gym, (px, py + 1))
        yield from ensure_facing_direction("Up")
        context.emulator.press_button("A")
        yield
        yield from wait_for_yes_no_question(answer)
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")
        # A door just opened — drop stale negative A* verdicts.
        from dexbot.navigation import _walkable_neg

        _walkable_neg.clear()
    else:
        raise SkillError("beat_blaine: quiz loop exhausted without opening Blaine's room")

    # The gauntlet may have cost HP/faints (room trainers on wrong answers,
    # earlier runs) — Blaine at full strength is not the fight to wing.
    if any(p.current_hp < p.total_hp * 0.5 for p in get_party() if not p.is_egg):
        _log_event(skill="beat_blaine", status="phase", phase="pre_blaine_heal")
        yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.CinnabarIsland)
        yield from navigate_to(gym, (5, 6))  # doors stay open (flags)

    _log_event(skill="beat_blaine", status="phase", phase="fight")
    yield from navigate_same_level(gym, (5, 5))  # below Blaine (local_id 8 @ 5,4)
    yield from talk_to_npc(8)  # NOT 7 — that's Zac; local_ids are 1-based
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")

    if not get_event_flag("BADGE07_GET"):
        raise SkillError("Blaine was not defeated (badge flag unset)")


def beat_giovanni(min_level: int = 50) -> Generator:
    """Beat Giovanni (badge 8, Viridian — opens after badge 7). His all-
    Ground team folds to Water: Blastoise Surf sweeps. The gym's arrow
    spinners are forced-movement tiles the pathfinder models natively; the
    trainers en route are fought by the run's battle handler."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.player import get_player
    from modules.pokemon_party import get_party

    from dexbot.planner import _nearest_mart
    from dexbot.runner import _log_event

    if get_event_flag("BADGE08_GET"):
        return

    from dexbot.team import TeamObjective, assemble_party

    yield from assemble_party(
        TeamObjective(kind="gym", field_moves=("Cut",), avoid_defense_types=("Ground",),
                      prefer_offense_types=("Water", "Grass", "Ice"))
    )
    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)
    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.ViridianCity)

    from dexbot.openings import buy_items

    if get_item_bag().quantity_of(get_item_by_name("Hyper Potion")) < 8:
        hyper = min(8, get_player().money // 1200)
        if hyper > 0:
            yield from buy_items([("Hyper Potion", hyper)], _nearest_mart())

    _log_event(skill="beat_giovanni", status="phase", phase="enter_gym")
    yield from navigate_to(MapFRLG.VIRIDIAN_CITY_GYM, (2, 3))  # below Giovanni (local_id 8 @ 2,2)

    _log_event(skill="beat_giovanni", status="phase", phase="fight")
    yield from talk_to_npc(8)
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")

    if not get_event_flag("BADGE08_GET"):
        raise SkillError("Giovanni was not defeated (badge flag unset)")


GYMS = {"brock": beat_brock, "misty": beat_misty, "surge": beat_surge, "erika": beat_erika, "koga": beat_koga,
        "sabrina": beat_sabrina, "blaine": beat_blaine, "giovanni": beat_giovanni}
_DEFAULT_FIXTURE = {
    "brock": "m6_pre_brock_dex.ss1",
    "misty": "m7_ss_ticket.ss1",
    "surge": "m7_cerulean_sweep.ss1",
    "erika": "m7_rock_tunnel_sweep.ss1",
    "koga": "m8_post_snorlax.ss1",
    "sabrina": "m8_silph.ss1",
    "blaine": "m8_secret_key.ss1",
    "giovanni": "m7_badge_blaine.ss1",
}


def main() -> None:
    from dexbot.emulator import setup_headless_emulator

    which = sys.argv[1] if len(sys.argv) > 1 else "brock"
    fixture = sys.argv[2] if len(sys.argv) > 2 else _DEFAULT_FIXTURE.get(which, "m7_ss_ticket.ss1")
    if fixture == "--live":
        # Run against the persistent living-dex profile (same resume behavior
        # as run.py): the badge lands in current_state.ss1 for real.
        from dexbot.emulator import get_or_create_profile

        context = setup_headless_emulator(profile=get_or_create_profile("livingdex"), is_test_run=False)
        out = None
    else:
        context = setup_headless_emulator(is_test_run=True)
        context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / fixture).read_bytes())
        out = PROJECT_ROOT / "fixtures" / f"m7_badge_{which}.ss1"
    context.emulator.run_single_frame()

    from dexbot.runner import attach_video_window

    attach_video_window(context, "dexbot gym")

    from dexbot.catching import fight_all_battles

    run_skill(GYMS[which](), f"beat_{which}", timeout_frames=900_000, on_battle_started=fight_all_battles)
    print(f"{which} defeated")
    if out is not None:
        out.write_bytes(context.emulator.get_save_state())


if __name__ == "__main__":
    main()
