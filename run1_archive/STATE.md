# STATE.md — current run state

Read/write for the orchestrator (CLAUDE.md file table). The supervisor parses the
`Open event:` line verbatim: the literal value `none` means no council event is in
flight and the bot may be resumed. Any other value is the ID of the open event.

- Run phase: live run (started 2026-08-01T23:22:16Z); EVENT 1 closed, bot cleared to resume
- Open event: none
- Last closed event: 1 (PASS-WITH-CONCERNS, 4/6 exchanges)
- Events total: 2
- Bot: not running — paused by the supervisor for EVENT 1; resumes on this file showing no open event
- Telemetry offsets: skills.jsonl=87 progress.jsonl=1 (skills.jsonl grew 6→87 during the event: the
  §9.2 regression runs append their own skill records to the live file — see carried concern 9)
- Completion target (DECISIONS.md D1): 170 owned species; primary metric Tier 1 = 125/125
- EVENT 0 deliverables committed: `5a98147` (the log's `Fix:` line reads
  "unavailable" because the files were still untracked when Seat C wrote the
  verdict; the entry is closed and is not amended retroactively)
- EVENT 1 fix committed: `4fb6c16` (stdio hardening; FINDINGS F1). Live-run state was protected
  during the §9.1 replay: it ran against a throwaway profile copy, and `livingdex/current_state.ss1`
  still does not exist — the resume point is the fresh save, unchanged, as it was at the trigger.
- Last updated: 2026-08-02T00:12Z by driver (EVENT 1 close)

## Carried into the next event (EVENT 0 concerns, not yet FINDINGS entries)

Seat C's PASS-WITH-CONCERNS named these as candidate FINDINGS. None has a fix or
commit hash yet, so none was written to FINDINGS.md (§6 requires both). Detail
lives in `OBTAINABLE.md` §7 and `ROUTE_PLAN.md` §6.

1. `data/dependencies.json` annotates 53 of `data/encounters.json`'s 124 encounter
   maps; **71 encounter-bearing maps are unannotated** and `accessible_maps()`
   treats unannotated as inaccessible. The planner cannot currently route to
   Cerulean Cave, Mt. Ember, Victory Road, Tanoby, Sevii 4–7 and more. Blocks the
   ledger from being actionable.
2. Per-map vs per-method HM gating — the structural shape of the two BASELINE.md
   failures. `dependencies.json` gates whole maps; `missing_catchable()` iterates
   per method. Needs a schema change, not a per-map edit.
3. `data/encounters.json["1,122"]` (Altering Cave) records the Smeargle table
   (9 of 9); the reachable table is Zubat (0). Upstream extraction collapses nine
   headers keyed by `(group, number)`.
4. Two annotations under-gated: `"3,49"` (Dunsparce) needs the National-Dex
   `setmaplayoutindex` swap, not just `BADGE08_GET`; Tanoby chambers need
   `FLAG_SYS_UNLOCKED_TANOBY_RUINS`.
5. `pokebot-gen3/modules/pokedex.py` `is_national_dex_enabled` is wrong for FRLG
   (tests Emerald's `nationalMagic`; reads True from frame one).
6. `BASELINE.md`'s recorded pass count is stale — 74 vs the current 120, from three
   test files added after baseline commit `fc60676`. Failure count and identity are
   unchanged. BASELINE.md is READ ONLY to models.
7. The single-Eevee claim (D4) is not exhaustively grepped. Close it before wiring
   breeding automation.
8. Seat C could not run pytest itself — `.venv` points at a missing Python 3.12
   install from the Codex shell's view. Driver-run evidence was accepted instead.
   Fix if it recurs, or Seat C cannot self-serve §9.2 evidence.
   **RESOLVED in EVENT 1** by commit `a055bf3`: Seat C ran `tools\run_tests.cmd`
   itself twice (control `2 failed, 120 passed`; post-fix `2 failed, 136 passed`).

## Carried out of EVENT 1 (concerns, not yet FINDINGS entries)

9. **The §9.2 regression suite writes into the live telemetry the supervisor polls.**
   `logs/skills.jsonl` went 6 → 87 lines purely from pytest (`assemble`, `test_nav_*`
   records). Seat C raised this as its PASS-WITH-CONCERNS item. Today it is harmless —
   every appended record is `start`/`phase`/`success`, and `Watcher.poll_skills`
   (`supervisor/supervisor.py:120-143`) only triggers on `whiteout`/`stall`/`deferred`/
   `advisor_retry` — but a future test that emits any of those would fire a phantom
   council trigger, and the appended `start` records already leave `watcher.objective`
   mislabelled (`test_nav_oaks_lab`) until the bot's next real `start`. Every future
   event that satisfies §9.2 will re-pollute the file. Fix: point the test harness at
   a temp telemetry path.
10. **`run.py` has no top-level exception handler** (Seat A exchange 1, separately
   named; Seat B argued out of scope and Seat C accepted). Any unhandled exception
   still exits rc≠0 — which is currently the supervisor's §4.4 trigger *contract*, so
   this is a deliberate deferral, not an oversight. Reopen only with its own design
   decision and its own §9.1 replay showing a handler cannot poison
   `current_state.ss1` by exiting mid-battle.
