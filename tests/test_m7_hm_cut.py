"""M7 story: HM01 Cut obtained from the S.S. Anne Captain and taught.

Regenerate: python -m dexbot.story get_hm_cut m7_badge_misty.ss1 m7_hm_cut.ss1
"""

from dexbot import PROJECT_ROOT


def test_hm_cut_obtained_and_taught():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_hm_cut.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert get_event_flag("GOT_HM01")
    assert get_party().has_pokemon_with_move("Cut")
    assert get_event_flag("BADGE02_GET")  # Cascade Badge — Cut is usable
    assert any(p.current_hp > 0 for p in get_party())  # survived the ship gauntlet
