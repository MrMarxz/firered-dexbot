# PREFLIGHT_REPORT_2 — Phase 4b: remediation + re-exam

Operator instance, 2026-08-01. Executes PREFLIGHT_REPORT.md §C's remediation
recommendation (human-approved). Same hard rules as Phase 4: no live run, no
pushes, copies only from the holdout, no protocol edits. Honesty over optimism.

**Status at a glance: the re-exam RAN and CLEARED the bar on every axis — 3/3
root causes, 3/3 protocol-compliant, 0 forbidden fetches, 0 §11 violations
(§H, §I). Both remediations are validated by that result. One new run-blocking
defect was found and fixed en route (the council-session background-wait
ceiling, dexbot-run `9191b72`). Recommendation is now GO for Event 0 once the
standing human-only items in PREFLIGHT_REPORT.md §B are closed (§J).**

*(Sections A–G below are the pre-exam record, written before the run and left
intact. §E's blocker was resolved by your permission grant; §F's no-go call is
superseded by §J.)*

## A. Remediation 1 — live-fidelity watchdog telemetry in the dry-run harness

Done, this repo, commit `01cf77c`.

`tools/council_dryrun.py` now synthesizes the skills.jsonl tail the live
supervisor always hands a council:

- **stall record** — sample tuple, script stack, state path, exactly as
  `_dump_stall` journals it. The sample is produced by dexbot-run's own
  `_progress_sample()` against the loaded savestate; the script stack read the
  same way `_dump_stall` reads it; the emission itself goes through
  dexbot-run's own `_log_event` (redirected to the exam workspace), so the
  outer line format is the live code's, not a re-template.
- **error record** — `run_skill`'s standstill SkillError text, with the frame
  budget chosen by the live branch (menu 6k vs overworld/battle 30k, read from
  the run repo's constants against the state's decoded game_state).
- **deferred record** — the planner's failure-boundary journal line, emitted
  only for catch-loop objectives (`--defer-event/--no-defer-event` override;
  default derived from the original label's call-site class — story/nav/patrol
  call sites swallow the SkillError without journaling a defer, and the
  synthesis must not invent one).
- **`--prior` (repeatable)** — earlier dumps of the same objective become
  earlier cycles in the tail, so clusters carry their real defer/retry history
  (position/money over time decoded from each prior state — real evidence, not
  narrative).
- The interrupted-skill **label is scrubbed** to the opaque objective name
  (the only scrub); timestamps are synthesis-time (original HHMMSS stamps are
  answer-key material). Both disclosed to the council in the preamble, along
  with: records predating the stall window are absent-not-evidence, and
  historical dumps predate the DRYRUN-003 enrichment fields.
- The trigger now matches the live `Watcher` shape: sample repr inline in the
  detail, evidence led by `[state, skills.jsonl]`.

Format fidelity is unit-tested against the REAL emitters, not against my
expectations: `tests/test_council_dryrun_telemetry.py` (5 tests) drives
dexbot-run's actual `_dump_stall` and asserts the synthesized record differs
from the live one by EXACTLY the three live-only enrichment fields
(key-for-key, order preserved), locks the error/deferred record shapes and the
budget branch, and plants source tripwires in the run repo so future drift
breaks the test instead of silently degrading exam fidelity. This repo's
suite: **79 passed, 2 failed** — the 2 are the named Psyduck baseline
failures, nothing new.

## B. Remediation 2 — DRYRUN-003's _dump_stall observability enrichment

Done, dexbot-run, commit `bf6b501` (references the event, per the task).

Implemented exactly the event's Seat B PRIMARY proposal (telemetry-only; the
subordinate leg guard is NOT included — Seat C passed the observability change
independently and the guard needs its own §9 replay):

- `controller_stack` — the qualnames `run_skill` already computes per frame
  and previously discarded at dump time.
- `held_buttons` — `emulator.is_button_held` over `input_map` (public API).
- `nav_intent` — new best-effort `dexbot.navigation._LAST_NAV` breadcrumb
  (destination / current leg / position), written at both `navigate_to`
  walker-leg sites; honestly `None`/stale for raw upstream legs (story.py's
  direct `navigate_same_level`), so `controller_stack` stays the
  authoritative "who was driving" signal, as the proposal disclosed.

Every read is guarded — a failed read degrades to an `unavailable:` marker
and the dump still lands. 4 new unit tests
(`tests/test_stall_dump_enrichment.py`) cover the happy path, the None
breadcrumb, the never-break guarantee, and JSON serializability. Full
dexbot-run suite: **116 passed, 2 failed** — the 2 are exactly BASELINE.md's
Psyduck failures; no new failures.

## C. Seat B occupancy (protocol §3) — gate PASSES

Probed per the task before any exam work, using the same harness the councils
use (`claude -p` orchestrator spawning a sub-agent):

1. Full-ID spawn: the spawn interface REJECTS `claude-opus-5` — it accepts
   only bare aliases (`sonnet|opus|haiku|fable`). Unchanged from the exam.
2. Alias resolution: `opus` now resolves the sub-agent to
   **`claude-opus-5[1m]`** — the §3 Seat B default (Opus 5; `[1m]` is the
   1M-context variant marker), where every exam-era spawn resolved to
   `claude-opus-4-8[1m]`.

So §3 occupancy is now producible and the standing §11 violation disappears:
re-exam entries' Model check lines should read Seat B `claude-opus-5[1m]`
(spawn param `opus`, alias-verified per the preamble's fallback rule).
One nuance for your ratification: if you want Model checks to match §3
STRING-exactly, amend §3 by human edit to note the `[1m]` variant marker;
I treat "same model, harness-annotated context variant" as a match and will
grade §11 on that basis unless you say otherwise.

## D. Re-exam — prepared end-to-end (selection, key, synthesis validated)

Selection per the task: 3 FRESH stalls, ≥2 from the missed class
(live-controller/navigation freezes). Peek-decoded each candidate (operator
side only) to confirm the captured state matches the documented diagnosis.
Full answer key + md5 integrity record: RUNBOOK.md appendix, "Re-exam
selection (Phase 4b)". Summary:

| Scrubbed | Original (target + priors) | Class | Why it tests the remediation |
|---|---|---|---|
| stall_g | vs_seeker_leg_133344 + priors 133200/133234/133309 | missed (nav/live-controller) | The stall_b cluster, fresh files: peek shows the avatar pinned at Vermilion (20,24) with money frozen at ₽136 across all four dumps — the tail now SHOWS the blind identical retries a live council would have seen. Hit bar: leg-freeze mechanism + integrating the repetition evidence (re-citing DRYRUN-002 alone falls short). |
| stall_h | beat_koga_221503 + prior 221419 | missed (nav/live-controller) | DEVLOG's "Cycling Road pinned the avatar in a state no walker could see": both dumps at Route 17 (11,18), ₽4,588 — exact match to the documented forced-slide pin, since fixed in current code (an already-remediated diagnosis à la DRYRUN-004 is a hit). |
| stall_i | catch_Dunsparce_070531 (no priors) | nav/planner (graph reachability) | KL's Three Island Port warpless-grass gap; a catch-loop objective, so the tail exercises the synthesized `deferred` record path. |

Harness synthesis validated for all three with `--no-invoke` (no council
exposure): stall_g tail = 8 records/4 cycles, stall_h = 4/2, stall_i = 3/1
incl. the deferred record. Validation workspaces deleted afterwards to keep
%TEMP% unambiguous. dexbot-run cleanliness restored before the exam: my own
test-suite artifacts (logs/skills.jsonl assemble_party telemetry + the
recreated livingdex profile) archived to
`..\prelaunch_log_archive\phase4b_testrun\`; logs/ empty, no profile,
STATE.md `Open event: none`. Holdout originals untouched (read-only copies;
md5s recorded in the RUNBOOK appendix).

## E. The one blocked step — launching the council sessions (your call)

Running the exam means launching `claude -p` council sessions with
`--dangerously-skip-permissions` (via your User-scope `DEXBOT_CLAUDE_ARGS`,
exactly as the Phase 4 exam did). This operator session's permission
classifier declined that launch, and its guidance is to stop and let you
decide rather than engineer around the denial. I did not attempt any
workaround. Two honest alternatives were rejected on the merits:

- Unprivileged councils (no bypass flag): the session cannot write
  COUNCIL_LOG.dryrun.md or run reproductions (only the Codex MCP server is
  pre-approved in dexbot-run's `.claude/settings.local.json`) — the chain
  breaks mid-event AND the council's cross-run memory would still record the
  attempt, contaminating the fresh stalls. A broken run burns an exam item.
- Editing dexbot-run's settings to allowlist Write/Bash for the councils:
  that is me granting what the classifier just declined — yours to authorize,
  not mine.

**To run the re-exam** (one at a time, ~25–40 min each; from firered-dexbot
root in a fresh shell so `DEXBOT_CLAUDE_ARGS` is present):

```
.venv\Scripts\python.exe tools\council_dryrun.py ..\quarantine_holdout\_stalls\vs_seeker_leg_133344.ss1 stall_g --prior ..\quarantine_holdout\_stalls\vs_seeker_leg_133200.ss1 --prior ..\quarantine_holdout\_stalls\vs_seeker_leg_133234.ss1 --prior ..\quarantine_holdout\_stalls\vs_seeker_leg_133309.ss1
```

```
.venv\Scripts\python.exe tools\council_dryrun.py ..\quarantine_holdout\_stalls\beat_koga_221503.ss1 stall_h --prior ..\quarantine_holdout\_stalls\beat_koga_221419.ss1
```

```
.venv\Scripts\python.exe tools\council_dryrun.py ..\quarantine_holdout\_stalls\catch_Dunsparce_070531.ss1 stall_i
```

Or re-invoke me with permission to run them (a Bash allow rule for
`tools/council_dryrun.py`, per the classifier's own suggestion) and I will
run the full sequence: one at a time, chain verification after each
(§12-format entry, Model check lines incl. Seat B `claude-opus-5*`, one Codex
threadId, exchange cap, citation spot-check, forbidden-fetch grep of every
transcript, logs/profile cleanliness between runs), then draft-grade against
the RUNBOOK key and finalize this report. Either way, hand the results back
to me for verification + grading — the answer key never enters dexbot-run.

## F. Pass bar and current go/no-go

Re-exam pass bar (task directive): **≥2/3 root causes, 3/3
protocol-compliant, zero forbidden fetches, zero §11 violations** (the Seat B
mismatch must be gone — §C says it now can be).

**Current recommendation: NO-GO for Event 0 until the re-exam runs and
clears the bar.** Everything else on the critical path is green: both
remediations landed with no new test failures in either repo, the Seat B
occupancy gate passes, the exam is selection-complete, key-complete, and
synthesis-validated. The only outstanding blockers are (1) the council-launch
authorization above and (2) the standing human-only items from
PREFLIGHT_REPORT.md §B (spend caps, Windows prep, GitHub privacy — unchanged).

## G. Repo state after this session

- firered-dexbot (this repo): commit `01cf77c` (harness synthesis + fidelity
  tests + tools/README); RUNBOOK.md appendix extended with the Phase 4b
  answer key (uncommitted alongside this report until you've seen it);
  suite 79P/2F (2 = named baseline).
- dexbot-run: local main at `bf6b501` (DRYRUN-003 telemetry commit on top of
  `fc8095d`); suite 116P/2F (2 = named baseline); logs/ empty; no profile;
  STATE.md `Open event: none`; COUNCIL_LOG.dryrun.md untracked as before;
  **nothing pushed**.
- Holdout: untouched, read-only access only; selected-file md5s recorded.
- No protocol files were edited.

---

# Re-exam execution (added after the run, 2026-08-01)

## H. A run-blocking defect found by running the exam

The first stall_g invocation exited **rc=0 after 25 min having written
nothing**. `claude -p` terminates a session whose BACKGROUND tasks are still
running after a default 600 s ceiling, printing "Background tasks still
running after 600s; terminating". The council's seats ARE background
sub-agents: Seat A had finished and Seat B was mid-deliberation. No Codex
thread, no council-log entry — `COUNCIL_LOG.dryrun.md` was byte-identical to
its pre-run md5.

This is **not a dry-run artifact**. `council_dryrun.py` invokes through
dexbot-run's own `supervisor.claude_argv()` and inherits the environment —
the exact path `invoke_claude` uses for live events. A live council whose
Seat B ran past 10 min would have been killed the same way, and because the
exit code is 0 the supervisor could not have told the event died.

Fixed in two places:

- `tools/council_dryrun.py` (this repo) — `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`
  defaulted to `0` so the exam could proceed.
- **dexbot-run `9191b72`** (your ratification) — `council_env()` sets the same
  default for the live orchestrator launch and `invoke_claude` passes it;
  operator override preserved via `setdefault`. Not an unbounded hang:
  `COUNCIL_TIMEOUT` (4 h) still bounds the session and, unlike the CLI
  ceiling, is logged and handled as "died mid-event". `planner_shim` is out of
  scope (single-turn, no sub-agents, own `cli_timeout`). 4 unit tests, the
  load-bearing one driving the real `invoke_claude` path so an inherited-env
  regression fails the suite. dexbot-run suite **120 passed / 2 failed** (the
  named Psyduck baseline failures).

Evidence the fix is real: the same invocation then ran **65 min** and logged a
complete event; stall_h ran 79 min and stall_i 86 min. Every one of the three
would have died under the old ceiling.

**The aborted attempt did not burn the exam item.** dexbot-run's cross-run
memory was last written 03:25 during exam 1 and the 14:56–15:19 session added
nothing; the repo was clean and no entry was logged. stall_g was therefore
re-run as a clean first grade, not a contaminated retry. This is disclosed in
the RUNBOOK sheet.

## I. Re-exam result — CLEARED

Full per-stall grading, with caveats, is in the RUNBOOK.md appendix. Summary:

| Scrubbed | Entry | Runtime | Root cause | Protocol |
|---|---|---|---|---|
| stall_g | DRYRUN-007 | 65 min | **HIT (exceeds bar)** — surf-dismount check-order bug, `map_path.py:947` before `:951`; repetition evidence integrated (32,000-frame gaps, zero intervening frames); refined DRYRUN-002 rather than re-citing it | Clean |
| stall_h | DRYRUN-008 | 79 min | **HIT** — Cycling Road forced-slide pin at Route 17 (11,18), reproduced byte-exactly, recognized as since-remediated | Clean |
| stall_i | DRYRUN-009 | 86 min | **HIT (exact)** — Dunsparce grass has no incoming warp edge; root traced to FRLG runtime layout swaps invisible to a ROM-static tile model | Clean |

**Tally: 3/3 root causes, 3/3 protocol-compliant, 0 forbidden fetches, 0 §11
violations.** Bar was ≥2/3 / 3/3 / 0 / 0.

Verification performed per stall, independently of the councils' own claims:
council-log md5 diffed against a pre-run baseline; §12 entry structure; Model
check lines; single Codex threadId per event; exchange cap; citation
spot-checks; a forbidden-scope grep of every orchestrator and sub-agent
transcript; dexbot-run cleanliness (`git status`, `logs/`, `fixtures/`,
`STATE.md`) between runs; and holdout md5 re-verification after the last run
(all three unchanged).

What the remediations bought, concretely:

- **§11 is closed.** All three entries record Seat B `claude-opus-5[1m]` as a
  MATCH. The standing violation from DRYRUN-001…006 is gone.
- **Remediation 1 (synthesized tail) demonstrably worked on the case it was
  built for.** stall_g's council used the repetition evidence as load-bearing
  reasoning — four samples exactly 32,000 frames apart with zero intervening
  frames — to rule out transient and RNG explanations. That is precisely the
  evidence class whose absence caused the three Phase 1 misses.
- **Quality of deliberation rose.** Seat B withdrew its own centrepiece fix
  when the driver falsified it (stall_h), and stall_i produced the only
  FAIL→returned→cured cycle across both exams — the §7 gate working.

Honest caveats, both recorded in the RUNBOOK sheet:

1. **stall_h's scrub leaked.** `navigation.py:813-820` names "the beat_koga
   30k-frame stall at (11,18)" in a source comment, so objective and
   coordinates were discoverable in-repo. The reconstruction was still
   independent and byte-exact, but stall_h is a weaker test of the telemetry
   remediation than stall_g. Future selections should grep the run repo for
   the original label first.
2. **stall_g's caller attribution differs from the key** (Vermilion rod catch
   objective vs `_earn_by_vs_seeker` legs); Seat C forced it to "plausible
   caller path, not proven telemetry". The hit bar was the mechanism.
3. Minor §10 scope question for you: Seat B fetched pret/**pokeemerald** for a
   shared Gen-3 struct header. Not in §10's allowed list, not the forbidden
   category. Consider naming sibling pret decomps explicitly.
4. Tail fidelity could go further — the synthesized tail carries only
   `stall`+`error` records, and DRYRUN-007 noticed a live run also emits
   `start`/`success`/`deferred`/`skipped`.

## J. Go/no-go

**GO for Event 0**, conditional only on the standing human-only items from
PREFLIGHT_REPORT.md §B (spend caps recorded, Windows prep, GitHub privacy) —
unchanged and still yours.

Critical-path status: both remediations landed and are now validated by
result, not just by unit test; the Seat B occupancy gate passes in three
consecutive live events; the council chain (claude -p → sub-agents → Codex
thread → log entry) completed end-to-end three times, which also re-satisfies
RUNBOOK Phase 1.5; and the background-wait defect that would have silently
truncated live events is fixed and tested.

One item to decide before Event 0: §3 still names Seat B `claude-opus-5` while
the harness reports `claude-opus-5[1m]`. I graded the variant marker as a
match. If you want Model checks to be string-exact, amend §3 by human edit.

## K. Repo state after the exam

- firered-dexbot: `01cf77c` + uncommitted `tools/council_dryrun.py` (ceiling
  default), RUNBOOK.md (re-exam grades), and this report. Suite **79 passed /
  2 failed** (named baseline).
- dexbot-run: local main at **`9191b72`**; suite 120P/2F; `logs/` empty; no
  profile; STATE.md `Open event: none`; COUNCIL_LOG.dryrun.md untracked as
  before, now carrying DRYRUN-001…009; **nothing pushed**.
- Test-suite telemetry from the regression run archived to
  `..\prelaunch_log_archive\phase4b_testrun2\` to keep `logs/` empty between
  exam runs.
- Holdout: untouched; all three target md5s re-verified after the final run.
- No protocol files were edited.
