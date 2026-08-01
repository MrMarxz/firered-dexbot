# HARNESS_REPORT — Phase 3: council harness built (no live run)

Setup instance, 2026-07-31. Continuation of SETUP_REPORT_3.md. The council
machinery that COUNCIL_PROTOCOL.md and dexbot-run/CLAUDE.md assume now exists.
No live run was started; no gameplay logic was modified; the holdout is
untouched; nothing was pushed.

## A. State and record files (dexbot-run root)

- `STATE.md`, `COUNCIL_LOG.md`, `FINDINGS.md`, `DECISIONS.md`, `PARKED.md` —
  created with the protocol's header/index structure and zero entries.
  STATE.md's `- Open event: <value>` line is the supervisor's resume contract
  (literal `none` = resume the bot).
- `BASELINE.md` — pytest baseline **74 passed / 2 failed / 0 skipped**,
  re-verified by a fresh run at dexbot-run HEAD `fc60676` before recording
  (33.63s). The two failures, named per test:
  `tests/test_m6_planner.py::test_planner_queue_covers_pre_brock_species` and
  `tests/test_m6_planner.py::test_pre_brock_dex_complete` (the Psyduck
  planner/KB drift from SETUP_REPORT_3 §3).
- `COUNCIL_PROTOCOL.md` §9.2 placeholder replaced with those two test names —
  the single authorized edit, made once. Diff is in commit `3ab0411`.
- Baseline invocation is `pytest tests/` (the dexbot suite). A bare `pytest`
  from the root also collects `pokebot-gen3/tests/`, which needs upstream test
  states that don't exist here — BASELINE.md documents the correct scope.

## B. Codex MCP wiring — verified end-to-end

- Registered in `dexbot-run/.mcp.json`: `codex mcp-server`, stdio, spawned via
  `cmd /c` (Windows .cmd shim). Pre-approved for headless sessions in
  `dexbot-run/.claude/settings.local.json` (`enableAllProjectMcpServers` +
  `enabledMcpjsonServers: ["codex"]`).
- Handshake transcript: `setup_proof/codex_mcp_handshake.txt`. Evidence chain:
  - tools exposed: `codex`, `codex-reply`;
  - first call returned structured content with
    `threadId 019fb9b2-f8b7-7a61-9006-884853406601`;
  - `codex-reply` on that threadId recalled the planted codeword (LAPRAS-7) —
    thread continuity proven;
  - harness evidence per protocol §11: the `session_configured` event reports
    `model: gpt-5.5, model_provider_id: openai` (the configured GPT-5-class
    model; `~/.codex/config.toml` sets `gpt-5.5`, reasoning `xhigh`);
    self-report cross-check: "I am Codex, a coding agent based on GPT-5."
  - Claude Code end-to-end (the council's actual path): a headless `claude -p`
    session in dexbot-run called `mcp__codex__codex` and returned
    `WIRED — threadId 019fb9b5-8282-7f33-b01c-61c8d059a442` (transcript
    addendum).
- Cosmetic: `claude mcp list` still displays the server as "Pending approval"
  (that display tracks the interactive trust dialog); real sessions honor the
  settings pre-approval, as the live test proves.

## C. Supervisor (`dexbot-run/supervisor/supervisor.py`, 297 lines, stdlib only)

Dumb outer loop, LLM-free. Bot lifecycle (PID + health logged), §4 trigger
watch, stop-the-world council invocation, STATE.md-gated resume, usage-limit
backoff 15→30→60→60… min retried forever (bot stays paused), 5-min heartbeats
including during deliberation and backoff, 15-min snapshot cadence, crash
restarts below the §4.4 threshold, offset persistence across supervisor
restarts (`logs/supervisor_state.json`). Full behavior table in
`supervisor/README.md`.

Design decision worth review: **pause is a hard process kill, deliberately.**
LibmgbaEmulator's graceful shutdown unconditionally overwrites
`current_state.ss1` with the live state — mid-wedge that reproduces the
resume-poisoning run.py's own comments warn about (Diglett Cave incident).
The bot's 5-minute auto-checkpoint writes only calm-overworld states, so the
last checkpoint is the correct resume point (≤5 game-minutes replayed), and
the watchdog has already dumped the wedged state to `fixtures/_stalls/` as
council evidence.

Launch (dexbot-run root):

```
.venv\Scripts\python.exe supervisor\supervisor.py
```

with `DEXBOT_CLAUDE_ARGS` and `DEXBOT_LLM_API_KEY` set per
`supervisor/README.md`. Stop with Ctrl-C (stops the bot too).

## D. Progress tracking

- `tools/progress_snapshot.py` — condenses the newest `logs/telemetry_*.jsonl`
  line (the bot's own memory decoder; no new memory-reading code) into one
  `logs/progress.jsonl` line: UTC ts, dex owned/seen, badges, money, map
  (named via textual MapFRLG parse, numeric fallback), frame.
- `tools/status_write.py` — rewrites `STATUS.md`: dex, badges, money,
  location, catch rate over 1h/6h/24h vs run average, open event, parked
  count, last council event + verdict, heartbeat age, current objective.
- Both wired into the supervisor (every 15 min, plus once at every trigger so
  the council sees fresh evidence). The §4.5 strategic review's rate windows
  come from `status_write.rate_windows` over progress.jsonl — the same code
  path as the dashboard, never recomputed ad hoc.

## E. Dry-run harness (this repo, human-operated)

- `tools/council_dryrun.py` + `tools/README.md`. Copies a savestate into a
  temp workspace under a scrubbed name, decodes a state summary with this
  repo's emulator harness (the test suite's exact pattern), generates the
  supervisor-IDENTICAL watchdog-stall invocation (imported from dexbot-run's
  supervisor, not re-templated), wraps it in a DIAGNOSE-ONLY preamble (Seat A
  + Seat B only, implement nothing, log to `COUNCIL_LOG.dryrun.md` with
  DRYRUN- event ids, never touch the live record files), and invokes the
  orchestrator in dexbot-run. `--no-invoke` inspects without invoking.
- README documents the scrubbing procedure: holdout filenames ARE the previous
  owner's diagnosis (`vs_seeker_leg_*.ss1`), so the human notes the original
  name in a private grading sheet and passes an opaque name; the tool warns if
  the scrubbed name appears in the source filename.
- Verified with `--no-invoke` on `fixtures/m1_game_start.ss1` (a normal
  fixture: decoded map (4,1) @ (6,6), matching its README recipe). **No
  holdout file was touched, and no dry-run orchestrator invocation was made.**

## F. Config

`dexbot-run/config.json` llm_planner → Anthropic OpenAI-compatible endpoint
(`https://api.anthropic.com/v1`), model `claude-sonnet-5`, enabled, key from
env `DEXBOT_LLM_API_KEY` (documented in supervisor/README.md). No key material
anywhere in either repo. The name deliberately avoids `ANTHROPIC_API_KEY`,
which the spawned `claude` CLI would honor and silently switch to API-key
billing.

## Tests

New: `dexbot-run/tests/test_harness_supervisor.py` — 16 tests, synthetic
telemetry only (no emulation): stall fires; defers fire only past 5, counted
per objective; no-progress fires at exactly 324,000 frames (90 emu-minutes),
re-anchors on catches and after council resets; whiteouts/crashes fire on the
3rd; backoff schedule 900/1800/3600/3600 s; rate-limit detection (exit code +
signature, no false positive on transcript text); tail offset survives partial
lines and restarts; snapshot decoding incl. missing-telemetry; rate-window
math; STATUS.md rendering.

Full dexbot-run suite after the harness: **90 passed, 2 failed** = baseline's
74 + 16 new passing, the same two pre-existing planner failures, nothing else
broken.

## Commits (dexbot-run local main; NOT pushed)

```
937937d test(harness): trigger detection, backoff, snapshot/status — synthetic telemetry only
7a3a616 feat(tools): 15-min progress snapshots + STATUS.md dashboard
56c4bc9 feat(supervisor): LLM-free outer loop — bot lifecycle, §4 triggers, council invocation, backoff
234eb7a feat(config): point llm_planner at Claude Sonnet, key via DEXBOT_LLM_API_KEY
cde3a86 feat(mcp): register Codex as the project MCP server (stdio)
3ab0411 docs(baseline): record pytest baseline 74P/2F; name the two drift tests in protocol §9.2
f4a8d31 docs(council): initialize experiment state and record files
```

NOTE: dexbot-run now has a remote `origin`
(github.com/MrMarxz/dexbot-run.git) — added by the human since
SETUP_REPORT_3 recorded "no remotes". Nothing was pushed, per the hard rule.

## Unresolved / honesty over optimism

1. **The permission flag is not named in supervisor/README.md.** Unattended
   orchestrator sessions need Claude Code's permission-bypass flag in
   `DEXBOT_CLAUDE_ARGS`; the setup tooling's safety classifier blocked writing
   the literal flag into the repo (twice), so the README describes it and
   points at `claude --help`. The human must set it before the run —
   sessions without it stall on permission prompts and events never close.
2. **No full council event has ever been fired.** The claude -p path was
   verified with a minimal MCP tool-call session; supervisor logic is
   unit-tested against synthetic telemetry. The first real end-to-end event
   (trigger → pause → council → STATE.md close → resume) has not happened —
   the human should exercise one dry run (section E) before the live run.
3. **Codex tool-call defaults are conservative**: `session_configured` showed
   `approval_policy: on-request`, restricted file system, restricted network.
   For Seat C judgment (reading evidence quoted in prompts, returning
   verdicts) this suffices, but the orchestrator must pass evidence inline in
   the Codex prompt rather than expecting Codex to read repo files itself.
   If Seat C needs more, that's an orchestrator-side prompt discipline, not a
   wiring change.
4. **.claude/settings.local.json is machine-local** (gitignored): on any other
   machine the codex pre-approval must be recreated before headless sessions
   can use the MCP server.
5. **DEXBOT_LLM_API_KEY was never exercised against the real endpoint** (no
   key available to the setup instance). The fallback path (planner
   deterministic default) is what's actually test-covered (M9 tests).
6. Whiteout attribution is coarse: whiteouts count against the most recent
   `start` event in skills.jsonl, which may be a sub-skill (e.g. a restock
   trek) rather than the catch objective that caused the trip.
7. §4.5 convenes a stop-the-world strategic review every 60 minutes even when
   healthy — that is what the protocol mandates; expect roughly hourly bot
   pauses plus one orchestrator session each. Cost accepted by design.
8. The two baseline planner failures stand (SETUP_REPORT_3 §7 item 1 — the
   human decision on syncing the owner's newer planner/data remains open;
   alternatively the council may fix them itself, which §9.2 explicitly
   allows).
9. `council_dryrun.py` runs the orchestrator synchronously with no timeout —
   it is a human-operated tool; Ctrl-C if a session wedges.
10. Carried over from prior phases: original repo uncommitted (reports +
    setup_proof/ + tools/ untracked by instruction silence), four ROM copies,
    Linux-only setup.sh, `a_team_solo.ss1` recipe undocumented.
