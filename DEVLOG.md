# DEVLOG

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
