"""M7 acceptance (badge 1 sub-milestone): Brock beaten unattended.

Regenerate the fixture with: python -m dexbot.gyms brock (from m6_pre_brock_dex.ss1).
"""

from dexbot import PROJECT_ROOT


def test_brock_defeated():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_badge_brock.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    assert get_event_flag("BADGE01_GET")
    assert any(p.current_hp > 0 for p in get_party())  # did not white out


def test_badge_unlocks_more_maps():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_badge_brock.ss1").read_bytes())
    context.emulator.run_single_frame()

    from dexbot.planner import accessible_maps, missing_catchable

    maps = accessible_maps()
    assert (3, 21) in maps  # Route 3
    assert (1, 1) in maps  # Mt Moon 1F

    new_targets = {species for species, *_ in missing_catchable()}
    # Ekans (Route 4 east) additionally needs the Mt Moon fossil gate cleared.
    assert {"Nidoran♂", "Jigglypuff", "Zubat", "Geodude", "Paras", "Clefairy"} <= new_targets
    assert "Ekans" not in new_targets
