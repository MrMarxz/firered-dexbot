"""M4 acceptance: the opening sequence produced the expected world state.

The full fresh-boot run (python -m dexbot.openings) takes ~8 minutes and
regenerates these fixtures; the test asserts on its saved outcome.
"""

from dexbot import PROJECT_ROOT


def test_post_opening_state():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m4_pokedex.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.items import get_item_bag, get_item_by_name
    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert get_event_flag("SYS_POKEDEX_GET"), "should own the Pokédex"
    assert get_event_flag("BEAT_RIVAL_IN_OAKS_LAB"), "should have beaten the lab rival"

    party = get_party()
    assert party[0].species.name == "Squirtle"
    assert party[0].current_hp > 0

    assert get_item_bag().quantity_of(get_item_by_name("Poké Ball")) >= 10
