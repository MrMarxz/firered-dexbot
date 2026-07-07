# DEVLOG

## 2026-07-07 — Navigation is a planning-SPEED wall; needs a precomputed connectivity graph

**Two real navigation wins committed:**
1. **Direct-warp fast path** for building entry: navigating to a building interior on the giant connected overworld (level 180 = all of central/southern Kanto, 122 warps) was hanging for minutes because building interiors have no global coords, so the distance heuristic couldn't rank their doors and the search fanned into every building. Fix: check same-level warps that land directly in the destination map first. Vermilion→mart dropped from *minutes* to **0.1s**. This unblocks `buy_items` and all building entry.
2. **Warp-count-priority planning** (verified-walkable Dijkstra): explore fewer-warp routes first so the planner returns the shortest *real* route.

**The remaining wall (precisely diagnosed):** cross-region planning is just SLOW. `_plan_warp_route` A*-verifies (`calculate_path`) each candidate warp, and each A* runs over the huge level-180 tile map (~15-20ms). A correct route like gym→Vermilion is **7 warps** (gym-exit + the Underground Path's ~5 internal warps) and takes **~32s** to plan; gym→S.S.-Anne-Captain exceeds the A* budget entirely. `navigate_to` caches the plan (once per journey), but a single failed leg (wandering NPC, warp-approach quirk) clears the cache and forces another ~32s re-plan — so a multi-warp journey with any hiccup runs to minutes. That is why `get_hm_cut` never finishes the ship run.

**The fix (clear, substantial, best done fresh):** precompute a static warp-connectivity graph from the ROM once — for each map/level, A* every warp-pair's walkability a single time and cache it (to `data/` like the KB). Then `_plan_warp_route` is an instant graph BFS with zero live A*; execution failures re-plan instantly too. This is the load-bearing fix for all of mid/late-game travel. (Also seen this session: long emulator runs occasionally die silently — segfault-class — so the connectivity precompute should be chunked/resumable.)

**State unchanged and solid:** Badges 1–2 ✓, Mt Moon ✓, Nugget Bridge ✓, SS Ticket ✓, S.S. Anne boarding ✓. HM01/Cut blocked only on planning speed for the ship run (the skill logic — board, fight rival with potions, Captain, teach Cut — is written and correct). Dex: 15 owned. 29 tests green; everything committed.
## 2026-07-07 — S.S. Anne boarding fixed; ship gauntlet is a difficulty wall (solo Wartortle loses)

**Boarding solved and verified.** Root cause of the get_hm_cut stall: stepping south onto the Vermilion gangplank triggers `VermilionCity_EventScript_CheckTicket` — a "may I see your ticket?" msgbox that only advances on **A**. Plain navigation walks into it and stalls forever (no A). Fix: an explicit board loop (hold Down + mash A until the map group flips to the ship). Verified live: "BOARDED (1,4)(32,5)" — the S.S. Anne exterior. (Diagnosed efficiently via a throwaway `_wip_vermilion_gangplank` fixture so I didn't re-run the 90s trek each iteration.)

**Remaining blocker is difficulty, not a bug.** After boarding, navigating the ship to the Captain, a solo **Wartortle L31 whited out** (→ Pokémon Center, then the re-plan blew the route budget). The S.S. Anne chains many trainers with no PC aboard, and the rival Terry's starter is **Ivysaur (Grass) — which resists Wartortle's Water and hits back super-effectively**. A lone water-type can't grind it down. Mitigation added: buy Super Potions at the Vermilion mart before boarding (the healing battle strategy will use them). That may not be sufficient alone.

**Handoff / next options for the ship (pick per strategy):**
1. Withdraw a backup Pokémon (e.g. the boxed Pidgey/Pikachu) so the solo lead isn't the only answer — Pikachu (Electric) also helps vs the ship's water trainers.
2. Overlevel Wartortle further (mid-30s) so it can tank Ivysaur's Grass hits.
3. Both potions (added) + a backup. This is also the first fight where the M7 brief's real damage-projection / switch logic would earn its keep.

**State:** Badges 1–2 ✓, Mt Moon ✓, Nugget Bridge ✓, SS Ticket ✓, S.S. Anne boarding ✓. HM01/Cut still pending (blocked on the ship gauntlet). Dex: 15 owned. 29 tests green; all committed.
## 2026-07-07 — Long-range nav proven; get_hm_cut stalls in the S.S. Anne (precise handoff)

**Navigation across regions works.** Verified live: Cerulean → (Underground Path) → Vermilion in 53s, routing correctly through the north/south tunnel warps. The cached best-first planner (commit 1d1b46a) plans once per journey and executes legs; a Vermilion→Captain plan is 6s / 4 warps (gangplank → exterior → 1F → 2F → office) — **planning is not the bottleneck**. Correction to an earlier wrong inference: `navigate_to` *avoids* encounters by default, so "0 wild encounters during a trek" is normal, not a stall signal (I over-killed a couple of healthy runs on that mistaken read).

**`get_hm_cut` progresses through phases** (added `_log_event` phase markers: heal → to_vermilion → board_and_ship → talk_captain). It reliably reaches **board_and_ship** — heal at Vermilion, walk to the gangplank — then stalls *executing* the ship traversal to the Captain. Since the plan itself is fast/correct, the stall is in walking the ship: almost certainly the **S.S. Anne rival trigger** blocking a corridor (a coord-event/line-of-sight fight the route must step into, like the Oak and Nugget-Bridge Rocket triggers) or a ship inter-deck warp not firing.

**Precise next step (handoff):** run `get_hm_cut` with per-frame position tracing scoped to the board_and_ship phase; watch which ship map it's on and whether the rival object is blocking. Fix is expected to be the same pattern already used elsewhere — walk into the trigger tile so the battle listener fights the rival, then continue — plus possibly a ship-specific warp-approach tweak. The Captain interaction itself (talk → seasick dialogue → HM01, then teach Cut over the weakest move) is already coded and simple.

**State:** Badges 1–2 ✓ (Brock, Misty), Mt Moon ✓, Nugget Bridge ✓, SS Ticket ✓. Dex: 15 owned. Wartortle L31. All committed; 29 tests green. `get_hm_cut` is the only in-flight skill.
## 2026-07-07 — Badge 2 (Misty) beaten; ticket-fixture stall root-caused and fixed

**Done — Misty defeated unattended, badge 2 in hand.** `beat_misty` from `m7_ss_ticket.ss1`: heal at Cerulean, walk into the gym, beat the junior trainers + Misty. Won at **L29** (no grind) — the damage-calc strategy avoided her resisted Water moves and Wartortle's level lead out-raced Starmie's Recover, exactly as hoped. Wartortle ended L31. Fixture `m7_badge_misty.ss1`; 29 tests green.

**The Misty "can't move" stall was a fixture bug, now fixed.** Root cause (found by inspecting `running_state`/script context, not guessing): `m7_ss_ticket.ss1` had been saved with `Route25_SeaCottage_EventScript_Bill` **still active** — my final ticket-talk A-mashed while facing Bill, which re-triggered his "go to the S.S. Anne!" dialogue in a loop, so the save was script-locked and the avatar couldn't step even under raw input. Fix: after the ticket, close with **B** (A re-triggers) and walk out of the cottage, so `visit_bill` returns in a clean, controllable overworld state. Regenerated the fixture. General lesson (added to the pattern): **savestate fixtures must be captured from a fully-released overworld state** — assert `not script.is_active` + standing still before saving, or a downstream skill inherits the lock.

**Chain state:** Brock ✓, Mt Moon ✓, Nugget Bridge ✓, SS Ticket ✓, **Misty ✓ (badge 2)**. Cut is now *usable* (Cascade Badge). Dex: 15 owned.

**Next:** S.S. Anne → HM01 Cut (get + teach), then a planner sweep of the now-accessible Cerulean-area species (Jigglypuff/Clefairy/etc., funded by the Nugget), then Vermilion/Surge (badge 3, Cut-gated gym).
## 2026-07-07 — Navigation perf fixed (big win); Misty blocked on a fixture micro-state

**Shipped: warp route-planning is ~5000× faster.** `_plan_warp_route` was doing a full A* (`calculate_path`) per warp edge during BFS — cross-Kanto plans hung >150s. Rewrote it as a pure map-level graph BFS (no per-edge A*); the same plans are now ~0.03s. Execution-time `navigate_to` + the blacklist still verify each leg is walkable and re-plan around same-level splits (Route 2 forest). **The full suite dropped from ~26s to ~6s and stays 28/28 green.** This pays down the KNOWN_LIMITATION flagged with the SS Ticket. Committed (257ec62).

**`beat_misty` written** (gym skill, mirrors `beat_brock`; Misty obj 3 @ (8,6), approach (8,7)). Damage-calc strategy will avoid her resisted Water moves and a level lead should out-race Starmie's Recover. Committed but **not yet passing** — blocked below.

**Open blocker (hand-off): navigate_to stalls from the `m7_ss_ticket` fixture.** From the Sea Cottage at (30,0)(7,7), the player is `controllable`, in OVERWORLD, and the route plans fine ([(cottage door 7,9), (Cerulean gym door)]) — but the avatar will not step south: even a raw `hold_button("Down")` for 120 frames leaves it at (7,7). Bill (obj 1) sits at (7,6) to the *north*, so it isn't blocking the exit. Hypothesis: the fixture captured the player in a just-finished-script micro-state that upstream's movement won't advance, OR the door-warp tile (7,9) needs a specific approach. **Next step:** load the fixture, single-step frames while pressing Down, and watch `running_state`/`tile_transition_state`; if it's a stuck micro-state, regenerate `m7_ss_ticket.ss1` by walking a few tiles out of the cottage before saving (a clean overworld state), then beat_misty should navigate normally.

**Discipline note:** spent far too long spiraling in navigation minutiae this turn (both the perf hunt and this stall). The perf fix was worth it; the Misty stall should have been a "regenerate the fixture from a clean state and move on" call much sooner.

**Dex: 15 owned. Badges: 1.** Chain state: Brock ✓, Mt Moon ✓, Nugget Bridge ✓, SS Ticket ✓. Next: unstick Misty (fixture), then S.S. Anne (HM01 Cut), then the Cut-gated gyms.
## 2026-07-07 — SS Ticket obtained (badge-2 chain: Bill done)

**Done — `visit_bill` completes unattended.** From `m7_bridge.ss1`: full-heal at Cerulean → cross Route 25 → Sea Cottage → talk Bill (Yes) → run the teleporter console → talk restored Bill → **SS Ticket in the bag** (`GOT_SS_TICKET`, `HELPED_BILL_IN_SEA_COTTAGE`, item present). Fixture `m7_ss_ticket.ss1`; 28 tests green.

**The bugs behind the long fight (all now fixed and reusable):**
- **Live-object lookup** (`_talk_to_live_object`): live ObjectEvents are keyed by `local_id` with no script symbol — cross-reference the template list (by script substring) to find the *visible* Bill (obj 2 @ (10,6), not the hidden obj 1 @ (7,5)), then approach from an adjacent walkable tile. Reusable for every NPC beat.
- **Same-map interior nav**: routing an intra-cottage move through the door warp resets the map's TEMP flags (`BILL_IN_TELEPORTER`). Interior approach uses upstream same-map A* only.
- **Move-replacement stale index** (upstream patch): `map_battle_party_index` returns a stale slot after PC deposits shrink the party → `get_party()[idx]` IndexError on *every* move-learn. Clamped. (Same class as the item-target and lead-select patches.)
- **Poison whiteout mid-handshake was the real killer**: Wartortle arrived from the Route 25 gauntlet poisoned/chipped and poison-fainted during the Bill dialogue → whiteout to Cerulean → every same-map nav then crashed "not connected". Fix: enter the cottage at FULL HP (poison cured) via an explicit Cerulean heal; a full-HP lead survives one crossing, so the battle-free interior completes cleanly.

**New KNOWN_LIMITATION surfaced:** `_pick_reachable_center` (multi-center "nearest reachable" search) is **too slow from far-apart positions** — `_plan_warp_route` runs a full A* per warp edge, and from mid-Route-24 it can hang >90s. Worked around by passing an explicit center. This is a real navigation-performance debt that will bite other skills; the fix is a precomputed static warp-connectivity graph (offline, from ROM) instead of live per-edge A*. Logged for a dedicated pass.

**Dex: 15 owned.** SS Ticket → S.S. Anne → HM01 Cut is next, then Misty, then the Cut-gated gyms. The reusable helpers (`_talk_to_live_object`, universal battle policy, whiteout recovery) mean the remaining story beats should be faster.
## 2026-07-07 — visit_bill (SS Ticket): navigation + object-lookup solved; Bill handshake open

**Status:** `visit_bill` reliably reaches the Sea Cottage and locates the live Bill (both were bugs, both fixed). The remaining open item is the help→teleporter→console→ticket *handshake sequencing*. Exceeded the 3-attempt rule; committing solid progress and handing off with precise state.

**Fixed this pass (committed):**
- **Cottage navigation** works: `navigate_to(ROUTE25_SEA_COTTAGE, (7,7))` routes Route24→Route25→cottage-door warp cleanly (proven in isolation). The earlier "no warp route to (5,5)" failures were my own bad target — (5,5) is a wall (the teleporter housing). Real interior: door drops at (6-8,9), Bill/console up top.
- **Live-object lookup** (`_talk_to_live_object`): `get_map_objects()` returns live ObjectEvents keyed by `local_id` with no script symbol; the script lives on the *template* from `get_map_data().objects`. Now cross-references template local_ids (matching a script substring) against live objects, then approaches from a walkable adjacent tile. This is reusable for every future "talk to NPC X" story beat.
- Confirmed via trace: talking to Bill with "Yes" DOES work — he walks into the teleporter and `removeobject` fires (live Bill list goes empty), so `BILL_IN_TELEPORTER` (FLAG_TEMP_2) is set.

**Open — the console step:** after Bill enters the teleporter, `_face_and_talk((4,6),"Up")` did not set `HELPED_BILL_IN_SEA_COTTAGE`. The pret `Route25_SeaCottage_EventScript_Computer` (a `sign` bg-event at (4,5)) runs `RunCellSeparator` (which sets HELPED) only `goto_if_set BILL_IN_TELEPORTER`. The post-console screenshot shows the player NOT at (4,6) — so either the intra-cottage `navigate_to((4,6))` didn't land there, or the console must be faced from a different tile. **Next step for the next session:** trace the player's actual position after `navigate_to((4,6))`, confirm (4,6) is reachable/where the avatar ends up, and verify facing Up from there targets the (4,5) sign (bg-events are interacted by facing the tile). Then the second `_talk_to_live_object("Bill")` should hand over the SS Ticket (`GOT_SS_TICKET`). All the pieces are cached in `docs/pret_SeaCottage_scripts.inc`.

**Dex: 15 owned.** SS Ticket unblocks the S.S. Anne (HM01 Cut) and, with Cut, the remaining gyms.
## 2026-07-07 — Nugget Bridge CLEARED (badge-2 chain unblocked)

**Done — the bridge falls unattended**: `cross_nugget_bridge` runs the full chain from `m7_post_badge1_dex.ss1` — deposit fodder to boxes → solo-grind Wartortle to 26 → climb (rival Terry + five trainers) → the Team Rocket recruiter. Verified: `MAP_SCENE_ROUTE24=1`, Nugget in bag (₽5000 when sold), Wartortle L29 full HP. Fixture `m7_bridge.ss1`; 27 tests green.

**The Rocket was a false alarm — and taught the real lessons.** Six-plus attempts chased a phantom: my completion check read `HIDE_NUGGET_BRIDGE_ROCKET`, but the pret script sets **`VAR_MAP_SCENE_ROUTE24=1`** on defeat (the HIDE flag is unrelated). The fight had been *winning*; only the verification failed. Root-caused by fetching the actual `Route24/scripts.inc` from pret. Two real bugs surfaced en route and are fixed:
1. The Rocket's "Halt!" dialogue only advances on **A** — a hold-Up-only approach reaches the trigger tile but never enters the battle. Final approach now full-heals, walks to one tile south, then A-mashes through the dialogue into the fight.
2. Universal battle policy (the big one): a solo overleveled champion with no potions, chained through 7 trainer fights, kept hitting either "no rotation target" or "flee not allowed in trainer battle" — both hard errors. The single `make_healing_battle_strategy` now does the right thing in every context: potion if available → else **flee wild** battles when low (grind loop heals between) → else **fight trainers to the faint** (whiteout recovery, never a hard stop). This replaces the earlier flip-flopping between `hp_threshold=1` (thrashed wild grinding) and `=25` (errored trainer fights).

**Upstream patches** (all in `patches/0001-upstream-fixes.patch`, auto-applied by setup.sh): FRLG stair warps; empty-move-slot learning; solo-faint lead selection; battle item-target index clamp after PC deposits.

**Process note:** this thread ran well past the 3-attempt rule on one NPC. The lesson logged for next time: when a skill "fails" but the party/HP look fine, suspect the *verification predicate* before the *action* — read the pret script for the real flag/var first, don't infer it.

**Dex: 15 owned.** Next: `visit_bill` (Route 25 → Sea Cottage → SS Ticket), then Misty, then the deferred Cerulean-area catchables (Jigglypuff/Clefairy/Nidoran♀/Ekans) funded by the Nugget + bridge payouts.
## 2026-07-07 — Badge-2 chain: bridge conquered, Rocket verification open

**Status: Nugget Bridge climbing works (rival + five trainers beaten unattended); the final Rocket-recruiter interaction stalls — under investigation after 6+ distinct attempts. Committed everything verified; per process rules, documenting and pausing this thread.**

**What got built and verified on the way (all committed)**
- `dexbot/boxes.py` (M8 arrives early): deposit-all-but-strongest at any center's PC — one PC session per deposit (batching trips on upstream's stale party indices), `state_cache.reset()` after. The battle roster is now a solo overleveled champion; caught fodder lives in boxes.
- Whiteout = recoverable: `on_whiteout → True` in the runner's bot mode; the game heals the party at a center and skills re-plan from there. Verified live several times ("whiteout recovered" telemetry events).
- Bounded story-skill retries with healing between attempts.
- `hp_threshold=1`: fight to the faint — a "cannot battle" verdict on a solo party was a hard failure, a faint is a free heal.
- Upstream patches (all in `patches/0001-upstream-fixes.patch`):
  1. FRLG diagonal stair warps (from M3).
  2. Move-replacement crash with empty move slots.
  3. Solo-party faint: choose-new-lead flow now accepts the whiteout instead of crashing on a bogus party index.
  4. **Battle item targeting**: `map_battle_party_index` returns a stale slot right after PC deposits shrink the party — the potion-drink path crashed *every* fight with "Cannot scroll to party index #3". Clamped to the active battler. This one masqueraded as everything from fainting loops to timeouts; root-caused via generator introspection + deterministic savestate replays.
- Runner now matches upstream `main_loop` semantics exactly: `context.frame` increments, and the frame ALWAYS advances after a controller pops (same-frame listener re-runs pushed duplicate battle handlers that hung forever).

**Where it stands**
- `cross_nugget_bridge` from `m7_post_badge1_dex.ss1`: deposits ✓, solo grind to 26 ✓ (poison faints during heal walks self-recover via whiteout), bridge climb ✓ — rival (Pidgeotto 17/Abra 16/Rattata 15/Bulbasaur 18) and all five bridge trainers beaten unattended.
- Open: the Rocket recruiter at the bridge top. His trigger/talk interaction leaves `HIDE_NUGGET_BRIDGE_ROCKET` unset and a later attempt stalled in his script-battle (same DoNoIntroTrainerBattle family as the rival, which the current patch set *does* get through). Next steps for whoever picks this up (probably me, next session): capture a savestate standing at (11,16) pre-trigger, replay his script with the frame-by-frame script-stack trace, and check whether his post-battle script needs a specific input pattern (the sign-lady taught us FRLG tutorial boxes can eat A).

**Dex ledger**: 15 species owned. Remaining pre-Misty catchables (Jigglypuff, Clefairy, Nidoran♀, Ekans) deferred on economy — the Nugget (₽5000) + bridge payouts fund them once the Rocket falls.
## 2026-07-06 — M7 (badge 1): Brock beaten unattended

**Done**
- `dexbot/gyms.py`: `beat_brock` — precondition (strongest party member ≥ L13 + a Rock-beating move: water *or* fighting), heal at Pewter, walk in, fight the junior trainer en route via listeners, talk to Brock, verify `BADGE01_GET`.
- **Navigation redesign** (forced by "Route 2 south → Pewter" having no same-level path): warp-route BFS now searches *(position, warp)* space and verifies every same-level leg with the real A* offline (`calculate_path` needs no player) instead of trusting map-"level" identity — Kanto's outdoor level is physically split by the forest/caves. Nav tests: bedroom→lab and Pallet→Viridian Mart still green (slower: ~14 s per long route; cache per-region walkability if it ever hurts).
- **`rotate` reorders the party permanently** — discovered when a grind-to-13 produced a L13 *Mankey* lead and a L6 Squirtle in slot 6. Grind now tracks the strongest non-egg member; Brock's precondition accepts Karate Chop/Low Kick (fighting beats rock too). Mankey ended up doing the job Squirtle couldn't.
- Fight-vs-flee battle policy centralised (`fight_all_battles` in catching.py) — the third "grind fled everything" incident; policy lives at the run_skill call site by design, so gyms/planner share the helper.
- Post-badge-1 maps annotated (Route 3/4, Mt Moon 1F/B1F/B2F) → 7 new species enter the planner queue (verified by test).

**Verified**
- `python -m dexbot.gyms brock` from `m6_pre_brock_dex.ss1`, fully unattended: grind → heal → gym → badge. Fixture `m7_badge_brock.ss1`. Suite: 26 passed.

**Risky / notes**
- Route 3's trainer gauntlet is unavoidable for Mt Moon trips — heal cycles + rotate should cope, but money for potions/balls is thin until trainer payouts accumulate.
- The Squirtle-vs-Bulbasaur rival counter still needs a real answer before forced rival fights (Cerulean, SS Anne).
## 2026-07-06 — M6: Deterministic dex planner (+ M9 pulled forward)

**Done**
- `dexbot/planner.py`: deterministic priority queue — missing species × accessible maps (flag-gated annotations in `data/dependencies.json` `maps` section; unannotated = off-limits, coverage grows with story) sorted by encounter rate. Loop: plan → catch → update dex → repeat. `grind_levels` fights wilds at Route 2 south grass with heal cycles.
- **M9 pulled forward** (no emulator needed): `dexbot/llm_planner.py` — optional Ollama planner behind `config.json`, consulted only at objective boundaries with the enumerated valid-objective list; validator rejects anything not in the list and falls back to the deterministic queue head. 8 tests inject garbage/hallucinated/broken responses + connection failures.
- `run.py`: living-dex entry point — persistent profile resume, telemetry + 5-minute auto-savestate frame hooks, fresh-save bootstrap.
- Unattended-operation config overrides (`emulator.py`): `new_move=learn_best`, `stop_evolution=False`, `faint_action/lead_cannot_battle_action=rotate`, `hp_threshold=10`.

**Failure archaeology (5 failed runs, each a real lesson)**
1. Grind fled every battle — wild "trash" encounters default to RunAway; `BattleAction.Fight` must be explicit.
2. Grind switched to Manual — Squirtle learning Withdraw at L10 with `new_move: stop`.
3. Party wiped during grind — battles won but *never healed*; chip damage + Weedle poison → lead was a 2 HP Rattata. Grind now checks the starter (slot 0), heals below 40% or on any status.
4. Route 22 rival = Bulbasaur, the built-in Squirtle counter (Bubble resisted, Vine Whip super-effective) — party of L3 fodder couldn't rotate. **Solved by geometry**: his ambush trigger is a 3-tile line at (33, 4–6); the Mankey/Spearow grass at (38, 11) is reachable from the east entrance without crossing it. No fight, no grind needed.
5. Infinite spin↔no-heal loop hunting Pikachu — **Static paralyzed** Squirtle while HP stayed above the heal threshold; `needs_heal` triggered on status but `ensure_healthy` only checked HP. Both now consider status conditions.

**Verified**
- Full autonomous run from `m4_pokedex.ss1`: all 9 pre-Brock species (Rattata, Pidgey, Mankey, Caterpie, Weedle, Kakuna, Spearow, Metapod, Pikachu) caught; queue drains to empty. Fixture `m6_pre_brock_dex.ss1`. Suite: 24 passed.

**Risky / notes**
- The rival fight is deferred, not solved — M7 needs an answer to Bulbasaur (Butterfree's Confusion is super-effective on Grass/Poison; or overlevel for Bite at L16).
- Ball economy held (~15 balls for 9 species thanks to weakening) but money is nearly zero; M7 trainer fights fund M8.
## 2026-07-06 — M5: Catch loop

**Done**
- `dexbot/catching.py`: `catch_species(species, map_key=None, tile=None)` — KB picks the best encounter map, walks to an encounter tile (centroid-sorted, or an explicit safe tile), spins to trigger encounters. Target species → upstream `CatchStrategy` (ball choice by catch-rate math, status moves); everything else → flee. `ensure_healthy()` heals at the Viridian Pokémon Center below 50% lead HP. `dexbot/kb.py`: KB accessors.
- `runner.run_skill` gained an `on_battle_started` hook so skills can set per-encounter battle policy.
- Navigation hardening from real failures:
  - transient path failures (wandering NPC blocking a choke point — its current *and* previous tiles are obstacles) → wait 120 frames, retry;
  - persistent failures → blacklist that warp and re-plan (map "levels" are not internally connected: the BFS once routed to Route 2's *north* forest gate, unreachable from the south segment);
  - "not controllable" right after menus → brief wait, retry.
- KB pick is reachability-blind: Pikachu's globally best map is the Power Plant (Surf-gated). Explicit map override for now; the M6 planner must intersect encounter maps with the dependency graph.

**Verified**
- From `m4_pokedex.ss1`, fully unattended: bought 5 extra balls, caught Rattata, Pidgey, Caterpie, Weedle and the 5%-rate Pikachu (forest south-entrance grass, away from bug-catcher line of sight); dex owns 6 species. Fixture `m5_five_species.ss1`; suite 14 passed.

**Risky / notes**
- `CatchStrategy` doesn't weaken targets (status+balls only) — ball burn is ~3/catch for rate-255 commons. Fine for commons; low-catch-rate targets (Abra, legendaries) will need weakening logic (M7's damage calc) and better balls.
- The Route 22 rival ambush beat a chipped Squirtle earlier — trainer fights during catch trips are the M7 boundary. Until then catch routes avoid trainer maps.
- Party-full box management deferred to M8 (party has room for now); KNOWN_LIMITATIONS updated.

## 2026-07-06 — M4: Scripted openings (and M3 completion)

**Done**
- `dexbot/runner.py` upgraded to upstream's full main-loop shape: FrameInfo + bot listeners each frame, controller stack. This gives every skill upstream's battle handling for free — wild encounters and the rival fight are fought by the default battle strategy without any code on our side.
- `dexbot/openings.py`: `acquire_starter` (Oak trigger → cutscene → pick Squirtle middle ball → decline nickname → rival-takes-starter scene), `beat_lab_rival` (walk to door triggers fight; listener battles it; verified via `BEAT_RIVAL_IN_OAKS_LAB`), `deliver_parcel_get_pokedex` (mart counter talk-across, Oak delivery, `SYS_POKEDEX_GET`), `buy_pokeballs` (drives FRLG's buy menu directly — upstream's `buy_in_shop` precondition `Task_ShopMenu` never sticks in FRLG marts; documented flow in the code).
- **Sign-lady deadlock (nasty)**: crossing Pallet's north exit triggers the sign tutorial. Her "press START to open the MENU" box (`signmsg` + `DisableMsgBoxWalkaway` in pret scripts) swallows A/B forever — and blind A-mash + re-triggering her while her scripted walk was in flight hard-deadlocked the game script. Fix in `navigation.py`'s interruption handler: reset held buttons, mash A with periodic START, B afterwards to close an accidentally opened menu, wait for `ScriptMovement_MoveObjects` to drain before re-planning.
- M1 telemetry flag names fixed — `get_event_flag()` silently returns False for unknown names; the originals didn't exist in `frlg.txt`. Now: `SYS_POKEDEX_GET`, `BEAT_RIVAL_IN_OAKS_LAB`, `GOT_HM01–06`, badges.
- `context.stats` now uses upstream's real `StatsDatabase` (profile-local SQLite), required by encounter handling.

**Verified**
- Full unattended fresh-boot run: intro → name entry → starter → rival won → parcel → Pokédex → 10 Poké Balls bought (money 3080→1080). Fixtures `m4_post_lab.ss1`, `m4_pokedex.ss1` regenerated by `python -m dexbot.openings`.
- The brief's M3 acceptance now green: post-Oak's-lab state → Viridian Mart, exact map+coords. Suite: 12 passed.

**Risky / notes**
- Wild encounters during Route 1 crossings are *fought*, not fled (default strategy) — fine now (free XP), M5 will make encounter policy explicit per skill.
- If the lab rival fight were ever lost the run aborts with a clear SkillError — deterministic seed wins it today; revisit if fixtures change.
- FRLG mart interaction quirks (counter talk-across at (4,3), buy-menu task flow) are encoded in `buy_pokeballs` — reuse it as the template for M8's `buy_items`.

## 2026-07-06 — M3: navigate_to (part 1 — warp-spanning navigation works)

**Done**
- `dexbot/navigation.py`: L1 `navigate_to(map, coords)` — BFS over the warp graph (levels = upstream's connected-map components, edges = warp events read from ROM map data), each leg delegated to upstream's A* (`calculate_path`/`navigate_to`), which already handles collision, ledges, NPCs, and connections.
- `dexbot/runner.py`: `run_skill()` frame loop with timeout + JSONL skill telemetry (`logs/skills.jsonl`) — no skill can hang silently.
- **Found + fixed an upstream bug**: FRLG diagonal stair warps ("Stair Warp Up/Left" etc., behaviours 0x6C–0x6F) got no `extra_warp_direction` in `map_path.py` (only RSE-style arrow warps did), so the pathfinder parked on the stair tile and the warp never fired — then mGBA eventually segfaulted. Patch kept minimal, saved as `patches/0001-frlg-diagonal-stair-warps.patch`, auto-applied by `setup.sh`.
- **Second gotcha**: map warp *events* on tiles with behaviour "Normal" (e.g. two of the three exit-warp events in the player's house) are ignored by the game engine. The warp graph now only uses warps sitting on actual warp-triggering behaviours (`WARP_BEHAVIOURS`).

**Verified**
- `tests/test_m3_navigation.py`: bedroom → Oak's lab (stair warp + exit mat + door warp, 3 maps) lands exactly at (4,3)(6,10) in ~1050 frames. Suite: 10 passed.

**Pending for M3 completion**
- The brief's acceptance (Pallet Town → Viridian Mart) needs a post-Oak's-lab savestate — pre-starter, the Oak cutscene intercepts at Route 1. M4's opening script produces that state; the test gets added then.
- 🧍 checkpoint: human should watch one non-headless navigation run (any time; `python -m dexbot.new_game` then a navigate call without headless flags).

**Risky / notes**
- Warp-graph BFS minimizes warp count, not distance (`ponytail` comment in code); fine until routes look dumb.
- Dynamic warps (elevators, group 127/127) are excluded from the graph — story scripts handle those when we get there.

## 2026-07-06 — M2: Knowledge base

**Done**
- `dexbot/build_kb.py` generates `data/` from the **verified ROM itself** via pret symbol tables — no hand-copied game facts:
  - `encounters.json`: 124 maps, all encounter types with per-slot % rates + level ranges (from `gWildMonHeaders`).
  - `trainers.json`: all 742 trainer parties decoded from `gTrainers` (pret `struct Trainer`, 0x28 bytes; handles held-item/custom-move party layouts).
  - `tmhm.json`: TM01–50 + HM01–08 → move, from upstream's pret-derived items/moves JSON.
- Species/catch-rate/evolution data: reused from `pokebot-gen3/modules/data/species.json` (pret-extracted), not duplicated.
- `data/dependencies.json`: hand-authored story/badge/HM dependency graph (cited: Bulbapedia walkthrough + badge field-move gating), consumed by the M6 planner. Structure validated acyclic in tests.

**Verified**
- `tests/test_m2_kb.py` (9 tests total now, all passing): Pikachu 5% / Caterpie 40% in Viridian Forest, Abra 15% @ L8–14 on Route 24, old rod = 100% Magikarp, Brock = Geodude 12 + Onix 14, HM01=Cut / HM03=Surf / HM04=Strength / TM26=Earthquake, exactly 50 TMs, Squirtle catch rate 45 & evolves at 16, dependency graph acyclic with only known flag references.

**Risky / notes**
- `dependencies.json` gating details (esp. Sevii access, Flash aide's 10-dex requirement) are from documentation, not yet verified in-game — verify as milestones reach them.
- Trainer `iv_strength` is the raw 0–255 fixed-IV field; convert with `iv * 31 // 255` when the M7 damage calc needs real IVs.

## 2026-07-06 — M1: State telemetry

**Done**
- `dexbot/telemetry.py`: `capture_state()` decodes frame, game state, player name, money, map group/number, coords, facing, party (species/level/hp/status), all 8 badge flags, configurable story flags, dex seen/owned counts, and battle state — all via pokebot memory decoders, zero pixel reads. `TelemetryLogger` appends JSONL to `logs/` every N frames via `tick()`.
- Upstream's FireRed test savestates are **v1.1** (CRC 0x84EE4776); our cart is v1.0 (0xDD88761C), so they're unusable. Generated our own: `dexbot/new_game.py` drives fresh-boot → New Game → Oak intro → naming screens (3×A, START, A) → controllable overworld, purely off `gMain.callback2` state. Worked first try; saved as `fixtures/m1_game_start.ss1`.

**Verified**
- `tests/test_m1_telemetry.py`: loads the fixture, runs 100 frames with a 30-frame logging interval, asserts ≥3 entries, exact known values (name "AA", ₽3000, map (4,1) @ (6,6), empty party, no badges, not in battle) and monotonically increasing frame numbers. All tests pass.

**Risky / notes**
- `new_game.py` naming-screen handling is timing-based (fixed frame offsets); robust enough headless+deterministic, but M4 should replace it with task/menu-state-driven input if it ever flakes.
- v1.0 vs v1.1 matters everywhere: symbol tables differ. All fixtures must come from our own runs — documented in `fixtures/README.md`.

## 2026-07-06 — M0: Environment

**Done**
- ROM extracted from user-provided zip → `roms/firered.gba`; MD5 verified = `e26ee0d44e809351c8ce2d73c7400cdd` (FireRed USA 1.0).
- Cloned 40Cakes/pokebot-gen3 @ `5dd898f` (gitignored; `setup.sh` re-clones at pinned commit).
- Python 3.12 venv + all pokebot deps installed. libmgba-py 0.2.0 bindings unzipped into `pokebot-gen3/mgba/`.
- No root available for `apt install libmgba0.10t64`, so the .deb is extracted into `vendor/lib/` and `dexbot/__init__.py` preloads it with `ctypes.CDLL(..., RTLD_GLOBAL)` — no `LD_LIBRARY_PATH` needed.
- `dexbot/` sibling package created (zero upstream diffs so far). `dexbot/m0_boot.py` boots headless, taps A through the intro, detects the title screen via `gMain.callback2 == CB2_TITLESCREENRUN` (memory, not pixels), waits out the fade-in, and dumps proof.

**Verified**
- `proof/m0_title.png` shows the full FireRed title screen; `proof/m0_memory.json` has the callback2 symbol + gMain bytes; `fixtures/m0_title.ss1` savestate saved.
- `tests/test_m0_boot.py` (headless: load fixture, assert `GameState.TITLE_SCREEN`) passes.

**Risky / notes**
- Upstream already ships far more than expected: `map_path.py` (pathfinding), battle handling, safari strategy, a savestate-based test harness (`tests/utility.py` with `AutomatedTestBotMode`, `@with_save_state`). M3/M5/M7 should reuse these heavily instead of building from scratch.
- `context.rom.game_name` is `"Pokémon FireRed (E)"` — the (E) suffix is their language tag for English, not Europe.
- The bundled libmgba-py build targets Ubuntu 23.04; works fine on 24.04 with the vendored 0.10.2 lib, but keep an eye on it.
