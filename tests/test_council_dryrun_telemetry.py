"""Synthesized watchdog tail (tools/council_dryrun.py) vs the REAL emitters.

The Phase 1 exam remediation: the dry-run must hand the council a
skills.jsonl tail in the live emission format. These tests lock the
synthesis against dexbot-run's actual code — the stall record against a real
_dump_stall call, the error/deferred records and budget branch against the
run repo's source — so run-repo drift breaks a test here instead of silently
degrading exam fidelity.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUN_REPO = REPO.parent / "dexbot-run"

pytestmark = pytest.mark.skipif(
    not (RUN_REPO / "dexbot" / "runner.py").is_file(),
    reason="dexbot-run sibling repo not present",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cd():
    return _load("council_dryrun_under_test", REPO / "tools" / "council_dryrun.py")


@pytest.fixture(scope="module")
def runner(cd):
    return cd.load_runner_module(RUN_REPO)


SAMPLE = ((1, 41), (33, 19), 38024, 7, 21, 80, (154, 60, 110, 90, 105, 64))
SCRIPT_STACK = ["EventScript_Stub"]


class _FakeEmulator:
    def get_save_state(self):
        return b"\x00stub"

    def get_screenshot(self):
        raise RuntimeError("headless")

    def is_button_held(self, button=None):
        return button == "Down"


def _gen():
    yield


def _real_stall_record(runner, monkeypatch, tmp_path) -> dict:
    """Drive dexbot-run's actual _dump_stall and return the journal record."""
    import modules.tasks
    from modules.context import context

    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    (tmp_path / "fixtures").mkdir(exist_ok=True)
    monkeypatch.setattr(runner, "_events_path", tmp_path / "real_skills.jsonl")
    monkeypatch.setattr(context, "emulator", _FakeEmulator())
    monkeypatch.setattr(context, "controller_stack", [_gen()])

    class _Script:
        is_active = True
        stack = SCRIPT_STACK

    monkeypatch.setattr(modules.tasks, "get_global_script_context", lambda: _Script())
    runner._dump_stall("stall_t", SAMPLE)
    return json.loads((tmp_path / "real_skills.jsonl").read_text().splitlines()[-1])


def _synth_records(cd, runner, tmp_path, defer_event=True, sample=SAMPLE) -> list[dict]:
    events = cd.watchdog_tail_events(
        "stall_t",
        {"sample": sample, "script": SCRIPT_STACK, "budget": runner._PROGRESS_BUDGET_FRAMES},
        str(tmp_path / "stall_t.ss1"),
        defer_event,
    )
    tail = tmp_path / "synth_skills.jsonl"
    cd.write_tail(runner, events, tail)
    return [json.loads(line) for line in tail.read_text().splitlines()]


def test_stall_record_matches_live_dump_stall(cd, runner, monkeypatch, tmp_path):
    real = _real_stall_record(runner, monkeypatch, tmp_path)
    synth = _synth_records(cd, runner, tmp_path)[0]

    # The only fields the synthesis may omit are the live-process-state ones
    # the historical dumps predate — exactly LIVE_ONLY_STALL_FIELDS. A new
    # field in the live record makes this fail and forces a fidelity decision.
    assert set(real) - set(synth) == set(cd.LIVE_ONLY_STALL_FIELDS)
    assert set(synth) - set(real) == set()
    # Key order is part of the format (json.dumps preserves insertion order).
    assert [k for k in real if k not in cd.LIVE_ONLY_STALL_FIELDS] == list(synth)

    assert synth["skill"] == real["skill"] == "stall_t"
    assert synth["status"] == real["status"] == "stall"
    assert synth["sample"] == real["sample"] == repr(SAMPLE)
    assert synth["script"] == real["script"] == SCRIPT_STACK
    assert synth["state"].endswith(".ss1") and real["state"].endswith(".ss1")
    assert isinstance(synth["time"], float)


def test_error_and_deferred_records_match_live_shape(cd, runner, tmp_path):
    records = _synth_records(cd, runner, tmp_path)
    assert [r["status"] for r in records] == ["stall", "error", "deferred"]
    stall, error, deferred = records

    # run_skill logs the standstill SkillError as {skill, status, error}.
    assert list(error) == ["time", "skill", "status", "error"]
    budget = runner._PROGRESS_BUDGET_FRAMES
    assert error["error"] == (
        f"Skill 'stall_t' made no observable progress for {budget} frames "
        f"at {SAMPLE[:2]} (stall state: {stall['state']})"
    )
    # The live raise's template fragments must still exist in the run repo —
    # if run_skill's message changes, the synthesis must follow.
    src = (RUN_REPO / "dexbot" / "runner.py").read_text(encoding="utf-8")
    assert "made no observable progress for " in src
    assert "(stall state: {state_path})" in src
    assert "{sample[:2] if sample else '?'} " in src

    # planner.py's failure boundary logs {skill, status=deferred, error}.
    assert list(deferred) == ["time", "skill", "status", "error"]
    assert deferred["error"] == error["error"]
    planner_src = (RUN_REPO / "dexbot" / "planner.py").read_text(encoding="utf-8")
    assert 'status="deferred", error=str(e)' in planner_src


def test_defer_event_off_omits_planner_record(cd, runner, tmp_path):
    # Story/nav/patrol call sites swallow the SkillError without journaling a
    # defer — the tail for those objectives must end at the error record.
    records = _synth_records(cd, runner, tmp_path, defer_event=False)
    assert [r["status"] for r in records] == ["stall", "error"]


def test_none_sample_mirrors_live_fallbacks(cd, runner, tmp_path):
    # _progress_sample returns None when its reads fail; live emission then
    # journals sample=repr(None) and formats the location as '?'.
    records = _synth_records(cd, runner, tmp_path, sample=None)
    assert records[0]["sample"] == "None"
    assert " at ? (stall state: " in records[1]["error"]


def test_budget_branch_matches_live_run_skill(cd, runner):
    from modules.memory import GameState

    for state in (GameState.OVERWORLD, GameState.BATTLE, GameState.BATTLE_STARTING,
                  GameState.BATTLE_ENDING, GameState.CHANGE_MAP):
        assert cd._stall_budget(runner, state) == runner._PROGRESS_BUDGET_FRAMES
    menu_states = [s for s in GameState if cd._stall_budget(runner, s) != runner._PROGRESS_BUDGET_FRAMES]
    assert menu_states, "expected at least one menu-budget state"
    for state in menu_states:
        assert cd._stall_budget(runner, state) == runner._MENU_PROGRESS_BUDGET_FRAMES
    # Tripwire: the five big-budget states must still be the ones run_skill names.
    src = (RUN_REPO / "dexbot" / "runner.py").read_text(encoding="utf-8")
    for name in ("GameState.OVERWORLD", "GameState.BATTLE,", "GameState.BATTLE_STARTING",
                 "GameState.BATTLE_ENDING", "GameState.CHANGE_MAP"):
        assert name in src
