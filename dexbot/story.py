"""Story-progression skills (the brief's progress_story): each clears one
roadblock, is idempotent, and is verified by an event flag.

Run:  .venv/bin/python -m dexbot.story clear_mt_moon <in_fixture> <out_fixture>
"""

import sys
from typing import Generator

from dexbot import PROJECT_ROOT
from dexbot.catching import ensure_healthy
from dexbot.navigation import navigate_to
from dexbot.runner import SkillError, run_skill

MT_MOON_B2F = (1, 3)


def clear_mt_moon() -> Generator:
    """Beat Super Nerd Miguel and take the Helix Fossil, opening the east exit.

    Deterministic fossil choice: Helix (Omanyte) — one fossil per cart, documented
    in KNOWN_LIMITATIONS.
    """
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable

    if get_event_flag("GOT_FOSSIL_FROM_MT_MOON"):
        return

    # The B2F tunnel chains several grunt fights plus Miguel (Grimer/Voltorb/
    # Koffing L12, resists Fighting) with no healing in between — overlevel first.
    from dexbot.planner import grind_levels
    from modules.pokemon_party import get_party

    if max(p.level for p in get_party() if not p.is_egg) < 16:
        yield from grind_levels(16)

    # Stock up on potions for the gauntlet (as affordable).
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.player import get_player

    if get_item_bag().quantity_of(get_item_by_name("Potion")) < 5:
        affordable = get_player().money // 300
        if affordable > 0:
            from dexbot.openings import buy_items

            yield from buy_items([("Potion", min(8, affordable))], MapFRLG.PEWTER_CITY_MART)

    yield from ensure_healthy(minimum_fraction=0.9)

    # Walk up to Miguel (grunt line-of-sight fights on the way are handled by
    # the battle listener via the navigation interruption handler).
    yield from navigate_to(MT_MOON_B2F, (13, 12))
    yield from talk_to_npc(3)  # Super Nerd Miguel — battle starts via listener
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    # Take the Helix Fossil (right one of the pair on the platform).
    from modules.context import context

    yield from navigate_to(MT_MOON_B2F, (14, 8))
    yield from ensure_facing_direction("Up")
    context.emulator.press_button("A")
    yield
    yield from wait_for_yes_no_question("Yes")
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("GOT_FOSSIL_FROM_MT_MOON"):
        raise SkillError("Fossil not obtained — Mt Moon east exit still blocked")


def cross_nugget_bridge() -> Generator:
    """Fight up Nugget Bridge (rival + five trainers + the Rocket recruiter)."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag, get_event_var
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    def rocket_done() -> bool:
        # The Nugget Bridge Rocket sets VAR_MAP_SCENE_ROUTE24=1 on defeat
        # (the HIDE_NUGGET_BRIDGE_ROCKET flag is unrelated).
        return get_event_var("MAP_SCENE_ROUTE24") >= 1

    if rocket_done():
        return

    # The Cerulean rival (Pidgeotto 17/Abra 16/Rattata 15/Bulbasaur 18) ambushes
    # north of town. Caught fodder in the party makes in-battle rotation
    # possible, and the rotation flow can stall unwinnable fights — deposit
    # everything but the champion, then overlevel it (solo XP is faster too).
    from dexbot.boxes import deposit_party_fodder
    from dexbot.planner import grind_levels
    from modules.pokemon_party import get_party

    yield from deposit_party_fodder(keep=1)
    if max(p.level for p in get_party() if not p.is_egg) < 26:
        yield from grind_levels(26)

    # Climb with heal stops (Cerulean's PC is one screen south; beaten trainers
    # stay beaten). Stop one tile SOUTH of the Rocket's trigger row (y=15) so the
    # last heal actually lands before the fight — then full-heal and step in.
    from modules.context import context
    from modules.player import get_player_avatar

    for waypoint in [(11, 31), (11, 24), (11, 18), (11, 16)]:
        yield from ensure_healthy(minimum_fraction=0.6)
        yield from navigate_to(MapFRLG.ROUTE24, waypoint)
    # Full heal right before the Rocket — a chipped lead just faints and loops.
    yield from ensure_healthy(minimum_fraction=2.0)
    yield from navigate_to(MapFRLG.ROUTE24, (11, 16))
    # Step onto the trigger row (y=15) and A-mash: holding Up reaches the tile
    # but only A advances the Rocket's "Halt!" dialogue into his battle, which
    # the battle listener then fights at full HP.
    for _ in range(600):
        if get_player_avatar().local_coordinates[1] > 15:
            context.emulator.hold_button("Up")
        else:
            context.emulator.reset_held_buttons()
            context.emulator.press_button("A")
        yield
        if rocket_done():
            break
    context.emulator.reset_held_buttons()
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not rocket_done():
        raise SkillError("Nugget Bridge Rocket not defeated (VAR_MAP_SCENE_ROUTE24 unset)")


def visit_bill() -> Generator:
    """Route 25 gauntlet to the Sea Cottage; help Bill; receive the SS Ticket."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    if get_event_flag("GOT_SS_TICKET"):
        return

    for waypoint in [(MapFRLG.ROUTE25, (20, 6)), (MapFRLG.ROUTE25, (40, 6))]:
        yield from ensure_healthy(minimum_fraction=0.6)
        yield from navigate_to(*waypoint)
    yield from ensure_healthy(minimum_fraction=0.6)
    yield from navigate_to(MapFRLG.ROUTE25_SEA_COTTAGE, (5, 6))

    # Bill is the Pokémon on the floor; help him (Yes), he runs the machine,
    # then interact with the console, then he hands over the SS Ticket.
    yield from talk_to_npc(1)
    yield from wait_for_yes_no_question("Yes")
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("GOT_SS_TICKET"):
        # The machine console step: Bill entered the teleporter; press A on it.
        from modules.modes.util.walking import ensure_facing_direction

        yield from navigate_to(MapFRLG.ROUTE25_SEA_COTTAGE, (2, 5))
        yield from ensure_facing_direction("Up")
        _ctx().emulator.press_button("A")
        yield
        yield from wait_for_no_script_to_run("A")
        yield from wait_for_player_avatar_to_be_controllable("A")
        # Talk to restored Bill for the ticket.
        yield from talk_to_npc(1)
        yield from wait_for_no_script_to_run("A")
        yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("GOT_SS_TICKET"):
        raise SkillError("SS Ticket not obtained from Bill")


def _ctx():
    from modules.context import context

    return context


STORY_SKILLS = {
    "clear_mt_moon": clear_mt_moon,
    "cross_nugget_bridge": cross_nugget_bridge,
    "visit_bill": visit_bill,
}


def main() -> None:
    from dexbot.catching import fight_all_battles
    from dexbot.emulator import setup_headless_emulator

    which = sys.argv[1]
    fixture = sys.argv[2] if len(sys.argv) > 2 else "m7_badge_brock.ss1"
    out = sys.argv[3] if len(sys.argv) > 3 else f"m7_{which}.ss1"

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / fixture).read_bytes())
    context.emulator.run_single_frame()

    attempts = 0
    while True:
        attempts += 1
        try:
            run_skill(STORY_SKILLS[which](), which, timeout_frames=900_000, on_battle_started=fight_all_battles)
            break
        except Exception as e:  # noqa: BLE001 — bounded retries; last error re-raised
            if attempts >= 3:
                raise
            print(f"attempt {attempts} failed ({type(e).__name__}: {e}); healing, then retrying")
            from dexbot.catching import ensure_healthy

            try:
                run_skill(ensure_healthy(minimum_fraction=2.0), "retry_heal", timeout_frames=120_000)
            except Exception as heal_error:  # noqa: BLE001
                print(f"retry heal failed ({heal_error}); retrying anyway")
    print(f"{which} done")
    (PROJECT_ROOT / "fixtures" / out).write_bytes(context.emulator.get_save_state())


if __name__ == "__main__":
    main()
