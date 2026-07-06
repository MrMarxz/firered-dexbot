"""M6 acceptance: deterministic planner completes the pre-Brock dex."""

from dexbot import PROJECT_ROOT

PRE_BROCK_SPECIES = {
    "Rattata",
    "Pidgey",
    "Caterpie",
    "Weedle",
    "Metapod",
    "Kakuna",
    "Pikachu",
    "Mankey",
    "Spearow",
}


def test_planner_queue_covers_pre_brock_species():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m4_pokedex.ss1").read_bytes())
    context.emulator.run_single_frame()

    from dexbot.planner import missing_catchable

    queue = missing_catchable()
    assert {species for species, *_ in queue} == PRE_BROCK_SPECIES
    # deterministic: most common first
    rates = [rate for _, _, rate, _ in queue]
    assert rates == sorted(rates, reverse=True)


def test_pre_brock_dex_complete():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m6_pre_brock_dex.ss1").read_bytes())
    context.emulator.run_single_frame()

    from dexbot.planner import missing_catchable
    from modules.pokedex import get_pokedex

    owned = {s.name for s in get_pokedex().owned_species}
    assert PRE_BROCK_SPECIES <= owned
    assert missing_catchable() == []  # queue is drained
