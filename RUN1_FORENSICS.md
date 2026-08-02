# RUN1_FORENSICS.md — attempt 1 post-mortem (terminated by the human at T+8.85h)

Written by the operator instance, 2026-08-02, from the archive only (`run1_archive/`
in this repo — byte-identical copies of dexbot-run's logs, the wedged `livingdex`
profile, STATUS.md, COUNCIL_LOG.md, STATE.md, and `fixtures/_phases`). No live run
was performed. Timezone note: log timestamps are UTC (`Z`); file names/mtimes and
savestate names are local time (UTC+2), so `2026-08-02_02-16-51_auto.ss1` ≡
00:16:51Z.

## Verdict in one paragraph

The bot spent 4 minutes playing well and 7 hours 57 minutes spinning at ~99% CPU
inside a **single controller step** of `catch_Metapod` — pre-first-yield planning
code on the `ensure_healthy()` heal path, entered with 4/6 party members fainted
right after `assemble_party` failed with `No PC tile found on map (4, 0)`. Because
the step never returned, the frame loop never ticked again: no frames, no
telemetry, no savestates, no skill events, and **every in-bot watchdog starved**
(they are all frame-denominated, and the wall-time step watchdog is a no-op on
Windows — no SIGALRM). The supervisor stayed blind for two independent reasons,
both now fixed: its §4.3 no-progress trigger is frame-denominated (frames frozen ⇒
0 frames "stalled" forever — Defect B), and all seven hourly §4.5 reviews — at
least the last of which contained a complete, correct STALL diagnosis — were
discarded because the UTF-8 review output was read back in cp1252, mojibaking the
em-dash the prompt itself demands, so the verdict regex never matched (Defect A).

## Timeline (all UTC, from `run1_archive/logs/`)

| Time | Event | Evidence |
|---|---|---|
| 23:22:16 | Supervisor starts; bot pid 25836 | supervisor.log:1-2 |
| 23:22–23:24 | Bot crashes rc=1 ×3 (cp1252 `♀` panel — EVENT 1's bug) | supervisor.log:5-10; skills.jsonl:1-6 |
| 23:23:47 | §4.4 crash_loop trigger → pause → council (EVENT 1) | supervisor.log:10-12 |
| 23:41–00:07 | §9.2 regression runs append test skill records to the live skills.jsonl (known carried concern 9) | skills.jsonl:7-87 |
| 00:12:47 | EVENT 1 closed (stdio hardening, dexbot-run `4fb6c16`); bot resumes, pid 25724 | supervisor.log:23-24 |
| 00:12:54–00:16:45 | Healthy sprint: scripted_opening ✓, catch_Pidgey ✓, restock ✓, catch_Pikachu ✓, catch_Caterpie ✓, catch_Weedle ✓, catch_Kakuna ✓, collect_items ✓. dex_owned 1→6 | skills.jsonl:88-113 |
| 00:16:45 | `assemble_party` start (frame 103,147), phase `to_pc` | skills.jsonl:114-115 |
| 00:16:51 | Auto-checkpoint written — **the last calm savestate, intact** | bot.log; profile `current_state.ss1` (mtime 02:16:51 local) |
| 00:16:52 | `assemble_party` error `No PC tile found on map (4, 0)`; planner prints "team assembly deferred"; `catch_Metapod` start, frame 109,589 | skills.jsonl:116-117; bot.log |
| 00:16:52.353 | **Last telemetry line ever written** (frame 109,033) | telemetry_20260802_021249.jsonl tail |
| 00:16:52 → 08:13:29 | Nothing. No frames, no telemetry, no skill events, no savestates. Worker at ~99% CPU (28,028 s CPU logged by review #7's live observation) | all files frozen; review_last_invocation.log |
| 01:12–08:05 | Seven hourly §4.5 reviews invoked; all seven logged "returned no verdict line (rc=0) — review skipped" | supervisor.log:37-132 |
| 08:13:29 | Human Ctrl+C. KeyboardInterrupt lands **inside the spinning step**; run_skill logs `catch_Metapod status=error error=""` (`str(KeyboardInterrupt()) == ""`) at 08:13:29.481; traceback starts printing at `run.py:116`; supervisor's TerminateProcess cuts it off mid-print | skills.jsonl:118; bot.log tail; supervisor.log:135-137 |

Wedge duration: 00:16:52.987 → 08:13:29.481 = **7h 56m 36s**.

## Open question: what was the bot doing, and why were frames barely advancing?

**It was executing one `next(controller)` call for eight hours.** The evidence
chain, all archive-derived:

1. **The wedge is inside `catch_Metapod`'s first step(s).** Telemetry writes every
   600 frames; the last line is frame 109,033 and the skill started at frame
   109,589, so the next telemetry line was due at frame 109,633 — **at most ~44
   frames ran after the skill started**, then frame advance stopped entirely.
   Frames only advance when `run_skill`'s loop regains control between steps
   (`dexbot/runner.py:401` `run_single_frame`), so a step that never returns
   freezes the frame counter, the telemetry tick, the auto-checkpoint hook, and
   the skills journal all at once — which is exactly the observed signature.
2. **The main thread never crashed; it was busy.** The human's Ctrl+C at 08:13:29
   raised KeyboardInterrupt in the bot's main thread, and `run_skill`'s
   `except BaseException` handler *executed*, writing the empty-string error
   record at 08:13:29.481 (`str(KeyboardInterrupt())` is `""`). The truncated
   traceback at the end of bot.log (`run.py:116, in <module>` then nothing) is
   that same KeyboardInterrupt propagating to top level, its printing cut off by
   the supervisor's TerminateProcess one moment later. There was no crash at
   00:16:52 — the "[planner] team assembly deferred" line is the planner
   *catching* the assemble_party SkillError as designed.
3. **What that first step executes.** `catch_species`'s first action is
   `yield from ensure_healthy()` (`dexbot/catching.py:575`). The heal-worthiness
   test was true — the last telemetry shows the party as Squirtle 0/21 HP (lead,
   fainted), Pikachu 0/15, Pidgey 0/20, Caterpie 0/18, Weedle 9/19, Kakuna 10/19,
   ¥152 — so the generator proceeds into `_pick_reachable_center()` and then
   `navigate_to(center...)` (`catching.py:513-536`). All of that is **pre-yield
   planning code: it runs inside the first `next()` on the controller.**
4. **The pathology is a known, documented family.** `_pick_reachable_center`'s
   own docstring (`catching.py:441-443`): live-search fallback "burns MINUTES of
   uncached failed A* … this spun a run at 100% CPU for two hours."
   `_with_step_watchdog`'s docstring (`runner.py:218-231`): "planning pathologies
   have wedged steps for hours at 100% CPU with the avatar frozen."
5. **Why nothing interrupted it.** The step watchdog interrupts CPU-bound steps
   via SIGALRM — **which does not exist on Windows**, so
   `_with_step_watchdog` degrades to a bare `next(controller)`
   (`runner.py:225-227`). Every other defense — the 30k-frame behavioral stall
   detector, the pacing detector, `timeout_frames`, the §4.1 stall dump — is
   frame-denominated and lives inside the frame loop, downstream of the step
   that never returned. `fixtures/_stalls/` is empty: the in-bot watchdog never
   got to run.
6. **Which exact loop was spinning is deliberately left undetermined.** Pinning
   it requires executing gameplay code (the wedge is the council's to fix in
   attempt 2, not the operator's). The archived profile reproduces the approach
   state: load `run1_archive/profile_livingdex/current_state.ss1` (calm
   overworld, one frame-tick before the fatal objective) and run the planner;
   it will select `catch_Metapod` with the same fainted party. Note also that
   `run.py:21-25` already ships `DEXBOT_DUMP=1` faulthandler instrumentation
   that dumps all stacks every 30 s — had it been enabled, bot.log would name
   the wedged line. Worth considering for attempt 2.

### Why the party was dead in the first place (context, not diagnosis)

The five catches in four minutes left 4/6 party members at 0 HP (catch battles
are fought, not fled). The planner's answer is `assemble_party` before each
objective — deposit the battered team, withdraw a fresh one — but on Route 1 it
failed: `No PC tile found on map (4, 0)`, and the planner's contract is to
proceed with whatever party it has (`planner.py:568`). That put a
heal-mandatory party into `catch_species`, forcing the `ensure_healthy` planning
path that wedged. The PC-tile failure is adjacent to, but not identical with,
STATE.md carried concern 1 (unannotated maps) — the council should treat it as
its own lead.

## Why no supervisor trigger fired (all seven hours)

| Defense | Why it stayed silent |
|---|---|
| §4.3 no_progress (90 min of emulation) | **Frame-denominated** (Defect B): `stalled = latest_frame − anchor_frame`; frames froze at 109,033, so the measure read 0 forever. progress.jsonl "kept moving" because `tools/progress_snapshot.py:60-63` re-stamps the frozen telemetry tail with a fresh outer clock every 15 min. |
| §4.5 hourly review ×7 | **Verdicts lost in decode** (Defect A): `invoke_claude` read the UTF-8 sink with `read_text(errors="replace")` — locale cp1252 on this machine. The em-dash the prompt template itself demands (`REVIEW VERDICT: STALL — <reason>`) arrives as bytes `E2 80 94`, decodes in cp1252 as `â€”`, and the old separator class `[—–:-]` fails the whole line → verdict "missing" → "review skipped, bot keeps running", seven times. Verified byte-for-byte against the archived output: the same text parses as `('stall', …)` under UTF-8. Review #7 (the only surviving output — the sink truncates on every invocation, so #1–6 are unrecoverable) contained a complete and correct diagnosis by Seat A: worker pid 16244 at ~99% CPU, all outputs frozen since 00:16:52Z, dashboard freshness an artifact, savestate intact. The supervisor threw it away. |
| §4.4 crash loop | The process never exited. EVENT 1's deliberate deferral of a top-level exception handler rested on "any unhandled exception still exits rc≠0" — falsified by this wedge, which never raised at all (STATE.md concern 10 updated). |
| §4.1 in-bot stall dump | Frame-starved (see above). |
| §4.2 repeated defer | Lives at the `run_skill` return boundary — never reached. |
| Process liveness | `bot.poll()` watches the venv launcher (pid 25724), which stays alive while its child (the real interpreter, pid 16244) spins. Liveness was technically true anyway — the process *was* alive. It was just doing nothing observable. |
| STATUS.md dashboard | "Snapshot age: 0 min" comes from `tools/status_write.py:123` using the snapshot's own poll time (`e["time"]`), not `telemetry_time` — verified in code. The dashboard reported a healthy heartbeat for eight dead hours. |

## Fixes shipped in this close-out (detection only, per mandate)

In dexbot-run `supervisor/supervisor.py`, with unit tests in
`tests/test_harness_supervisor.py` (17 new tests, whole file 51/51 green):

- **Defect A:** sink read is now `encoding="utf-8"`; the verdict regex accepts
  em/en-dash, colon, hyphen, U+FFFD, *and* the cp1252-mojibake byte renderings,
  so a future decode regression can degrade the reason text but not lose the
  verdict (regression test uses the verbatim attempt-1 line under both
  decodings); every review output is preserved to `logs/reviews/` (attempt 1
  kept only the last of seven); and **§4 item 7**: three consecutive
  verdictless reviews are themselves a stall event — pause + full council on
  the review pipeline's own evidence. Rate-limited invocations neither extend
  nor reset the streak.
- **Defect B:** **§4 item 6**: dex_owned unchanged for 120 wall-clock minutes
  while the bot process is running is a stall event, independent of frame
  count (window counts running time only; council pauses slide the anchor).
  Every heartbeat now carries an emulation-rate line read from the bot's own
  telemetry tail (not the re-stamped progress.jsonl):
  `heartbeat: bot=… objective=… emu=<N> frames/min telemetry_age=<M>min` —
  attempt 1's signature would have read `emu=0 frames/min
  telemetry_age=<growing>` from the first post-wedge heartbeat.

Had both fixes been live, attempt 1 would have paused by ~02:17Z at the latest
(wall-clock trigger; the deaf-review trigger would have fired at the third
verdictless review, ~03:31Z; and with the decode fix alone, review #1 at 01:18Z
would have been *heard* — whatever its verdict was).

## Detection gaps NOT closed here (council material for attempt 2)

1. **The wedge itself** — gameplay logic, council's mandate. Reproduction
   recipe above; suspect list: `_pick_reachable_center()` graph planning /
   `navigate_to()` live A* fallback, entered from `ensure_healthy()`.
2. **No Windows-viable step watchdog** — SIGALRM is unix-only; a CPU-wedged
   step is uninterruptible in-process on this platform. Any fix (watchdog
   thread + `PyThreadState_SetAsyncExc`? worker process? faulthandler-based
   detection?) touches the runner and needs the council's design + §9.1 replay.
3. **`DEXBOT_DUMP`** — consider enabling (or a rate-limited variant) for
   attempt 2 so a future wedge names its own line.
4. **assemble_party PC-tile failure on (4, 0)** and the party-health collapse
   during catch sprints — both feed the wedge path.
5. **run.py's rc≠0 contract** (STATE.md concern 10) is falsified by this run;
   the deferral's premise needs the council's re-decision.

## Exam-fixture note

This is our own run's data — no quarantine concern. Two candidates:

- **Supervisor-side (recommended):** the frozen-telemetry log bundle
  (`run1_archive/logs/` minus nothing — it is already self-consistent) as a
  dry-run exam fixture: replay the logs against the supervisor and assert §4
  item 6 fires at 120 min and item 7 at the third verdictless review. The
  17 new unit tests encode the same facts synthetically, but the bundle
  exercises the real files.
- **Gameplay-side:** `run1_archive/profile_livingdex/current_state.ss1` (calm
  overworld, 00:16:51Z, one objective away from the wedge) as the repro
  fixture for the council's attempt-2 fix. The ten `states/*.ss1` before it
  bracket the whole catching sprint if a broader replay is wanted.
