"""M5 acceptance: five named early-route species caught unattended.

Regenerate the fixture with: python -m dexbot.catching (from m4_pokedex.ss1).
"""

from dexbot import PROJECT_ROOT


def test_five_species_caught():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m5_five_species.ss1").read_bytes())
    context.emulator.run_single_frame()

    from modules.pokedex import get_pokedex

    owned = {s.name for s in get_pokedex().owned_species}
    assert {"Rattata", "Pidgey", "Caterpie", "Weedle", "Pikachu"} <= owned


def test_kb_best_encounter_map():
    from dexbot.kb import best_encounter_map

    assert best_encounter_map("Caterpie") == ((1, 0), 40)  # Viridian Forest
    assert best_encounter_map("Mankey")[1] == 45  # Route 22
