"""M7 badge 5: Koga beaten unattended (invisible-wall maze is real collision).

Regenerate: python -m dexbot.gyms koga m8_post_snorlax.ss1
"""

from dexbot import PROJECT_ROOT


def test_koga_defeated():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_badge_koga.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert get_event_flag("BADGE05_GET")
    assert get_event_flag("BADGE04_GET")
    assert any(p.current_hp > 0 for p in get_party())
