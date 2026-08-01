"""council_dryrun.py — grade the council on a historical stall, offline.

Given a stall savestate and a SCRUBBED name (see tools/README.md — original
stall filenames leak the previous owner's diagnosis), this:

  1. copies the savestate into a fresh temp workspace under the scrubbed name
     (the original path/filename never reaches the council);
  2. decodes a state summary from it with this repo's own emulator harness
     (same pattern as the test suite: load state, run one frame, capture);
  3. SYNTHESIZES the watchdog telemetry the live system always provides — a
     skills.jsonl tail in the live emission format (stall / error / deferred
     records exactly as dexbot-run's runner and planner journal them), with
     the interrupted-skill label scrubbed to the opaque name but the sample,
     script stack, and frame budget read from the loaded savestate the way
     run_skill reads them live (remediation for the Phase 1 exam misses:
     every miss was a live-controller freeze diagnosed WITHOUT the telemetry
     a live council would have had);
  4. generates the SAME event invocation the supervisor would generate for a
     watchdog stall — imported from dexbot-run's supervisor, not re-templated;
  5. invokes the orchestrator in dexbot-run in DIAGNOSE-ONLY mode: Seat A
     classification + Seat B root-cause and proposed fix, nothing implemented,
     logged to COUNCIL_LOG.dryrun.md (never the live record files).

Usage (from this repo's root, human-operated):
    .venv\\Scripts\\python.exe tools\\council_dryrun.py <savestate.ss1> <scrubbed-name>
        [--run-repo ..\\dexbot-run] [--no-invoke]
        [--prior <earlier.ss1> ...] [--defer-event | --no-defer-event]

`--no-invoke` stops after generating the invocation (printed + saved) — useful
to inspect what the council would be told.
`--prior` (repeatable, oldest first) takes EARLIER stall dumps of the same
objective; each becomes one synthesized stall/error[/deferred] cycle before
the target's, so the tail carries the objective's real defer/retry history.
`--defer-event/--no-defer-event` controls whether each cycle ends in the
planner's status="deferred" record; the default is derived from the original
filename's skill label (only the catch loop journals defers — story/nav/
patrol call sites swallow the SkillError without a defer record).
"""

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("DEXBOT_VIDEO", "0")
sys.path.insert(0, str(REPO))

# Fields the LIVE _dump_stall records since dexbot-run's DRYRUN-003 commit
# (controller_stack / held_buttons / nav_intent). They capture live Python
# process state that a savestate does not carry, and every holdout dump
# predates the enrichment — so the synthesized tail matches the emission
# format of the watchdog that actually dumped the stall and omits them.
# tests/test_council_dryrun_telemetry.py asserts the delta between the live
# stall record and the synthesized one is EXACTLY this set, so any future
# live-format change forces an explicit fidelity decision here.
LIVE_ONLY_STALL_FIELDS = ("controller_stack", "held_buttons", "nav_intent")


def decode_summary(savestate: Path) -> dict:
    """Decode the savestate with the existing emulator harness (tests' pattern)."""
    try:
        import dexbot  # noqa: F401 — sys.path + libmgba bootstrap
        from dexbot.emulator import setup_headless_emulator
        from dexbot.telemetry import capture_state

        context = setup_headless_emulator(is_test_run=True)
        context.emulator.load_save_state(savestate.read_bytes())
        context.emulator.run_single_frame()
        return capture_state()
    except Exception as error:  # decode failure is evidence too, not a crash
        return {"decode_error": f"{type(error).__name__}: {error}"}


def load_supervisor_module(run_repo: Path):
    spec = importlib.util.spec_from_file_location(
        "dexbot_run_supervisor", run_repo / "supervisor" / "supervisor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_runner_module(run_repo: Path):
    """dexbot-run's dexbot/runner.py, loaded standalone: the synthesized tail
    is sampled by the run repo's own _progress_sample, priced by its own
    budget constants, and written by its own _log_event — so the tail's
    format tracks the code that emits live telemetry, not a re-template."""
    spec = importlib.util.spec_from_file_location(
        "dexbot_run_runner", run_repo / "dexbot" / "runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stall_budget(runner, game_state) -> int:
    """Mirror run_skill's budget branch: menu wedges trip the small budget,
    overworld/battle states the big one."""
    from modules.memory import GameState

    overworld_like = game_state in (
        GameState.OVERWORLD,
        GameState.BATTLE,
        GameState.BATTLE_STARTING,
        GameState.BATTLE_ENDING,
        GameState.CHANGE_MAP,
    )
    return runner._PROGRESS_BUDGET_FRAMES if overworld_like else runner._MENU_PROGRESS_BUDGET_FRAMES


def _stall_readouts(runner) -> dict:
    """Sample / script stack / frame budget for the CURRENTLY LOADED emulator
    state, read exactly the way run_skill and _dump_stall read them live."""
    from modules.memory import get_game_state
    from modules.tasks import get_global_script_context

    sample = runner._progress_sample()
    script = get_global_script_context()
    return {
        "sample": sample,
        "script": script.stack if script is not None and script.is_active else [],
        "budget": _stall_budget(runner, get_game_state()),
    }


def watchdog_tail_events(scrubbed: str, readouts: dict, state_path: str,
                         defer_event: bool) -> list[dict]:
    """One stall cycle as the live system journals it, label scrubbed.

    Field structure mirrors dexbot-run's emission sites record for record:
      - stall:    dexbot/runner.py _dump_stall's _log_event (minus the
                  LIVE_ONLY_STALL_FIELDS, which these historical dumps predate)
      - error:    dexbot/runner.py run_skill's standstill SkillError, logged by
                  its except-path _log_event (the pacing detector's variant
                  text is not reconstructible from a single artifact)
      - deferred: dexbot/planner.py plan_and_catch_all's failure boundary
                  (catch objectives only — hence defer_event)
    tests/test_council_dryrun_telemetry.py locks this against the real emitters.
    """
    sample = readouts["sample"]
    error_text = (
        f"Skill {scrubbed!r} made no observable progress for "
        f"{readouts['budget']} frames at {sample[:2] if sample else '?'} "
        f"(stall state: {state_path})"
    )
    events = [
        {"skill": scrubbed, "status": "stall", "sample": repr(sample),
         "script": readouts["script"], "state": state_path},
        {"skill": scrubbed, "status": "error", "error": error_text},
    ]
    if defer_event:
        events.append({"skill": scrubbed, "status": "deferred", "error": error_text})
    return events


def write_tail(runner, events: list[dict], tail_path: Path) -> None:
    """Emit the synthesized records through the run repo's own _log_event
    (redirected to the workspace), so the outer line format — time-first key
    order, json.dumps, one record per line — is the live code's, not ours."""
    runner._events_path = tail_path
    for event in events:
        runner._log_event(**event)


DIAGNOSE_ONLY_PREAMBLE = """DRY-RUN — DIAGNOSE-ONLY MODE (council grading harness, human-operated).

This is a rehearsal on a historical stall savestate, NOT a live event. Rules
for this invocation (they narrow, and never override, COUNCIL_PROTOCOL.md):
- Convene ALL THREE seats per protocol: Seat A (classification, severity,
  blast radius), Seat B (root cause + proposed fix, with alternatives
  considered and rejected in writing), and Seat C (Codex over MCP — ONE
  thread for the whole event, threadId recorded in the log entry, the
  continuation tool for every subsequent turn), with sources cited per
  protocol section 5.
- Seat model discipline (protocol sections 3 and 11): spawn each Claude seat
  passing the model EXPLICITLY as the full ID from the section 3 table —
  Seat A claude-sonnet-5, Seat B claude-opus-5 (default) — never a bare
  alias like "opus" (aliases have resolved to non-section-3 models in this
  harness). If the spawn interface rejects a full ID, use the closest alias,
  then check the sub-agent's self-reported model against section 3 and treat
  a mismatch as section 11 requires: redo with correct occupancy, or, if no
  spawn parameter can produce the section-3 model, record the violation
  prominently in the Model check lines.
- Telemetry fidelity: the evidence includes a skills.jsonl tail SYNTHESIZED
  by this harness from the stall artifact(s), in the live watchdog's exact
  emission format (stall / error / deferred records as dexbot/runner.py and
  dexbot/planner.py journal them; the sample tuple, script stack, and frame
  budget are read from the loaded savestate the same way run_skill reads
  them live). The interrupted-skill label is scrubbed to the opaque
  objective name; timestamps are synthesis-time, not historical. Records
  predating the stall window (start/phase/whiteout/other objectives'
  telemetry) are not reconstructible from the artifact and are ABSENT —
  treat their absence as unknown, not as evidence those events did not
  occur. These historical dumps also predate _dump_stall's
  controller_stack/held_buttons/nav_intent enrichment, so the stall records
  lack those fields.
- IMPLEMENT NOTHING: no code edits, no data/ edits, no config changes, no
  commits, no PARKED routing. The proposed fix stays a written proposal.
  Because nothing is implemented, section 9's replay/regression evidence
  gate is inapplicable: Seat C instead judges the WRITTEN PROPOSAL —
  classification soundness, citation quality (section 5), diagnosis-to-fix
  coherence, alternatives — and renders PASS / FAIL / PASS-WITH-CONCERNS on
  the proposal. The section 3 cross-model gate applies to this judgment.
- Diagnostic reproductions (headless) are allowed, but leave the repository
  AND the emulator profile state exactly as found; if a tool writes anywhere
  (e.g. pokebot-gen3/profiles/), restore it and disclose the side effect in
  the log entry.
- Log the event to COUNCIL_LOG.dryrun.md (create it beside COUNCIL_LOG.md if
  missing, same entry format, event ids prefixed DRYRUN-). Do NOT write
  STATE.md, COUNCIL_LOG.md, FINDINGS.md, DECISIONS.md, or PARKED.md.
- There is no bot process to pause or resume.
- The objective name in this invocation was deliberately scrubbed. Do not try
  to recover or guess the original filename; diagnose from the savestate, the
  synthesized telemetry, the decoded summary, and the repository alone.

The supervisor-identical event invocation follows.
--------------------------------------------------------------------------
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("savestate", type=Path)
    parser.add_argument("scrubbed_name")
    parser.add_argument("--run-repo", type=Path, default=REPO.parent / "dexbot-run")
    parser.add_argument("--no-invoke", action="store_true")
    parser.add_argument("--prior", action="append", type=Path, default=[],
                        help="earlier stall dump(s) of the SAME objective, oldest first; "
                             "each adds one synthesized cycle of defer history to the tail")
    parser.add_argument("--defer-event", dest="defer_event", action="store_true", default=None,
                        help="end each cycle with the planner's status=deferred record "
                             "(default: derived from the original filename's skill label)")
    parser.add_argument("--no-defer-event", dest="defer_event", action="store_false")
    args = parser.parse_args()

    savestate = args.savestate.resolve()
    run_repo = args.run_repo.resolve()
    if not savestate.is_file():
        sys.exit(f"savestate not found: {savestate}")
    if not (run_repo / "COUNCIL_PROTOCOL.md").is_file():
        sys.exit(f"{run_repo} does not look like the experiment repo (no COUNCIL_PROTOCOL.md)")
    scrubbed = args.scrubbed_name.removesuffix(".ss1")
    if scrubbed in savestate.stem:
        print(f"WARNING: scrubbed name {scrubbed!r} appears in the source filename "
              f"{savestate.name!r} — that defeats scrubbing. See tools/README.md.")
    if args.defer_event is None:
        # Only the planner's catch loop journals a status="deferred" record;
        # story/nav/patrol call sites swallow the SkillError without one.
        original_label = re.sub(r"_\d{6}$", "", savestate.stem)
        args.defer_event = original_label.startswith("catch_")
        print(f"[dryrun] defer-event {'ON' if args.defer_event else 'OFF'} (derived from the "
              f"original label's call-site class; --defer-event/--no-defer-event overrides)")

    workspace = Path(tempfile.mkdtemp(prefix=f"council_dryrun_{scrubbed}_"))
    state_copy = workspace / f"{scrubbed}.ss1"
    shutil.copyfile(savestate, state_copy)

    print(f"[dryrun] decoding state summary (headless emulator)...")
    summary = decode_summary(state_copy)
    summary_path = workspace / f"{scrubbed}_state.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"[dryrun] summary: game_state={summary.get('game_state', '?')} "
          f"map=({summary.get('map_group', '?')},{summary.get('map_number', '?')}) "
          f"coords={summary.get('coords', '?')}")
    if "decode_error" in summary:
        sys.exit(f"[dryrun] decode failed ({summary['decode_error']}) — cannot synthesize the "
                 f"live-fidelity watchdog tail; the exam should not run on this artifact")

    runner = load_runner_module(run_repo)
    from modules.context import context  # the live singleton decode_summary booted

    tail_events: list[dict] = []
    prior_copies: list[str] = []
    for index, prior in enumerate(args.prior, start=1):
        prior = prior.resolve()
        if not prior.is_file():
            sys.exit(f"--prior not found: {prior}")
        if scrubbed in prior.stem:
            print(f"WARNING: scrubbed name {scrubbed!r} appears in --prior {prior.name!r}")
        prior_copy = workspace / f"{scrubbed}_prior{index}.ss1"
        shutil.copyfile(prior, prior_copy)
        context.emulator.load_save_state(prior_copy.read_bytes())
        context.emulator.run_single_frame()
        tail_events += watchdog_tail_events(
            scrubbed, _stall_readouts(runner), str(prior_copy), args.defer_event)
        prior_copies.append(str(prior_copy))
    if args.prior:  # reload the target: priors displaced it in the emulator
        context.emulator.load_save_state(state_copy.read_bytes())
        context.emulator.run_single_frame()

    target_readouts = _stall_readouts(runner)
    tail_events += watchdog_tail_events(
        scrubbed, target_readouts, str(state_copy), args.defer_event)
    tail_path = workspace / "skills.jsonl"
    write_tail(runner, tail_events, tail_path)
    print(f"[dryrun] synthesized watchdog tail: {len(tail_events)} records "
          f"({len(args.prior)} prior cycle(s)) -> {tail_path}")

    supervisor = load_supervisor_module(run_repo)
    trigger = {
        "type": "watchdog_stall",
        "objective": scrubbed,
        # Live shape (supervisor.Watcher): detail carries the stall record's
        # sample repr; evidence leads with [state, skills.jsonl].
        "detail": f"runner watchdog dumped a stall for {scrubbed!r} (§4.1): "
                  f"{repr(target_readouts['sample'])} "
                  f"[dry-run: historical savestate, scrubbed name]",
        "evidence": [str(state_copy), str(tail_path), str(summary_path)] + prior_copies,
    }
    prompt = DIAGNOSE_ONLY_PREAMBLE + supervisor.council_prompt(trigger)
    (workspace / "invocation.txt").write_text(prompt, encoding="utf-8")
    print(f"[dryrun] workspace: {workspace}")
    if args.no_invoke:
        print("[dryrun] --no-invoke: invocation written, orchestrator not started")
        return 0

    argv = supervisor.claude_argv(prompt)  # same resolution + DEXBOT_CLAUDE_ARGS as live
    print(f"[dryrun] invoking orchestrator in {run_repo} ...")
    started = time.time()
    result = subprocess.run(argv, cwd=run_repo, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    transcript = workspace / "orchestrator_output.txt"
    transcript.write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
    print(f"[dryrun] orchestrator exited rc={result.returncode} "
          f"after {time.time() - started:.0f}s; output -> {transcript}")
    print(f"[dryrun] check {run_repo / 'COUNCIL_LOG.dryrun.md'} for the logged diagnosis")
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
