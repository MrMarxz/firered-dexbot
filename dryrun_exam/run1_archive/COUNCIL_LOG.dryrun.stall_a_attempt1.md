# COUNCIL_LOG.dryrun.md — dry-run (diagnose-only) deliberation record

Rehearsals on historical/scrubbed savestates, run by the human-operated council
grading harness. Entries use the COUNCIL_PROTOCOL.md §12 format with event ids
prefixed `DRYRUN-`. Nothing here is implemented: fixes are written proposals only.
This file is separate from the real COUNCIL_LOG.md and carries no run-state weight.

---

## EVENT DRYRUN-001 — 2026-07-31T22:42:49Z
Trigger: §4.1 watchdog_stall — supervisor.poll_skills observed a `status:"stall"`
telemetry record for one skill (objective name scrubbed to `stall_a`). Per
supervisor.py:133-136 + runner.py:388-436 a watchdog_stall = a single skill made
no observable progress (position/money/balls/game-state/party-HP frozen) for
30,000 frames. Evidence: stall_a.ss1, stall_a_state.json, logs/skills.jsonl.
Mode: DIAGNOSE-ONLY dry-run — Seat A and Seat B only; implement nothing.

Seats: A=claude-sonnet-5 (weight 2)  B=claude-opus-4-8[1m] (Opus default, weight 4)
       C=not convened (diagnose-only: no implementation exists for the §9 evidence gate)
Model check: Seat A self-reported "Claude Sonnet 5 (claude-sonnet-5)"; spawned with
  model=sonnet (harness-authoritative, §11). ✓ expected occupancy.
Model check: Seat B self-reported "claude-opus-4-8[1m]"; spawned with model=opus
  (harness-authoritative, §11). ✓ Opus default — NOT escalated to Fable: none of
  §3's escalation triggers held (Seat A classified cleanly; no prior FAIL; the fix
  is a patch to existing functions, not a new subsystem).
Cross-model gate (§2): N/A this event — Seat C not convened (no fix to judge).

Exchanges: 2/6

— Exchange 1 · Seat A (Diagnostician) · classification —
Position: **KB (data/) error compounded by a code defect; primary = KB error.**
Severity **High**; blast radius **systemic**.
Reasoning: `data/dependencies.json (3,41)` = `{requires:[], safe_tile:[38,11]}` — a
map-level gate that is correctly empty for LAND access, but the planner's queue
entry for that map is the *surf* encounter. `dexbot/planner.py::missing_catchable`
gates rod methods on a required bag item (planner.py:123) but applies **no**
capability gate to `surf` (only `_graph_reachable`, i.e. LAND walkability,
planner.py:136). So Psyduck@Route22-surf is emitted with a 100% rate and, per the
sort at planner.py:148, sits permanently at the queue head. Reaching it needs Surf
= HM03 + Soul Badge (Badge 5); memory-state shows BADGE05_GET=False, GOT_HM03=False
→ impossible. Reproduction confirmed the head objective `catch_Psyduck` freezes for
30,000 frames in Lavender PC ((8,0),(11,2)), while an unreachable *land* entry
(`catch_Fearow`) instead RAISES cleanly and defers — a secondary code-level
freeze-vs-defer divergence. Blast radius: ~50 maps in data/encounters.json carry
`surf_encounters`; all are mis-emitted pre-Surf, recurring for the whole
pre-Badge-5 era (high-rate surf entries re-sort to the head after each defer).
Not a rediscovery (FINDINGS.md empty). Overlaps the known BASELINE.md failures
(`test_m6_planner.py::test_planner_queue_covers_pre_brock_species`,
`::test_pre_brock_dex_complete`) — this is their first live runtime manifestation.
Sources: data/dependencies.json (3,41) + hm_field_requirements; data/encounters.json
(3,41 map_name ROUTE22, surf-only Psyduck); dexbot/planner.py:70-76,119-149;
dexbot/catching.py:591,631; runner.py:388-436; supervisor.py:133-136; BASELINE.md;
memory-state (savestate flags/bag). No fix proposed (per role).

— Exchange 2 · Seat B (Fix Designer) · root cause + proposed fix —
Position: **Combination fix — primary planner capability gate + defense-in-depth
skill fail-fast — flips both BASELINE tests without touching Route 22's pre-Brock
land targets or the other 74 tests.** Root cause split confirmed: (primary) surf
method has no capability gate in `missing_catchable`; (secondary) `catch_species`'
fast-fail guard at catching.py:600-604 is gated on `rod_name is not None`, so the
surf path (`rod_name=None`, `feasible=[]`) falls through and loops `navigate_to`
over unreachable water tiles, keeping the frame loop alive with no progress →
30k-frame watchdog trip. Fix:
  • Part 1 (primary; `dexbot/planner.py`): add a required-field-move column to
    `_ENCOUNTER_METHODS` (surf→"Surf"); add `_field_move_usable(move)` reading the
    EXISTING `data/dependencies.json → hm_field_requirements` table (`Surf:
    BADGE05_GET`, verified present alongside Cut/Fly/Strength/Rock Smash/Waterfall)
    and `get_event_flag`; skip a method when its field move's badge isn't earned —
    a sibling of the rod bag-item skip. Gate on the BADGE flag (not party-knows-move)
    to avoid a chicken-and-egg with assemble_party, and leave land (`field_move=None`)
    ungated so Route 22 Mankey/Spearow/Rattata still surface.
  • Part 2 (defense-in-depth; `dexbot/catching.py`): mirror the rod guard with a
    surf fail-fast (`_surf_field_ready()` = badge AND a party member `knows_move`
    "Surf", API pokemon.py:1071), and broaden the :600-604 feasibility guard to
    `rod_name is not None or method == "surf"` so any unreachable water attempt
    RAISES (clean defer) instead of freezing.
Alternatives rejected in writing: (a) edit (3,41) `requires` for surf — rejected,
map-level gate would delete the 3 legitimate pre-Brock LAND targets and fail the
test the other way; per-method requires needs a schema change the KB lacks.
(b) skill fail-fast alone — rejected as insufficient: the 100% Psyduck head still
re-sorts every pass (churn) and the two BASELINE tests would still see it. Kept as
defense-in-depth. (c) a new general capability subsystem — rejected as unjustified
scope/regression surface (and would trip §3 Fable escalation); the existing
`hm_field_requirements` table makes this a patch. (d) delete surf entries from
encounters.json — rejected: destroys correct KB needed at Badge 5 and strands those
species. Predicted evidence for Seat C's §9 gate: replay from the stall savestate →
`"Psyduck" not in missing_catchable()` species and queue head no longer surf; driving
one objective raises owned-species count (Gastly/Doduo/Cubone) with no 30k-frame
watchdog line; regression 74→**76 passed, 0 failed**; diff limited to planner.py +
catching.py (no protocol/telemetry edits). Sources: dexbot/planner.py:70-76,119-149,
559; dexbot/catching.py:542,571-573,591,599-604,631; data/dependencies.json
hm_field_requirements; pokemon.py:1071 knows_move; BASELINE.md §9.2; memory-state.

Verdict: **DIAGNOSIS COMPLETE (dry-run) — no PASS/FAIL rendered.** Seat C's §9
evidence gate (replay + regression + diff) requires an implementation, and the
diagnose-only rules forbid producing one, so no verdict is voted. Recommended
real-run disposition: implement Seat B's combination fix; expected Seat C outcome
**PASS** (replay unblocks the 6 reachable queue entries the reproduction already
showed catching once Psyduck is removed; regression predicted 76/0, flipping the two
BASELINE failures). Seats A and B are in agreement (B built on A's classification).
Vote: none (no verdict). Dissent: none.
Fix: none implemented (diagnose-only). Written proposal recorded above.
Finding: none written (dry-run does not touch FINDINGS.md). Were this a real event,
a FINDING would record: surf/HM-method encounters were emitted by missing_catchable
without a field-move capability gate; root cause = missing per-method gate against
data/dependencies.json hm_field_requirements; fix = planner gate + catch_species
fail-fast; sources as above.

— Driver notes (methodology / reproduction) —
Root cause was reproduced read-only by loading stall_a.ss1 headless (real ROM,
is_test_run) and running dexbot.planner.plan_and_catch_all: catch_Psyduck stalled at
"no observable progress for 30000 frames at ((8,0),(11,2))" — the exact watchdog
condition, same map as the evidence — then deferred, after which catch_Gastly and
catch_Doduo succeeded. Side-effect disclosure: plan_and_catch_all calls
emulator.create_save_state on catch, which writes to the emulator PROFILE dir
(pokebot-gen3/profiles/livingdex/) and is NOT sandboxed by redirecting
dexbot.runner.PROJECT_ROOT. The repro created 3 states/*_caught.ss1 and overwrote
current_state.ss1. Remediated: current_state.ss1 restored to embed the exact
stall_a.ss1 calm-checkpoint bytes (gbAs chunk verified byte-identical, 397312 B);
the 3 stray states deleted; states/ empty. Residual: the gitignored stats.db
encounter counters advanced (inconsequential). The git-tracked repo (all protocol,
code, data, and log files) was left pristine — `git status` clean throughout.
