"""M7 badge 8: Giovanni beaten unattended (spinner maze, Water sweep).

Regenerate: python -m dexbot.gyms giovanni m7_badge_blaine.ss1
"""

from dexbot import PROJECT_ROOT


def test_giovanni_defeated():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_badge_giovanni.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert all(get_event_flag(f"BADGE0{i}_GET") for i in range(1, 9))
    assert any(p.current_hp > 0 for p in get_party())
