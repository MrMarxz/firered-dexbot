"""M0 acceptance: emulator boots FireRed and the title-screen fixture is genuine."""

from dexbot import PROJECT_ROOT


def test_title_screen_fixture():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m0_title.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import GameState, get_game_state

    assert "FireRed" in context.rom.game_name
    assert get_game_state() == GameState.TITLE_SCREEN
