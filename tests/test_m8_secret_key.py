"""M8: Pokémon Mansion Secret Key obtained (statue-switch maze, B1F).

Regenerate: python -m dexbot.story get_secret_key <fixture> m8_secret_key.ss1
"""

from dexbot import PROJECT_ROOT


def test_secret_key_obtained():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m8_secret_key.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.items import get_item_bag, get_item_by_name
    from modules.memory import get_event_flag

    assert get_event_flag("HIDE_POKEMON_MANSION_B1F_SECRET_KEY")
    assert get_item_bag().quantity_of(get_item_by_name("Secret Key")) == 1
