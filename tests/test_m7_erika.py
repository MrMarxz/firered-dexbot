"""M7 badge 4: Erika beaten unattended (interior hedge cut + level lead).

Regenerate: python -m dexbot.gyms erika m7_tea.ss1
"""

from dexbot import PROJECT_ROOT


def test_erika_defeated():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_badge_erika.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert get_event_flag("BADGE04_GET")
    assert get_event_flag("BADGE03_GET")
    assert get_event_flag("GOT_TEA")  # Saffron routing stays open
    assert get_party().has_pokemon_with_move("Cut")
    assert any(p.current_hp > 0 for p in get_party())
