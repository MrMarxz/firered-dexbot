# PREFLIGHT_REPORT — Phase 4 pre-flight + council dry-run exam

Operator instance, 2026-08-01. Covers RUNBOOK Phase 0 (delegable parts), the
added seat-billed-planner-shim work, and the Phase 1 dry-run exam. No live run
was started; nothing was pushed; holdout originals untouched (copies only).
Honesty over optimism.

## A. Pre-flight checks

### A1. Backups — PASS

From inside dexbot-run (pre-amendment HEAD `6818910`):

- `..\dexbot-run-prelaunch.bundle` — 297,327 B, `git bundle create --all`.
- `..\dexbot-run-prelaunch.zip` — 7,874,818 B, 504 entries, `.git` and
  `roms/firered.gba` included, `.venv/` and `pokebot-gen3/` excluded
  (verified by listing the archive: 0 entries from either).

### A2. Protocol §4.5 amendment + supervisor alignment — PASS

- COUNCIL_PROTOCOL.md §4.5 replaced with the authorized non-blocking text,
  verbatim. Commit `9576ac9` "protocol: human-authorized amendment —
  non-blocking strategic review (§4.5)".
- supervisor.py did NOT match the amended semantics: the hourly review flowed
  into the same branch that pauses the bot and convenes the full council
  (stop-the-world). Fixed in commit `f420a1f`: the supervisor now invokes
  Seat A alone, read-only, WITHOUT pausing (output →
  `logs/review_last_invocation.log`), parses a mandatory
  `REVIEW VERDICT: OK | STALL — <reason>` line from the session's reply, and
  pauses + convenes only on a declared STALL. `OK`, a missing verdict line,
  or a rate-limited session skip to the next hourly review (bot keeps
  running). Six unit tests cover the prompt contract, verdict parsing
  (including "last line wins"), and all three outcomes. supervisor/README.md
  updated to match.

### A3. Environment — PASS with one nuance

- `DEXBOT_CLAUDE_ARGS` (User scope) = `--dangerously-skip-permissions` —
  present, contains the permission-bypass flag. Nuance: processes started
  before the variable was set do not inherit it; the supervisor session must
  be launched from a fresh shell (or set it in-session). The dry-run exam
  imported it explicitly.
- `DEXBOT_LLM_API_KEY` — unset everywhere, and now RETIRED (see D below);
  no longer a blocker.
- `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` — correctly NOT set anywhere
  (process/User/Machine). Subscription billing is safe.
- Seat auth: `claude` CLI 2.1.207 at `C:\Users\marku\.local\bin\claude.exe`,
  headless probe (`claude -p "Reply with exactly: OK" --model haiku`)
  returned `OK`, rc 0, 5.3 s. Logged-in account: **markus@y-knot.io**,
  org **Yknot**, billingType **stripe_subscription** — i.e. "Claude account
  with subscription", as required.

### A4. Planner smoke test — PASS (real completion through the shim)

Via the production code path (`llm_planner.choose_objective` with
config.json's settings; shim started/health-checked/stopped with the
supervisor's own functions):

- config: `base_url=http://localhost:8763/v1`, `model=claude-sonnet-5`,
  timeout 60 s, no bearer key.
- GET /health → 200. One real completion: chose `catch_Abra` from
  [catch_Abra, catch_Pidgey, catch_Caterpie] with a genuine reasoned
  rationale (Abra's first-turn Teleport ⇒ catch on sight), 17.3 s.
  The model string `claude-sonnet-5` was accepted as-is — no config fix
  needed. The reply was NOT the deterministic fallback.

### A5. Codex — PASS

- `codex-cli 0.146.0`; `codex login status` → "Logged in using ChatGPT".
- `~/.codex/config.toml` pins `model = "gpt-5.5"`,
  `model_reasoning_effort = "xhigh"` — the intended GPT-5-class pin, intact.
- dexbot-run `.claude/settings.local.json` pre-approval intact:
  `enableAllProjectMcpServers: true`, `enabledMcpjsonServers: ["codex"]`.
- Bonus: dexbot-run is `trust_level = "trusted"` in codex's own config.

### A6. State cleanliness — PASS (after archiving)

- STATE.md: `Open event: none`, run phase pre-run, bot not running. ✓
- logs/ contained leftovers: `skills.jsonl` (3,350 B of harness-test
  telemetry: assemble_party phases), plus `supervisor.log` +
  `planner_shim.log` lines produced by this session's own smoke test. All
  moved to `..\prelaunch_log_archive\logs\`. logs/ is now empty.
- Leftover runtime profile found and archived:
  `pokebot-gen3\profiles\livingdex\` (metadata.yml + stats.db, no savestate)
  → `..\prelaunch_log_archive\profile\livingdex\`. The live run will now
  create a fresh profile (fresh save per GOAL.md).
- No `fixtures/_stalls/` dumps, no stray STATUS.md, no current_state.ss1.

### A7. dexbot-run remotes (verbatim)

```
origin	https://github.com/MrMarxz/dexbot-run.git (fetch)
origin	https://github.com/MrMarxz/dexbot-run.git (push)
```

Nothing was pushed by this instance. RUNBOOK Phase 0.7's privacy requirement
(repo must be PRIVATE if used) is for the human to confirm on GitHub — not
verifiable from here without hitting the network.

## B. Blockers / items only the human can do

1. **Spend caps** (RUNBOOK Phase 0.3): set/record caps on BOTH provider
   accounts (Anthropic subscription usage is seat-billed now — the relevant
   cap is the subscription tier itself; OpenAI/ChatGPT for Codex). Not
   verifiable from this machine.
2. **Windows prep** (RUNBOOK Phase 0.4): pause updates (record date), power
   plan never-sleep, automatic restart disabled, UPS status recorded. Not
   done by this instance (system-settings changes are the operator's call).
3. **GitHub privacy**: confirm github.com/MrMarxz/dexbot-run is private.
4. **Persistent env**: launch the supervisor from a shell where
   `DEXBOT_CLAUDE_ARGS` is present (User-scope value exists; verify with
   `echo $env:DEXBOT_CLAUDE_ARGS` in the launch shell).
5. **Subscription-limit reset formats**: detection now covers the message
   shapes found in the installed CLI binary (see D); a real limit error was
   not provocable during pre-flight (the probe succeeded). First real
   occurrence should be checked against `logs/supervisor.log` to confirm the
   sleep-until-reset path engaged.
6. **Seat B model (protocol §3 vs harness reality)**: §3 (human-amended
   commit `6818910`) names Seat B default `claude-opus-5`, but the claude CLI
   on this machine cannot produce it — every sub-agent spawn resolves to
   `claude-opus-4-8[1m]`. All six exam entries carry this as a disclosed §11
   violation. Before Event 0: make Opus 5 available to the CLI (check
   subscription tier / CLI version), or amend §3 by human edit to name
   Opus 4.8. Left as-is, every live event will be technically §11-invalid.
7. **Exam verdict**: the dry-run exam came in below the RUNBOOK pass bar
   (3/6 root causes; details in C) — the recommendation is remediate +
   re-examine with 3 fresh stalls, and the remediation itself (dry-run
   telemetry fidelity) needs your sign-off since it touches the exam design.

## C. Dry-run exam (RUNBOOK Phase 1)

Six stalls selected from the holdout for category spread (originals untouched —
copies only, no .png sidecars, scrubbed names stall_a…f). Answer key + full
draft grades: RUNBOOK.md appendix (this repo). Official council entries:
DRYRUN-001…006 in dexbot-run's COUNCIL_LOG.dryrun.md (untracked). Per-run
transcripts/invocations/state summaries: dryrun_exam/<stall>_run/ (this repo).

### Chain verification (step 11) and the one plumbing fix

stall_a's FIRST attempt broke the chain two ways: the driver read the
diagnose-only preamble's "Run Seat A and Seat B" as excluding Seat C entirely
(no Codex thread), and spawned Seat B via the bare `opus` alias, which resolved
to claude-opus-4-8[1m] while the human-amended §3 requires claude-opus-5 — and
declared it "✓ Opus default" against the outdated table. Per the task's
step-11 rule, I fixed ORCHESTRATION PLUMBING ONLY — tools/council_dryrun.py's
DIAGNOSE_ONLY_PREAMBLE (this repo; COUNCIL_PROTOCOL.md untouched): all three
seats convened with Seat C judging the WRITTEN proposal over one recorded Codex
thread; explicit full §3 model IDs with a verified-fallback rule when the spawn
interface can't produce them; an explicit leave-no-side-effects rule for
diagnostic reproductions. Attempt-1 evidence archived (dryrun_exam/run1_archive;
COUNCIL_LOG.dryrun.md reset to header before the fresh re-run so the re-run
could not read attempt 1's diagnosis). All six official runs then passed chain
verification: complete §12-format entries, Model check lines for every seat,
exchanges ≤6 (3/6 in all six), citations on game facts (Seat C repo-verified
the load-bearing ones every time), one Codex threadId per event used across
turns, zero forbidden-scope fetches in any transcript (grep of every
transcript + log for the upstream repo/author: 0 hits).

### Results

| Stall | Category | Council diagnosis (DRYRUN-nnn) | Root cause vs Dewald | Fix plausible+cited | Protocol |
|---|---|---|---|---|---|
| a | post-whiteout | enter_center redundant exit/re-entry; mechanism "unrecoverable from artifact" (001) | **Miss** — whiteout chain invisible without telemetry | Yes | Clean |
| b | Vs Seeker | surf-dismount held-direction wedge + Sevii ferry graph-unreachability (002) | **Miss** vs documented key (see caveat) | Yes | Clean |
| c | navigation | right neighborhood (B1F, Down blocked), declared mechanism unrecoverable; observability-first proposal (003) | **Miss** — conveyor-tile misread unfound | Yes (as scoped) | Clean |
| d | evolution/item | Leaf-Stone wallet-clamp menu wedge, already-remediated, residual waits flagged (004) | **HIT — exact** | Yes | Clean |
| e | battle wedge | Arena Trap blocked-Run + undismissed message freeze; unwinnable battle fail-fast (005) | **HIT — substantial** | Yes | Clean |
| f | judgment (VR churn) | Strength-already-active sign wedge in unbounded Yes/No wait at btn4; duplicate collapsed (006) | **HIT** | Yes | Clean |

Caveat for ratification (stall_b): the council's surf-dismount wedge is a
verified property of that exact frozen state (button-hold repro: Left no-ops
while surfing); Dewald's documented diagnosis describes the CLUSTER's strategic
failure (rematches never fire). Both may be true at different layers — the
human may choose to grade it a partial.

### Pass bar and recommendation

Tally: **3/6 root causes** (bar: ≥4/6), **6/6 protocol-compliant**, **0
forbidden fetches** → **BELOW THE BAR. Recommendation: remediate and
re-examine with 3 fresh stalls (RUNBOOK Phase 1.4) — do NOT proceed to
Event 0 yet.**

The failure pattern is diagnostic, not random: all three hits are wedges whose
mechanism lives in game RAM (menu task state, battle controller callbacks, an
open script message box) — reconstructible from the .ss1; all three misses are
live-Python-controller freezes (nav generator/held-button state) that a
savestate cannot carry, AND the dry-run harness withholds the telemetry the
live system always provides (the watchdog's skills.jsonl tail with the
interrupted-skill label, stall sample, and defer history). The councils
themselves flagged this repeatedly and correctly ("not telemetry-confirmed",
"unrecoverable from artifact" — a conclusion Seat C explicitly ruled
legitimate). Remediation before re-exam: (1) council_dryrun.py synthesizes a
scrubbed-label skills.jsonl tail so dry-run evidence matches live fidelity;
(2) consider pre-approving DRYRUN-003's _dump_stall observability enrichment
(controller_stack/held_buttons/nav_intent) as an early live fix — the council
independently designed the exact instrumentation that would let it solve the
class it missed. Quality signals worth noting for the writeup: every event
produced genuine cross-model challenge (Seat C issued specific §5 refutations
in 5 of 6 events, two of which the driver then verified and extended), all
side effects were disclosed and restored (md5-verified evidence integrity),
and the sessions built their own cross-run memory (e.g.
`repro-writes-profile-dir`, `stall-ss1-omits-controller-state`).

### Time/cost observations

Official runs (wall-clock): a=24.3 min, b=36.2 min, c=26.8 min, d=24.5 min,
e=41.3 min, f=37.2 min — total ≈3.2 h for six events, plus 33 min for the
discarded attempt 1. Token counts are not exposed by `claude -p` output;
subscription usage (not API dollars) absorbed all of it — no usage-limit
error was hit during ~4 h of continuous council sessions. Exchanges never
exceeded 3/6; entries are long but log-only. Expect a live council event to
land in the same 25–40 min band before implementation/replay work.

### Post-exam cleanliness (re-verified)

logs/ empty; no livingdex profile (each session removed its own, and I
re-checked after every run); dexbot-run working tree clean except the
untracked COUNCIL_LOG.dryrun.md (the exam record — left in place
deliberately); holdout originals byte-intact (md5 spot-check matches the
drivers' recorded hashes); STATE.md still `Open event: none`.

## D. Added task — seat-billed planner shim (dexbot-run commits)

1. **`supervisor/planner_shim.py`** (commit `78c1042`): stdlib-only localhost
   HTTP server exposing exactly the OpenAI chat-completions surface
   `dexbot/llm_planner.py` calls (`POST /v1/chat/completions`, plus
   `GET /health`). Each request → `claude -p --model <request model>` with
   the prompt on stdin, run in an empty scratch cwd (no repo context leaks
   into completions), `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` stripped
   from the child env (subscription billing cannot be silently bypassed).
   Any CLI failure — nonzero exit (usage window exhausted), timeout, empty
   output — returns non-200; `llm_planner` treats that as a clean failure
   and its deterministic fallback engages (bot keeps playing). config.json:
   `base_url → http://localhost:8763/v1`, `api_key_env: ""` (no key),
   `timeout_seconds 20→60` (CLI latency; smoke test measured 17.3 s).
   The supervisor starts the shim at boot (port parsed from config.json),
   restarts it on death or failed health check (heartbeat cadence), stops it
   on exit. 10 unit tests incl. loopback end-to-end proof of both the
   completion path and the clean-fallback path through the real llm_planner.
2. **Subscription-limit awareness** (commit `6fce9c8`): `rate_limited()`
   extended with the exact message vocabulary of the installed claude CLI
   binary v2.1.207 (string-dumped, not guessed): "You've hit your
   <session/weekly/Sonnet/Opus/usage credit/monthly spend> limit",
   "Out of usage credits", "credit balance too low". A cheap probe
   invocation verified CLI behavior (account not at limit ⇒ real limit
   output not observable; formats sourced from the binary itself, which also
   shows resets arrive as epoch seconds via `anthropic-ratelimit-unified-reset`
   and are rendered "resets 3pm" / "resets Aug 1, 3:30pm").
   `usage_limit_reset_epoch()` parses epoch / ISO-8601 / human-clock reset
   statements; when a reset time is stated, `run_council` sleeps until
   reset + 2 minutes; otherwise the existing 15→30→60 min backoff is
   unchanged. Both paths unit-tested with synthetic error text.
3. **DEXBOT_LLM_API_KEY retired** (commit `fc8095d` + this repo's RUNBOOK
   update): removed from config.json and supervisor/README.md; RUNBOOK
   Phase 0 items 1–2 rewritten (seat-auth check + shim smoke test). The
   seat-auth requirement is documented in supervisor/README.md: the CLI must
   be logged in via "Claude account with subscription" before launch.
   Logged-in account verified and reported (A3).

### dexbot-run test suite after all changes

**112 passed, 2 failed** — the two failures are exactly the recorded
baseline failures (`test_planner_queue_covers_pre_brock_species`,
`test_pre_brock_dex_complete`, the Psyduck planner/KB drift named in
BASELINE.md §9.2). Nothing new broken. New totals: 74 baseline + 28
supervisor-harness (16 existing + 6 review + 6 limit) + 10 shim.

### dexbot-run commits this session (local main, NOT pushed)

```
fc8095d docs(supervisor): retire DEXBOT_LLM_API_KEY — document planner shim + subscription seat-auth requirement and reset-aware backoff
6fce9c8 feat(supervisor): subscription-limit awareness — sleep to stated reset + 2 min
78c1042 feat(supervisor): seat-billed planner shim — llm_planner now runs on the subscription
f420a1f fix(supervisor): align §4.5 review path with amended protocol — non-blocking
9576ac9 protocol: human-authorized amendment — non-blocking strategic review (§4.5)
```
