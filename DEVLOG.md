# DEVLOG

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
