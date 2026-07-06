"""M3 acceptance: warp-spanning navigate_to.

Current test: bedroom -> Oak's lab (2 maps of interior, 1 town, 3 warps incl. an
FRLG diagonal stair warp and door warps). The brief's Pallet Town -> Viridian
Mart test is added once M4 produces a post-Oak's-lab savestate (pre-starter,
walking towards Route 1 triggers the Oak cutscene).
"""

from dexbot import PROJECT_ROOT


def test_navigate_pallet_town_to_viridian_mart():
    """The brief's M3 acceptance: post-Oak's-lab state, walk to the Viridian Mart."""
    from dexbot.emulator import setup_headless_emulator
    from dexbot.navigation import navigate_to
    from dexbot.runner import run_skill

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m4_post_lab.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.map_data import MapFRLG
    from modules.player import get_player_avatar

    run_skill(navigate_to(MapFRLG.VIRIDIAN_CITY_MART, (4, 3)), "test_nav_viridian_mart", timeout_frames=40_000)

    avatar = get_player_avatar()
    assert avatar.map_group_and_number == (5, 3)  # VIRIDIAN_CITY_MART
    assert avatar.local_coordinates == (4, 3)


def test_navigate_bedroom_to_oaks_lab():
    from dexbot.emulator import setup_headless_emulator
    from dexbot.navigation import navigate_to
    from dexbot.runner import run_skill

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m1_game_start.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.map_data import MapFRLG
    from modules.player import get_player_avatar

    run_skill(navigate_to(MapFRLG.PALLET_TOWN_PROFESSOR_OAKS_LAB, (6, 10)), "test_nav_oaks_lab", timeout_frames=5000)

    avatar = get_player_avatar()
    assert avatar.map_group_and_number == (4, 3)  # PALLET_TOWN_PROFESSOR_OAKS_LAB
    assert avatar.local_coordinates == (6, 10)
