"""M7 badge 2: Misty beaten unattended.

Regenerate: python -m dexbot.gyms misty m7_ss_ticket.ss1
"""

from dexbot import PROJECT_ROOT


def test_misty_defeated():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_badge_misty.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert get_event_flag("BADGE02_GET")
    assert get_event_flag("BADGE01_GET")  # didn't lose earlier progress
    assert any(p.current_hp > 0 for p in get_party())
