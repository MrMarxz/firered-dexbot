"""Badge-2 chain: Nugget Bridge cleared unattended (rival + 5 trainers + Rocket).

Regenerate: python -m dexbot.story cross_nugget_bridge m7_post_badge1_dex.ss1 m7_bridge.ss1
"""

from dexbot import PROJECT_ROOT


def test_nugget_bridge_cleared():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_bridge.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.items import get_item_bag, get_item_by_name
    from modules.memory import get_event_var
    from modules.pokemon_party import get_party

    assert get_event_var("MAP_SCENE_ROUTE24") >= 1  # Rocket recruiter defeated
    assert get_item_bag().quantity_of(get_item_by_name("Nugget")) >= 1  # his reward
    assert any(p.current_hp > 0 for p in get_party())  # survived the gauntlet
