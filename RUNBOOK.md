# RUNBOOK.md — launching the autonomous living-dex run

Lives in the ORIGINAL repo (never dexbot-run — it references holdout knowledge).
Operator: the human. After Phase 4 below, the human's job is to watch, not touch.

## Phase 0 — Pre-flight (all must pass; no exceptions)

1. Environment (PowerShell, persistent for the supervisor session):
   - `DEXBOT_CLAUDE_ARGS` includes `--dangerously-skip-permissions`.
   - Do NOT set `ANTHROPIC_API_KEY` (the claude CLI would silently switch to API-key
     billing; the planner shim also strips it defensively).
   - Seat auth: the `claude` CLI is logged in via "Claude account with subscription"
     (cheap probe: `claude -p "Reply with exactly: OK" --model haiku` → OK, rc 0).
     Record the logged-in account. `DEXBOT_LLM_API_KEY` is retired — the L2 planner
     rides the subscription seat through supervisor/planner_shim.py, which the
     supervisor starts/health-checks/stops at http://localhost:8763/v1.
2. Planner smoke test: with the shim running, one real completion through
   http://localhost:8763/v1/chat/completions using config.json's model string.
   Confirm the reply is a real completion, not the deterministic fallback. If the
   CLI rejects the model name, fix config.json to a valid current Sonnet model
   string and re-test.
3. Codex: `codex` responds signed-in; `~/.codex/config.toml` still pins the intended
   GPT-5-class model; spend caps set on BOTH provider accounts. Record the cap values
   here: Anthropic seat-limited / OpenAI seat-limited.
4. Windows: updates paused (date recorded: 8/1/2026), power plan never sleeps, automatic
   restart disabled. UPS status recorded honestly: laptop battery + wifi on UPS.
5. Protocol §4.5 amended to the non-blocking strategic review (human edit, committed).
6. Backup: `git bundle create ..\dexbot-run-prelaunch.bundle --all` inside dexbot-run,
   plus a plain zip of the folder. Cheap insurance before an autonomous agent gets
   write access for days.
7. Remote policy: if github.com/MrMarxz/dexbot-run is used, it is PRIVATE. Pushes are
   made only by the human, or optionally by the supervisor (LLM-free) if remote
   STATUS visibility is wanted: a `status` branch containing only STATUS.md and
   progress.jsonl, pushed after each snapshot. Models never push (protocol §8.3).

## Phase 1 — Dry-run grading (the council's entrance exam)

1. Select 6 stall savestates from `..\quarantine_holdout\_stalls\`, spanning distinct
   failure categories per the original filenames and Dewald's documentation (battle
   wedge, navigation stall, evolution/item stall, post-whiteout, Vs Seeker, one of
   your choice). Record original names + Dewald's diagnosis in a private grading
   sheet (this file's appendix or a spreadsheet — never inside dexbot-run).
2. For each: copy under an opaque scrubbed name (stall_a.ss1 … stall_f.ss1) and run
   `tools/council_dryrun.py`. One at a time; Ctrl-C if a session wedges (no timeout).
3. Grade each DRYRUN event in COUNCIL_LOG.dryrun.md on four axes:
   classification correct? root cause matches Dewald's? proposed fix plausible and
   cited? protocol compliance (Model check lines, citations, exchange cap, no
   forbidden fetches)?
4. Pass bar to proceed: at least 4/6 correct root causes, 6/6 protocol-compliant,
   zero forbidden-scope fetches. Below the bar: fix the orchestration (prompts,
   seat instructions — not the protocol) and re-run with 3 fresh stalls.
5. This is also unresolved item 2's end-to-end test: at least one dry-run must show
   the full chain claude -p → sub-agents → Codex thread → log entry written.

## Phase 2 — Event 0 (route plan; the shakedown event)

1. With the bot NOT running, invoke the orchestrator headlessly in dexbot-run with:
   "EVENT 0 (pre-run, full council, protocol applies): produce ROUTE_PLAN.md — a
   rough FireRed progression guideline (badge order, area-by-area catch-before-
   leaving policy, HM gating, Sevii phases, post-game) from allowed sources, every
   claim cited; and OBTAINABLE.md — the exact obtainable-species list for a solo
   no-trade FireRed run with sources, explicitly listing unobtainables and why.
   OBTAINABLE.md defines 'complete' for GOAL.md. Log as EVENT 0."
2. Human skims both outputs for sanity (pre-run review is allowed; mid-run review is
   not). Check especially: trade-evolution handling, version exclusives, National
   Dex gating. If OBTAINABLE.md is wrong, the finish line is wrong — reject and
   re-run the event with the defect named.

## Phase 3 — Fresh-save launch

1. Confirm dexbot-run STATE.md shows no open event, logs/ clean of prior telemetry,
   no leftover profile/savestate from testing (fresh save per GOAL.md).
2. Take one provider snapshot of the machine state if virtualized; otherwise the
   Phase 0 bundle stands.
3. Start: `.venv\Scripts\python.exe supervisor\supervisor.py` in dexbot-run root.
4. Verify within the first hour: heartbeat lines appearing, first progress.jsonl
   snapshot, STATUS.md rendering, bot advancing past the intro (dex_seen > 0).
   If any fails, stop, fix, restart — the run clock starts only when all four hold.

## Phase 4 — During the run (operator discipline)

- You read STATUS.md, progress.jsonl, COUNCIL_LOG.md, supervisor.log. You touch
  nothing. You answer no session's question — there should never be one.
- Any human intervention = the zero-interaction claim is dead for this attempt.
  If you must intervene (runaway cost, machine failure), log what and why in the
  grading sheet; the run continues as a lower-tier attempt, still worth data.
- Hard stop conditions (pull the plug, no shame): provider spend cap reached; disk
  filling from savestates/logs; the same event PARKED-and-reopened cycling 3+ times
  (protocol loophole found — note it, fix protocol between runs, never during).

## Phase 5 — Post-run analysis (win or lose)

1. Freeze: stop supervisor, bundle the repo, copy logs.
2. Metrics vs Dewald's baseline: dex owned over time (progress.jsonl), stalls
   resolved autonomously / parked / cycled, cost per resolved stall (provider
   dashboards), wall-clock per badge.
3. The protocol's own demand (council doc, evaluation discipline): classify EVERY
   council event as outcome-changing / confirming / noise. That table — not the
   dex number — is the answer to whether cross-model reasoning earned its cost.
4. FINDINGS.md is the council's rediscovery of the game's traps with fresh eyes;
   diff it against Dewald's KNOWN_LIMITATIONS for the write-up.

## Appendix — private grading sheet

Selection made 2026-08-01 by the operator instance. Category spread per Phase 1.1:
post-whiteout (a), Vs Seeker (b), navigation stall (c), evolution/item stall (d),
battle wedge (e), judgment pick (f — the most recent, most layered failure class).
Line references are to this repo's KNOWN_LIMITATIONS.md (KL) and DEVLOG.md (DL)
as of commit ee2a10c.

**SHEET STATUS: DRAFT — grades are the operator instance's draft; the human
ratifies.** Exam ran 2026-08-01 (entries DRYRUN-001…006 in dexbot-run's
COUNCIL_LOG.dryrun.md; per-run transcripts archived under dryrun_exam/).

**Pass-bar tally (RUNBOOK Phase 1.4):** root causes correct **3/6** (d, e, f —
all three RAM-reconstructible wedges: menu, battle, script-box; the three
misses a, b, c are all live-Python-controller freezes whose mechanism the .ss1
cannot carry). Protocol-compliant **6/6** (each entry: full Model check lines,
one Codex thread with consistent threadId, ≤6 exchanges, cited game facts,
disclosed+restored side effects). Forbidden-scope fetches **0**.

**Result: BELOW the bar (needs ≥4/6 root causes) → remediate and re-examine
per Phase 1.4** — fix orchestration/harness, not the protocol, and re-run with
3 fresh stalls. Draft remediation proposal (operator's, for human ratification):
the dry-run withholds evidence the LIVE system always provides — the watchdog's
skills.jsonl tail (interrupted-skill label, stall sample, defer/retry history).
All three misses repeatedly flagged exactly that gap ("not telemetry-confirmed",
"unrecoverable from artifact"), and all three hits were cases where game RAM
alone carried the answer. Remediation: (1) council_dryrun.py should synthesize a
scrubbed skills.jsonl tail (skill label scrubbed to the opaque name, but real
status/sample/history fields) so the dry-run evidence matches live fidelity;
(2) consider pre-approving DRYRUN-003's _dump_stall observability enrichment
(controller_stack / held_buttons / nav_intent) as an early live-run fix — it
closes the same gap class for real events. A re-exam with 3 fresh stalls under
(1) tests what the live council will actually face.

**Standing item for the human (all six entries carry it):** protocol §3 names
Seat B default `claude-opus-5`, but the claude CLI in this harness cannot
produce it — every spawn resolved to `claude-opus-4-8[1m]`, recorded as a
disclosed §11 violation per the invocation's fallback. Before Event 0: either
make Opus 5 available to the CLI, or amend §3 (human edit) to name Opus 4.8.

| Scrubbed name | Original holdout file | Dewald's diagnosis | Council classification | Root cause match? | Fix plausible? | Protocol clean? |
|---|---|---|---|---|---|---|
| stall_a.ss1 | catch_Gastly_234206.ss1 | Post-whiteout wedge inside catch_species: party whited out in Pokémon Tower, handler recovered to the Lavender PC, then the skill made no progress for 30k frames until the watchdog deferred it; a fresh skill start succeeds (planner deferred-retry papers over it); why L47 Blastoise whited out vs L13–25 ghosts is unresolved (KL:39–46, stall 234206 named) | DRYRUN-001 (attempt 2): CODE DEFECT (navigation) — `enter_center` redundantly walks out+back-in when already inside a center; freeze mechanism declared unrecoverable from artifact. Class right (code defect), subsystem wrong. | DRAFT: **No** — the whiteout→recovery→in-skill-wedge chain never surfaced (invisible without telemetry: state shows a healed party at the PC; the dump's skill label was withheld by the scrub) | DRAFT: **Yes** — guard mirrors an existing idiom, all 4 callers verified, Seat C PASS-WITH-CONCERNS after repo verification | DRAFT: **Yes** (attempt 2) — full Model checks (Seat B claude-opus-5 unavailable in harness, violation disclosed per §11 fallback), one Codex thread, 3/6 exchanges, 0 forbidden fetches. Attempt 1 (archived in dryrun_exam/run1_archive) was protocol-broken: Seat C never convened + Seat B mismatch declared "✓" — fixed by preamble amendment, re-run fresh |
| stall_b.ss1 | vs_seeker_leg_133126.ss1 | Vs Seeker rematch income never fires — every lap earns ₽0: registered-item Select silently no-ops in-harness (must fire from bag), post-fire message box waits on a press wait_for_no_script_to_run never delivers, ≥100-step recharge needs the shuttle; even with all three fixed every fire reports "no interested trainers" — suspected per-trainer defeated flags (unbeaten ⇒ rematch-ineligible); the one +₽4.7k lap was first-time ambushes (KL:104–117; DL:148–153, 158–161) | DRYRUN-002: two CODE DEFECTS — (proximate) surfing avatar wedged by surf-blind calculate_path + held-direction walker at a Vermilion dismount tile (button-hold repro: Left no-ops); (strategic) Seagallop ferry absent from warp graph → all Sevii species invisible to missing_catchable. | DRAFT: **No** vs the documented key (Vs Seeker re-arm failure) — council never saw the Vs Seeker angle (no telemetry). Judgment caveat for ratification: the surf-dismount wedge is a VERIFIED property of this exact frozen state (mid-leg), so the answer key (cluster-level mechanism) and the council (this dump's proximate freeze) may both be right at different layers | DRAFT: **Yes** — guarded-generator fail-fast + escalation-flagged ferry subsystem; Seat C verified citations incl. map_path.py:945 and refuted an overbroad coverage claim (driver confirmed + narrowed) | DRAFT: **Yes** — full Model checks (same disclosed Seat B limitation), one Codex thread, 3/6, §5 refutation, sandboxed repros disclosed, 0 forbidden fetches |
| stall_c.ss1 | clear_rocket_hideout_182635.ss1 | Rocket Hideout B1F east corridor: RIGHT-pushing conveyor arrow tiles the tile model reads as 'Normal' (col 0, elev 3), so southbound is one-way blocked, planned Down-paths fail invisibly and walk_carefully re-path-loops until the progress watchdog dumps the stall — this exact file is named in the log; fix direction: dump the raw metatile behavior byte, extend the upstream Spin translation (DL:322; class writeup KL:15–24) | DRYRUN-003: CODE DEFECT (navigation/control-flow) with "mechanism unrecoverable from artifact" as the terminal conclusion; correctly localized to ROCKET_HIDEOUT_B1F (21,18) mid-clear_rocket_hideout with Down blocked; proposed observability enrichment of _dump_stall (controller_stack/held_buttons/nav_intent) + subordinate replay-gated leg guard. | DRAFT: **No** — the conveyor-tile behavior-byte misread was never examined; council attributed the Down block to the barrier and stopped at bounded uncertainty (Seat C ruled that terminal conclusion legitimate). Right neighborhood, mechanism unfound | DRAFT: **Yes** (as scoped) — the observability-first proposal is sound engineering and Seat C PASS'd it explicitly as instrumentation-only; it would not by itself have fixed Dewald's actual bug | DRAFT: **Yes** — full Model checks, one Codex thread, 3/6, numeric refutation of a citation (75× vs ~35 call sites), md5-verified evidence integrity, 0 forbidden fetches |
| stall_d.ss1 | evolve_stones_162313.ss1 | Blind-actuation-loop class during the stone-evolution pass: press-button-until-memory-shows-X with no bailout (shop quantity selector pins at affordable, prompts silently declined by B-mash), multiplied by layered retries (skill × CLI heal-retry × supervisor restart) replaying a deterministic failure — the 32-dump evolve_stones cluster at ~26 s intervals is that churn; fixed same day via press_until + menu stall budget + feasibility-before-actuation, after which the stone pass completed ×6 (DL:24–34; DL:18–20) | DRYRUN-004: CODE DEFECT — unbounded menu-actuation loop: evolve_stones in the Celadon 4F buy menu asked 2× Leaf Stone holding ₽3084 (needs ₽4200); FRLG clamps the quantity selector at the affordable max so the ×02 predicate is unreachable; identified as ALREADY REMEDIATED in current code (wallet clamp + bounded press_until), remediation replay-confirmed; residual unbounded waits flagged. | DRAFT: **YES — exact match** with DL:24–34's blind-actuation-loop class down to the specific wedge (quantity selector pinned at affordable); council reproduced both the pin (TEST 1) and the current-code pass (TEST 2). (Note: the openings.py:173–175 comment documents this wedge, so part of the answer was discoverable in-repo — the reconstruction from RAM was still independent and exact) | DRAFT: **Yes** — sophisticated: no-change for the remediated path + precisely scoped wait_for_task hardening at the 3 unbounded waits; Seat C verified every load-bearing citation; caller-set refutation verified (~19 sites, strengthens) | DRAFT: **Yes** — full Model checks, one Codex thread, 3/6, refutation, md5-verified evidence, 0 forbidden fetches |
| stall_e.ss1 | catch_Krabby_130244.ss1 | Intermittent undriven wild battle: BattleListener attaches no handler (in-process only; fresh process handles the identical trek), leaked navigation inputs then pick RUN, and against Arena Trap the failed-escape message deadlocks the battle beyond recovery (manual A/B cannot advance — verified); listener-gap root cause unfound; this exact file is named as the repro class (KL:91–100) | DRYRUN-005: two chained CODE DEFECTS — non-target wild encounter routed to bare RunAwayStrategy which attempts a Run that Arena Trap permanently blocks ("prevents escape" printed), and upstream handle_battle_action_selection's buttonless else never dismisses that message → 30k battle freeze; battle genuinely unwinnable with this party; fix = escape-aware flee strategy (fail-fast BotModeError) + upstream B-press hardening. | DRAFT: **YES (substantial)** — matches the documented deadlock (RUN chosen vs Arena Trap in Diglett's Cave, battle frozen beyond the strategy layer) and goes deeper (exact controller-callback gap; pret-verified no-turn-consumed trap block). Unmatched nuance: KL's "BattleListener attached no handler" trigger — which Dewald himself left "root cause unfound", and which the council's repro evidence complicates (the deliberate RunAway path produces the same wedge; their B-mash DID advance the callback, vs KL's "manual A/B cannot advance") | DRAFT: **Yes** — PRIMARY strategy fix is necessary-and-sufficient for the repro, SECONDARY explicitly flagged as insufficient alone (livelock, pret-verified); every load-bearing citation repo-verified by Seat C | DRAFT: **Yes** — full Model checks, one Codex thread, 3/6, §5 refutation (escape-item overbreadth), §10 research within allowed scope (pret decomp, cited), md5-verified evidence, 0 forbidden fetches |
| stall_f.ss1 | traverse_victory_road_153133.ss1 | Victory Road live-mode churn cascade: transient early Pallet-fly recovery → re-trek skips Button 3 (scene var already 100) → Strength not re-armed at Button 4 → push no-ops → stall → Pallet-fly → loop; plus navigate_same_level stalls when the push tile is boulder-adjacent, and "route planning budget exceeded" on 1-tile moves because a loaded boulder splits the region (fix: single-map navigate for pushes); headless is deterministic and green, live is not (DL:1059–1067, 1072–1080; the dump family also spans btn1/btn4 moments) | DRYRUN-006: CODE DEFECT (control-flow), defect-class — at VR 3F (33,19), Strength ALREADY active (SYS_USE_STRENGTH set; btn1/2/3 scene vars=100, boulder2=0 → exactly the mid-cascade re-trek state), activate_strength pressed A on the boulder, got the plain "already used STRENGTH" sign instead of the Yes/No prompt, and the unbounded wait_for_yes_no_question can never terminate → 30k wedge; fix = flag-gated bounded confirm_strength_if_prompted() collapsing the story.py duplicate. | DRAFT: **YES** — matches the documented btn4/Strength-re-arm cascade (DL:1064–1065, 1072–1080) down to the scene-var state, the very hang the owner's later "bounded activate_strength" commits chased; also independently surfaced the boulder-adjacent navigate_same_level fragility (DL:1078) as a separate defect. Hang reproduced live (2500+ frames) | DRAFT: **Yes** — flag gate mirrors the game's own branch predicate (pret-cited: flags.h, ClearTempFieldEventData, VR3F warp json); bounded; duplicate collapsed; Seat C supplied the missing citations it demanded | DRAFT: **Yes** — full Model checks (same disclosed Seat B limitation), one Codex thread, 3/6, §5 citation concern raised AND resolved in-entry, md5-verified evidence, 0 forbidden fetches |

### Re-exam selection (Phase 4b, 2026-08-01) — 3 fresh stalls, remediated harness

Selected by the operator instance after both remediations landed (synthesized
watchdog tail in council_dryrun.py, firered-dexbot commit 01cf77c; DRYRUN-003
_dump_stall enrichment, dexbot-run commit bf6b501). ≥2 from the missed class
(live-controller/navigation freezes). Peek-decode of each candidate confirmed
the captured state matches the documented diagnosis before selection. Seat B
occupancy re-probed before the exam: the spawn interface still rejects full
model IDs (aliases only), but alias `opus` now resolves sub-agents to
**claude-opus-5[1m]** — the §3 model (1M-context variant), vs the exam-era
claude-opus-4-8[1m]. Harness tail settings recorded per stall; timestamps in
the synthesized tail are synthesis-time by design (original HHMMSS stamps are
answer-key material and never reach the council).

Original-file md5s (integrity record; originals untouched, copies only):
133200=42debf71ad9346413a72839a357bb725, 133234=fd0bc9c4ae02ff2c6e5e985aa9861247,
133309=9a7c58040c32e30f0fd03af3314e3cf6, 133344=1e97e392be56337764203a3b9abca9b9,
koga_221419=703c72ec1095329830a31038d0581f84, koga_221503=fd8e0c8c9bb26737dc998636cbe51f65,
dunsparce_070531=19a522619697b0bee5f08f272dbd50a8.

| Scrubbed | Original (target) | Tail config | Dewald's diagnosis (answer key) | Class |
|---|---|---|---|---|
| stall_g.ss1 | vs_seeker_leg_133344.ss1, priors 133200/133234/133309 (oldest first) | 4 cycles, no defer record (leg call site prints and returns — planner.py `_earn_by_vs_seeker`) | Vs Seeker income cluster (KL:104–117, DL:148–153): legs of `_earn_by_vs_seeker` wedge — peek shows the avatar pinned at VERMILION (20,24) with money frozen at ₽136 across ALL FOUR dumps ≈35s apart, i.e. the caller re-drove the identical leg into the identical pin. Same family as exam-1 stall_b (133126, the cluster's first dump), whose council verified a surf-dismount held-direction wedge at a Vermilion dismount tile. Cluster-strategic layer (rematches never fire, "no interested trainers", suspected per-trainer defeated flags) is documented but NOT derivable from these artifacts. **Hit bar:** the leg-freeze mechanism at (20,24) PLUS explicit use of the tail's repetition evidence (same-coords/same-money cycles ⇒ blind identical retries, no income). Mere re-cite of DRYRUN-002 without integrating the new telemetry falls short. | missed class (nav/live-controller) |
| stall_h.ss1 | beat_koga_221503.ss1, prior 221419 | 2 cycles, no defer record (gym/story call site) | Cycling Road forced-slide pin (DL:171–195 "Cycling Road pinned the avatar in a state no walker could see", KL:118–125): Route 17 is one continuous "Cycling Road Pull Down" slope; parked against an obstacle the engine keeps `running_state==MOVING` forever, avatar never controllable, upstream walker waits/yields forever with zero input — beat_koga stalled twice at exactly (11,18), ₽4,588 (peek matches both dumps). FIXED in current code: Route 17 legs use walk_carefully with release-on-first-coord-change (+ the faint-counter 120-frame sustained-absence reset, second layer, different moment). **Hit bar:** the forced-slide/held-walker pin mechanism at Route 17 (11,18); recognizing it as since-remediated (à la DRYRUN-004) strengthens. | missed class (nav/live-controller) |
| stall_i.ss1 | catch_Dunsparce_070531.ss1 (no priors — single dump) | 1 cycle, WITH deferred record (catch-loop objective) | Sevii reachability gap (KL:153–161): Three Island Port's Dunsparce grass (32,7) is a warpless area invisible to the warp graph — catch_Dunsparce can sail in but navigation cannot route to the grass; peek shows the dump at THREE_ISLAND_PORT-area map (3,49) coords (12,13), ₽19,972, mid-catch_Dunsparce. Documented fix direction: probe_maze tape from the dock. **Hit bar:** navigation/graph-reachability root cause (target grass unreachable in the modeled graph / plan-fail or pace loop near the dock); naming the warpless-subarea mechanism = exact. | nav/planner (graph reachability) |

**Re-exam pass bar (task directive):** ≥2/3 root causes, 3/3
protocol-compliant, zero forbidden fetches, zero §11 violations (Seat B must
produce claude-opus-5\* occupancy).

**SHEET STATUS: DRAFT — grades are the operator instance's draft; the human
ratifies.** Re-exam ran 2026-08-01 (entries DRYRUN-007/008/009 in dexbot-run's
COUNCIL_LOG.dryrun.md). One aborted attempt preceded DRYRUN-007 and is NOT
counted as an exam item: the `claude -p` background-wait ceiling terminated the
session mid-deliberation at rc=0 with nothing logged (see PREFLIGHT_REPORT_2
§H). It wrote no council-log entry and no cross-run memory, so stall_g was
re-run clean rather than burned.

| Scrubbed | Council diagnosis (DRYRUN-nnn) | Root cause match? | Fix plausible? | Protocol clean? |
|---|---|---|---|---|
| stall_g.ss1 | DRYRUN-007: CODE DEFECT (upstream pokebot-gen3) — check-order bug in `map_path.py`'s `is_tile_accessible`: the surf-dismount `return True` at :947 fires BEFORE the live-object check at :951, routing the surfing avatar onto (19,24) where an uncut Cut-tree object stands; the 20-frame per-step timeout is swallowed by `navigate_to`'s `while True`, which re-plans an identical path from unchanged state until the 30k watchdog fires. Fix = hoist the `blocked_coordinates` guard above the dismount return, via `patches/`. | DRAFT: **YES — exceeds the bar.** Leg-freeze mechanism at (20,24) pinned to the line, verified against the engine's own `CanStopSurfing()` (pret: the dropped conjunct is `GetObjectEventIdByPosition(...) == OBJECT_EVENTS_COUNT`), and reproduced deterministically incl. an in-memory check-order experiment. Repetition evidence explicitly integrated: frame counts exactly 32,000 apart with zero intervening frames, used to rule out NPC-transient/RNG. Explicitly REFINED DRYRUN-002 ("supported in outcome, refined in mechanism") rather than re-citing it. Caveat: caller attributed to a Vermilion rod catch objective (`_shore_tiles`), where the key says `_earn_by_vs_seeker` legs — Seat C forced this down to "plausible caller path, not proven telemetry". Bar was the mechanism, not the caller. | DRAFT: **Yes** — two-line reorder, necessary-and-sufficient, shipped via `patches/` (shown to be the only durable home: `pokebot-gen3/` is gitignored and untracked); §9.3 precedent inside the same function. Seat C narrowed it to dismount-only on decomp evidence. | DRAFT: **Yes** — Seat B `claude-opus-5[1m]` **MATCH** (§11 violation gone), one Codex thread `019fbd8a…`, 4/6 exchanges, §5 refutation raised by Seat C then partly overturned by driver replay, side effects disclosed+restored, savestate md5s intact, 0 forbidden fetches |
| stall_h.ss1 | DRYRUN-008: CODE DEFECT — Route 17's `"Cycling Road Pull Down"` tile type matches none of `map_path.py`'s forced-movement branches, so `forced_movement_to` is never set and `_has_spinners()` structurally cannot see the map; `AvatarFlags.ForcedMove` stays unset (avatar controllable == True) and `running_state` is never `NOT_MOVING`, so four upstream stop-gates can never fire and the walker's turn loop yields forever with zero input. ALREADY REMEDIATED in mainline by `_FORCED_SLOPE_MAPS` + `walk_carefully`. | DRAFT: **YES** — the documented forced-slide pin at Route 17 (11,18), reproduced byte-exactly (R5), and correctly identified as since-remediated (the DRYRUN-004-style strengthener the key called for). **Disclosure caveat:** `navigation.py:813-820`'s comment above the workaround names "the beat_koga 30k-frame stall at (11,18)" — objective name AND coordinates were discoverable in-repo, so the scrub leaked and this is a weaker test of the telemetry remediation than stall_g (cf. the DRYRUN-004 `openings.py:173-175` note in the Phase 1 sheet) | DRAFT: **Yes** — ruled NO runtime change for the demonstrated stall (mainline already passes), raise-only Fix B as separable defence-in-depth via `patches/`, Fix C a ROM-scan assertion. Seat B WITHDREW its own centrepiece fix when the driver's falsifier fired (R12) | DRAFT: **Yes** — Seat B `claude-opus-5[1m]` MATCH, one Codex thread `019fbdd3…`, 5/6 exchanges, side effects disclosed, 0 forbidden fetches. Minor scope note for the human: Seat B fetched pret/**pokeemerald** `global.fieldmap.h` for a shared Gen-3 struct — not in §10's allowed list, not the forbidden category either |
| stall_i.ss1 | DRYRUN-009: two-layer CODE DEFECT — pokebot-gen3 models FRLG geometry as a pure function of the ROM while FRLG swaps layouts at runtime (`setmaplayoutindex`), so THREE ISLE PATH reads as solid rock and its east warp reads "Cave" instead of "South Arrow Warp", leaving the Dunsparce grass with **no incoming warp edge from anywhere in the game**; proximate layer is `catching.py:604` restoring graph-infeasible candidates on the land/spin path. | DRAFT: **YES — exact.** Hit bar was "target grass unreachable in the modeled graph; naming the warpless-subarea mechanism = exact". The council named it and went one level deeper on the cause (runtime layout swap invisible to a ROM-static tile model). Exercised the synthesized `deferred` record path as designed | DRAFT: **Yes** — staged: Fix 1 graph-gated symmetric fast-fail ships first, Fixes 2/3 (observation-aware layout cache + ROM-derived variant-layout table) are the load-bearing repair behind §9 replay with concrete assertions, Fix 4 `story_epoch()` flags | DRAFT: **Yes** — Seat B `claude-opus-5[1m]` MATCH, one Codex thread, 5/6 exchanges, and the only **FAIL→returned→cured** cycle of either exam (Seat C FAILed on citations at exchange 3, Seat B closed it at 4, Seat C cured to PASS-WITH-CONCERNS at 5) — the §7 gate working as designed. 0 forbidden fetches |

**Re-exam tally: root causes correct 3/3, protocol-compliant 3/3, forbidden
fetches 0, §11 violations 0. Pass bar (≥2/3 root causes, 3/3 protocol, 0
fetches, 0 §11) — CLEARED on every axis.**

Remediation feedback for a future exam (not blocking): (1) the synthesized tail
carries only `stall`+`error` records, and DRYRUN-007 correctly noticed a live
run would also emit `start`/`success`/`deferred`/`skipped` — it therefore
refused to read the dump count as a recurrence signature. Adding those record
types would raise fidelity further. (2) The scrub is leaky wherever dexbot-run's
own source comments name historical stalls by objective (`beat_koga` here);
grep the run repo for the original label before selecting a stall.

### Attempt 1

Attempt 1 terminated at T+8.7h, reason: silent stall undetectable due to frame-denominated triggers plus verdictless reviews; EVENT 1 resolved autonomously; dex 6.

### Operator Event

Paused at T+~21h, cause: Seat C provider credit exhaustion; run state intact. And my ruling on the purity question, for the record: refilling a provider account is infrastructure, same category as electricity — the zero-interaction claim survives, provided you touch billing and nothing else.
Fix the money: refill or raise the OpenAI/Codex credit allocation — that is a conversation with whoever owns that workspace at Yknot, this morning. Nothing restarts until the judge can sit.
