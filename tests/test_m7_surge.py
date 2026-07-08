"""M7 badge 3: Lt. Surge beaten unattended (cut tree, memory-read trash-can
puzzle, beam-door crossing, potion-funded fight).

Regenerate: python -m dexbot.gyms surge m7_cerulean_sweep.ss1
"""

from dexbot import PROJECT_ROOT


def test_surge_defeated():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_badge_surge.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert get_event_flag("BADGE03_GET")
    assert get_event_flag("BADGE02_GET")  # didn't lose earlier progress
    assert get_party().has_pokemon_with_move("Cut")  # mule still aboard
    assert any(p.current_hp > 0 for p in get_party())
