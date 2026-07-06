"""M4: scripted opening sequence — starter, rival fight, Oak's parcel, Pokédex.

Composable generator skills, all driven by memory state (script stack, event
flags/vars, party contents). Run with dexbot.runner.run_skill, which provides
battle handling via upstream's bot listeners.

Run everything from a fresh save:  .venv/bin/python -m dexbot.openings
"""

from typing import Generator

from dexbot import PROJECT_ROOT
from dexbot.navigation import navigate_to
from dexbot.runner import SkillError

SQUIRTLE_BALL_STAND_TILE = (9, 5)  # below the middle ball on the lab table


def _ctx():
    from modules.context import context

    return context


def acquire_starter() -> Generator:
    """From a fresh post-intro state: trigger the Oak cutscene, pick Squirtle."""
    from modules.map_data import MapFRLG
    from modules.modes.util.tasks_scripts import (
        wait_for_script_to_start_and_finish,
        wait_for_yes_no_question,
        wait_until_script_is_no_longer_active,
    )
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as nav_same,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.pokemon_party import get_party

    if len(get_party()) > 0:
        return  # idempotent: already own a Pokémon

    # Walking into (12,1) on Pallet Town triggers PalletTown_EventScript_OakTrigger*.
    yield from navigate_to(MapFRLG.PALLET_TOWN, (12, 2))
    yield from nav_same(MapFRLG.PALLET_TOWN.value, (12, 1), avoid_scripted_events=False, expecting_script=True)
    # Oak walks us to the lab; the cutscene ends with the player standing next
    # to the starter table, free to choose.
    yield from wait_for_script_to_start_and_finish("PalletTown_ProfessorOaksLab_ChooseStarterScene", "A")
    yield from wait_for_player_avatar_to_be_controllable()

    yield from nav_same(MapFRLG.PALLET_TOWN_PROFESSOR_OAKS_LAB.value, SQUIRTLE_BALL_STAND_TILE)
    yield from ensure_facing_direction("Up")
    _ctx().emulator.press_button("A")
    yield
    yield from wait_for_yes_no_question("Yes")  # "So! You want SQUIRTLE?"
    yield from wait_for_yes_no_question("No")  # "Give a nickname?"
    yield from wait_until_script_is_no_longer_active("PalletTown_ProfessorOaksLab_EventScript_Squirtle", "A")
    # The rival immediately walks over and takes Bulbasaur — wait that scene out too.
    yield from wait_for_script_to_start_and_finish("PalletTown_ProfessorOaksLab_EventScript_RivalTakesStarter", "A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    party = get_party()
    if len(party) == 0 or party[0].species.name != "Squirtle":
        raise SkillError(f"Expected Squirtle in party, got {[p.species.name for p in party]}")


def beat_lab_rival() -> Generator:
    """Walk towards the lab exit, triggering (and winning) the first rival fight."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        navigate_to as nav_same,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.pokemon_party import get_party

    if get_event_flag("BEAT_RIVAL_IN_OAKS_LAB"):
        return

    # Walking south towards the door triggers the rival battle script. The
    # battle itself is handled by the BattleListener (default battle strategy).
    yield from nav_same(
        MapFRLG.PALLET_TOWN_PROFESSOR_OAKS_LAB.value, (6, 11), avoid_scripted_events=False, expecting_script=True
    )
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("BEAT_RIVAL_IN_OAKS_LAB"):
        raise SkillError("Rival battle in Oak's lab was not won")
    if get_party()[0].current_hp == 0:
        raise SkillError("Starter fainted — lost the rival fight")


def deliver_parcel_get_pokedex() -> Generator:
    """Fetch Oak's Parcel from Viridian Mart, deliver it, receive the Pokédex."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as nav_same,
        wait_for_player_avatar_to_be_controllable,
    )

    if get_event_flag("SYS_POKEDEX_GET"):
        return

    parcel = get_item_by_name("Oak’s Parcel")  # typographic apostrophe in items.json
    if get_item_bag().quantity_of(parcel) == 0:
        # Clerk is behind the counter — stand in front of it and talk across.
        yield from navigate_to(MapFRLG.VIRIDIAN_CITY_MART, (4, 3))
        yield from ensure_facing_direction("Left")
        _ctx().emulator.press_button("A")
        yield
        yield from wait_for_no_script_to_run("A")
        yield from wait_for_player_avatar_to_be_controllable("A")
        if get_item_bag().quantity_of(parcel) == 0:
            raise SkillError("Did not receive Oak's Parcel from the Viridian Mart clerk")

    yield from navigate_to(MapFRLG.PALLET_TOWN_PROFESSOR_OAKS_LAB, (6, 5))
    yield from talk_to_npc(4)  # Professor Oak at his desk
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("SYS_POKEDEX_GET"):
        raise SkillError("Pokédex flag not set after talking to Oak")


def buy_items(shopping_list, mart=None) -> Generator:
    """Buy a list of (item_name, quantity) at a mart (default: Viridian). FRLG
    mart interiors share one layout, so the counter position works everywhere.

    FRLG's mart flow (observed): clerk script → Buy/Sell/Quit list (A picks Buy)
    → Task_BuyMenu item list → Task_BuyHowManyDialogueHandleInput → yes/no.
    Upstream's buy_in_shop expects a Task_ShopMenu state that FRLG skips through,
    so this drives the buy menu directly with the same mart helpers.
    """
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.mart import get_mart_buy_menu_scroll_position, get_mart_buyable_items
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_until_task_is_active
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable
    from modules.tasks import get_task

    if mart is None:
        mart = MapFRLG.VIRIDIAN_CITY_MART
    wanted = [(get_item_by_name(name), quantity) for name, quantity in shopping_list]
    starting = {item.index: get_item_bag().quantity_of(item) for item, _ in wanted}

    yield from navigate_to(mart, (4, 3))
    yield from ensure_facing_direction("Left")
    _ctx().emulator.press_button("A")
    yield
    yield from wait_until_task_is_active("Task_BuyMenu", "A")
    for _ in range(20):
        yield

    buyable = get_mart_buyable_items()
    for item, quantity in wanted:
        if item not in buyable:
            continue
        slot = buyable.index(item)
        while get_mart_buy_menu_scroll_position() != slot:
            _ctx().emulator.press_button("Up" if get_mart_buy_menu_scroll_position() > slot else "Down")
            yield
            yield
        yield from wait_until_task_is_active("Task_BuyHowManyDialogueHandleInput", "A")
        while (current := get_task("Task_BuyHowManyDialogueHandleInput").data_value(1)) != quantity:
            _ctx().emulator.press_button("Up" if current < quantity else "Down")
            yield
            yield
        # A-mash confirms the quantity, the price yes/no, and the "Here you
        # are!" message, landing back in the item list.
        yield from wait_until_task_is_active("Task_BuyMenu", "A")
        for _ in range(20):
            yield
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")

    for item, quantity in wanted:
        if item in buyable and get_item_bag().quantity_of(item) < starting[item.index] + quantity:
            raise SkillError(f"Purchase of {item.name} failed")


def buy_pokeballs(quantity: int = 10, mart=None) -> Generator:
    yield from buy_items([("Poké Ball", quantity)], mart)


def scripted_opening() -> Generator:
    """Fresh post-intro bedroom state → own Pokédex + Poké Balls in the bag."""
    yield from acquire_starter()
    yield from beat_lab_rival()
    yield from deliver_parcel_get_pokedex()
    yield from buy_pokeballs()


def main() -> None:
    from dexbot.emulator import setup_headless_emulator
    from dexbot.new_game import run_new_game_intro
    from dexbot.runner import run_skill

    context = setup_headless_emulator(is_test_run=True)
    run_new_game_intro(context.emulator)

    fixtures = PROJECT_ROOT / "fixtures"
    run_skill(acquire_starter(), "acquire_starter", timeout_frames=60_000)
    run_skill(beat_lab_rival(), "beat_lab_rival", timeout_frames=60_000)
    (fixtures / "m4_post_lab.ss1").write_bytes(context.emulator.get_save_state())
    run_skill(deliver_parcel_get_pokedex(), "deliver_parcel_get_pokedex", timeout_frames=150_000)
    run_skill(buy_pokeballs(), "buy_pokeballs", timeout_frames=60_000)
    (fixtures / "m4_pokedex.ss1").write_bytes(context.emulator.get_save_state())

    from dexbot.telemetry import capture_state
    import json

    print(json.dumps(capture_state(), indent=1))


if __name__ == "__main__":
    main()
