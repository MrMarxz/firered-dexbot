"""Sub-project A Task 4: planner fields a catch team, not a solo lead."""

import pytest
from pathlib import Path

from dexbot import PROJECT_ROOT

pytestmark = pytest.mark.skipif(
    not (PROJECT_ROOT / "fixtures" / "a_team_solo.ss1").exists(),
    reason="needs a_team_solo.ss1",
)


def test_planner_assembles_catch_team_not_solo():
    """The catch objective now fields a diverse party (>=2 mons, includes the
    Cut mule and a sleep user), leaving a slot for the catch — not a solo lead."""
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "a_team_solo.ss1").read_bytes())
    context.emulator.run_single_frame()

    from dexbot.team import SLEEP_MOVES, TeamObjective, enumerate_roster, select_party

    picked = select_party(TeamObjective(kind="catch", field_moves=("Cut",)), enumerate_roster())
    assert 2 <= len(picked) <= 5  # diverse, and one slot left free for the catch
    assert any("Cut" in m.moves for m in picked)  # HM mule aboard
    assert any(any(mv in SLEEP_MOVES for mv in m.moves) for m in picked)  # sleep user aboard
