# tools — human-operated harness utilities

## council_dryrun.py — grading the council before the live run

Feeds a historical stall savestate to the dexbot-run council in
**diagnose-only** mode: Seat A classifies, Seat B proposes a root cause and
fix, nothing is implemented, and the event is logged to
`COUNCIL_LOG.dryrun.md` in dexbot-run (never the live record files). Compare
the logged diagnosis against what you know actually caused the stall to grade
the council.

```
.venv\Scripts\python.exe tools\council_dryrun.py <path\to\savestate.ss1> <scrubbed-name>
```

Options: `--run-repo <path>` if dexbot-run is not the sibling directory;
`--no-invoke` to only generate and inspect the invocation. The orchestrator
invocation honors the same `DEXBOT_CLAUDE_ARGS` environment variable as the
supervisor (see dexbot-run/supervisor/README.md).

Everything the council sees lands in a fresh temp workspace
(`%TEMP%\council_dryrun_<name>_*`): the renamed savestate copy, the decoded
state summary JSON, the synthesized skills.jsonl tail, the exact invocation
text, and the orchestrator's output.

### Synthesized watchdog tail (Phase 1 exam remediation)

The live supervisor always hands the council `logs/skills.jsonl`; the first
exam withheld it, and every root-cause miss was a live-controller freeze
diagnosed without that telemetry. The tool now synthesizes a `skills.jsonl`
tail in the live emission format — the `stall` record (sample tuple, script
stack, state path) as `_dump_stall` journals it, the `error` record as
`run_skill`'s standstill SkillError logs it, and (for catch-loop objectives)
the planner's `deferred` record. Sample/script/budget are read from the
loaded savestate exactly the way `run_skill` reads them live; only the skill
label is scrubbed. The emission is produced by dexbot-run's own
`_log_event`, and `tests/test_council_dryrun_telemetry.py` locks the format
against the run repo's real emitters. Historical dumps predate dexbot-run's
DRYRUN-003 `_dump_stall` enrichment, so the synthesized stall record
deliberately omits `controller_stack`/`held_buttons`/`nav_intent` (disclosed
to the council in the preamble).

- `--prior <earlier.ss1>` (repeatable, oldest first): earlier dumps of the
  SAME objective; each adds one synthesized stall/error[/deferred] cycle
  before the target's, so the tail carries the objective's real defer/retry
  history (samples decoded from each prior state — money/position over time
  is real evidence).
- `--defer-event` / `--no-defer-event`: force or suppress the planner's
  `status="deferred"` record. Default is derived from the original
  filename's label: only the catch loop journals defers; story/nav/patrol
  call sites swallow the SkillError without one.

### Scrub filenames BEFORE feeding holdout stalls — this is the whole point

The holdout stall files are named by the code path that dumped them —
`vs_seeker_leg_143512.ss1`, `assemble_party_091203.ss1`,
`evolve_stones_120455.ss1` — i.e. **the filename IS the previous owner's
diagnosis**. Hand the council a file named `vs_seeker_leg_*.ss1` and you've
told it the answer; the dry run then measures nothing.

Procedure:

1. Pick the holdout pair (`.ss1` + `.png` sidecar) you want to test. Note the
   original name in YOUR private grading sheet (outside both repos), because
   it is the answer key.
2. Choose an opaque scrubbed name that carries zero gameplay vocabulary:
   `stall_A`, `stall_B`, `stall_2026_07_31_case1`. Never reuse any part of
   the original name — no skill words (`vs_seeker`, `assemble`, `evolve`,
   `retry`, `heal`), no map or species names, and don't keep the original
   timestamp digits if you plan to run several from the same producer (a
   shared prefix pattern is itself a hint).
3. Pass the ORIGINAL path and the SCRUBBED name to the tool; it copies the
   file into the temp workspace under the scrubbed name, so the original
   filename never appears anywhere the council can see. (The tool warns if
   the scrubbed name occurs inside the source filename.)
4. Do not show the council the `.png` sidecar or your grading sheet, and
   don't discuss the case in dexbot-run files between runs — the council
   reads its own logs.

Note: the decoded state summary (map, coords, party, game state) is fair
evidence — the live supervisor would provide the same. Only the *label* is
withheld, because the live watchdog's labels describe the interrupted skill,
not a human's root-cause diagnosis.

The setup instance has never run this tool against the holdout; the holdout
is untouched, reserved entirely for your grading.
