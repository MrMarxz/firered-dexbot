# DEVLOG

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
