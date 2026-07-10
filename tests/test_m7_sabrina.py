"""M7 badge 6: Sabrina beaten unattended (teleporter maze via the warp graph).

Regenerate: python -m dexbot.gyms sabrina m8_silph.ss1
"""

from dexbot import PROJECT_ROOT


def test_sabrina_defeated():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_badge_sabrina.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert get_event_flag("BADGE06_GET")
    assert get_event_flag("BADGE05_GET")
    assert any(p.current_hp > 0 for p in get_party())
