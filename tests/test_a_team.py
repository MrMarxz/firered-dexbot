"""Sub-project A: roster enumeration + PC assembly.

Fixture a_team_solo.ss1: the living-dex profile mid-run — solo Blastoise + Cut
mule (Paras) in party, diverse mons incl. Cubone L15 in boxes. Captured from
pokebot-gen3/profiles/livingdex/current_state.ss1.
"""

import pytest

from dexbot import PROJECT_ROOT

FIXTURE = "a_team_solo.ss1"

pytestmark = pytest.mark.skipif(
    not (PROJECT_ROOT / "fixtures" / FIXTURE).exists(),
    reason="a_team_solo.ss1 not captured",
)


def _load():
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / FIXTURE).read_bytes())
    context.emulator.run_single_frame()
    return context


def test_enumerate_roster_reads_party_and_boxes():
    _load()
    from dexbot.team import enumerate_roster

    roster = enumerate_roster()
    names = {m.species_name for m in roster}
    assert "Blastoise" in names
    assert "Cubone" in names  # the future False Swipe user
    assert any(m.location == "party" for m in roster)
    assert any(m.location.startswith("box:") for m in roster)
    blastoise = next(m for m in roster if m.species_name == "Blastoise")
    assert blastoise.level > 0 and blastoise.types and isinstance(blastoise.moves, tuple)


def test_assemble_party_realizes_selection():
    context = _load()
    from dexbot.catching import fight_all_battles
    from dexbot.runner import run_skill
    from dexbot.team import TeamObjective, assemble_party, enumerate_roster, select_party

    obj = TeamObjective(kind="catch", field_moves=("Cut",))
    target = {m.id_bytes for m in select_party(obj, enumerate_roster())}
    run_skill(assemble_party(obj), "assemble", timeout_frames=400_000, on_battle_started=fight_all_battles)

    from modules.pokemon_party import get_party

    party_ids = {bytes(p.data[:4]) for p in get_party() if not p.is_egg}
    assert party_ids == target
    assert get_party().has_pokemon_with_move("Cut")  # mule retained
