# PROJECT BRIEF

## Mission

Build an autonomous bot that completes a single-cart living dex in Pokémon FireRed (USA):
catch one of every species obtainable in FireRed without trading (~124 species), progressing
through the story as far as needed (all 8 badges if required for dex access). Runs unattended
for long stretches on the owner's PC (Ryzen 5800, RTX 3070 8GB VRAM, 64GB RAM).

## Non-negotiable constraints

1. The bot reads game state from emulator memory only. Never from pixels/screenshots.
2. No LLM calls in the runtime loop by default. The runtime must complete the living dex
   with zero LLM involvement. An optional planner may call a local Ollama endpoint
   (OpenAI-compatible API, configurable base URL + model in config); it is strictly additive.
   Never call the Anthropic API or claude CLI from the bot at runtime. Claude Code's role
   is development only.
3. ROM is user-provided. Expect it at roms/firered.gba. On startup, verify MD5 equals
   `e26ee0d44e809351c8ce2d73c7400cdd` (FireRed USA 1.0) and abort with a clear message if not.
   Never download, fetch, or generate ROM data.
4. All game facts come from a static local knowledge base (encounter tables, evolution
   methods, TM/HM data, trainer parties, story-flag dependencies), sourced from the
   pret/pokefirered decompilation and documented community data. The LLM planner must never
   be the source of game facts.
5. Fork of 40Cakes/pokebot-gen3 is the executor foundation. Extend via a plugins/ or
   sibling-package approach; keep upstream-touching diffs minimal so we can pull fixes.

## Architecture (four layers, strict boundaries)

- **L0 Executor** — pokebot-gen3 fork: libmgba emulation, frame-perfect input, FireRed memory
  decoding, encounter/catch automation, headless high-speed mode.
- **L1 Skill library** — deterministic Python routines composed from L0 primitives:
  `navigate_to(map, x, y)`, `catch_species(species)`, `progress_story(flag)`,
  `grind_levels(target)`, `manage_boxes()`, `buy_items(list)`, `use_pc()`, `safari_run(targets)`.
  Every skill: idempotent where possible, emits structured telemetry, has a timeout and a
  failure state (never hangs silently).
- **L2 Planner** — default: deterministic priority queue over missing dex entries, ordered by
  a dependency graph (story flags, HMs, badges, money). Optional: Ollama planner that receives
  structured JSON state + an enumerated list of currently-valid objectives and returns one
  choice with rationale. A validator rejects any response not in the list and falls back to
  the queue. Planner is consulted only at objective boundaries.
- **L3 Ops** — JSONL telemetry (logs/), auto-savestates every 5 min + before every risky
  maneuver (Safari entry, gym fight, story script), crash-resume from latest checkpoint,
  DEVLOG.md updated every session, dex-progress dashboard as a simple CLI/HTML status page.

## Development process rules

- Milestone-driven. Do not skip ahead. Complete, verify, commit, and log each milestone
  before starting the next. One commit minimum per milestone, conventional commit messages.
- Self-verify with the emulator as test harness. Emulation is deterministic: load a
  savestate, run the skill headless, assert on memory state (player map/coords, party
  contents, flags). Write these as pytest tests under tests/. A milestone is done when its
  automated check passes headless, not when the code "looks right."
- Maintain fixtures/ of savestates for tests (generate them during play-throughs of
  milestones; document how each was produced).
- On any failure you cannot resolve after 3 distinct attempts, write a detailed entry to
  DEVLOG.md (symptom, hypotheses, what was tried) and move to whatever work is unblocked.
- Ask the human ONLY at the checkpoints marked 🧍 below. Everything else, decide and proceed.
- Keep a KNOWN_LIMITATIONS.md — honesty over optimism.

## Milestones

- **M0 — Environment** 🧍(human places ROM): Fork/clone pokebot-gen3, install deps
  (Python 3.12, libmgba bindings), verify ROM MD5, boot FireRed headless, reach title screen,
  dump a screenshot + memory snapshot as proof. Commit.
- **M1 — State telemetry**: Continuous JSONL logging of decoded state (map id, coords, party,
  money, badges, flags of interest, current battle state) at a configurable interval.
  Verify by asserting log contents against a known savestate.
- **M2 — Knowledge base**: Build data/ (SQLite or JSON) from pret/pokefirered-derived data:
  species, encounter tables per map (grass/surf/rod/rock smash), evolution methods, catch
  rates, TM/HM list, key trainer parties, and a story-flag/HM/badge dependency graph.
  Include a data/README.md citing sources. Verify with spot-check tests (e.g., Pikachu in
  Viridian Forest slots, Abra rates on Route 24).
- **M3 — navigate_to (make-or-break)**: A* pathfinding over walkable tiles using in-memory map
  collision data, spanning map connections and warps, handling ledges (one-way edges), NPCs,
  and blocked tiles. Acceptance test: from a fresh post-Oak's-lab savestate, walk
  Pallet Town → Viridian City Poké Mart headless, assert final map+coords. 🧍(human watches
  one non-headless run to confirm sane behavior).
- **M4 — Scripted openings**: Skills for the fixed early sequence: intro/name entry, starter
  selection (pick Squirtle), first rival fight (spam attack + potion logic), Oak's parcel
  loop, Pokédex acquisition. Acceptance: fresh-save to "own Pokédex + Poké Balls purchasable"
  fully unattended.
- **M5 — Catch loop**: `catch_species` — navigate to best encounter location (from KB),
  trigger encounters (spin/sweet-scent later), weaken safely (no self-KO: track damage
  ranges), ball selection by catch-rate math, status moves when available, deposit-safe party
  management. Acceptance: catch 5 named early-route species unattended from a savestate.
- **M6 — Dex planner v1 (deterministic)**: Priority queue + dependency graph selects
  objectives; loop: plan → execute skill → update dex state → repeat. Acceptance: from
  post-M4 state, autonomously complete every species catchable pre-Brock.
- **M7 — Trainer/gym battle engine**: Damage-calc-based move selection (type chart, STAB,
  stats from KB), switch logic, potion/revive usage, level-grind trigger when projected to
  lose. Acceptance: beat Brock unattended from an appropriate savestate. Then iterate gym by
  gym; each badge is a sub-milestone with its own savestate test.
- **M8 — Long-haul systems**: PC box management for living-dex storage, money economy
  (ball/potion budgeting, payday routes), Safari Zone strategy (step budget, bait/rock policy
  from documented mechanics), Repel management, evolution handling (level/stone/friendship),
  crash-resume drills (kill -9 the bot mid-run; it must resume from checkpoint).
- **M9 — Optional Ollama planner**: Implement the L2 LLM planner behind a config flag with
  the validator + queue fallback. Acceptance: with an intentionally garbage model response
  injected in tests, the bot proceeds correctly via fallback.
- **M10 — The run** 🧍: Full living-dex attempt with dashboard. Log everything. Expect
  failures; each failure becomes a DEVLOG entry and a fix.

## Definition of done

`python run.py --goal living-dex` from a fresh save reaches 100% of single-cart-obtainable
FireRed species in boxes, unattended except for documented 🧍 checkpoints, surviving at least
one forced crash-resume, with all milestone tests green.
