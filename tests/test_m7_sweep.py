"""M7-era planner sweep: Cerulean/Vermilion-area species caught unattended.

Regenerate: python -m dexbot.planner m7_hm_cut.ss1 m7_cerulean_sweep.ss1
(the sweep fixture is updated in place by later sweeps — assert progress,
not an exact species list).
"""

from dexbot import PROJECT_ROOT


def test_sweep_progress():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_cerulean_sweep.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.pokedex import get_pokedex
    from modules.pokemon_party import get_party

    owned = {s.name for s in get_pokedex().owned_species}
    assert len(owned) >= 19
    assert {"Abra", "Meowth", "Oddish", "Ekans"} <= owned
    assert get_party().has_pokemon_with_move("Cut")  # the HM mule stayed aboard
    assert any(p.current_hp > 0 for p in get_party())


def test_post_surge_sweep_progress():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m7_post_surge_sweep.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.pokedex import get_pokedex
    from modules.pokemon_party import get_party

    owned = {s.name for s in get_pokedex().owned_species}
    assert len(owned) >= 23
    assert {"Diglett", "Drowzee", "Dugtrio", "Blastoise"} <= owned
    assert get_party().has_pokemon_with_move("Cut")
