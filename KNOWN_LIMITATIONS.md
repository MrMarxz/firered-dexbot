# Known limitations

- **Script-locked gates need explicit exclusion.** `calculate_path` sees
  collision, not coord-event scripts, so the graph over-connects through gates
  a guard blocks (Saffron's four gates until `GOT_TEA`). These are excluded at
  BFS time by `_story_gated_warp_dests` — a hardcoded destination-map set keyed
  on the relevant flag. Any future script-gated area (e.g. a badge-checked
  route guard) needs an entry there; the graph alone won't catch it. Only
  Saffron/`GOT_TEA` is handled today.
- **nav_graph.json's story epoch is the badge count — a proxy.** On a
  badge-count mismatch it auto-rebuilds in-process (~10s). Non-badge geometry
  changes (a boulder pushed, a cut tree — trees respawn so that's fine) are
  otherwise not re-detected; rebuild manually if a route looks stale.
- **Script-conditional metatile barriers are modeled as permanent walls.**
  Rocket Hideout B1F's barrier (20-21,19-21, opens on TRAINER_GRUNT_12) is
  hard-excluded via `_is_optional_blocker`, and B4F's (17-18,12-13) plus the
  spin maze are bypassed with a probe-derived hardcoded route in
  `clear_rocket_hideout` — correct for our one pass through, but the graph
  will never route through such barriers even when they're open. If a future
  area needs one post-open (Silph Co has similar gadgets), model the flag.
  Discovery protocol when "map data open, game blocked": read pret's
  `data/maps/<Map>/scripts.inc` on_load handlers; probe with
  `scripts/probe_maze.py` (fights ambushes, A-presses obstructions — but keys
  states on position, so flag-only progress like talk-fights needs pret).
- **Nav-graph walk edges are rep-to-rep**: a directed walk edge A→B is proven
  between one representative tile pair; if a component is internally mutual
  but the one-way passage only works from part of it (shouldn't happen for
  SCCs, but NPC templates can shift with story state), a leg can fail at
  execution — corrected by the blacklist-and-replan machinery.

- **Unwinnable battles wedge until the watchdog fires.** A wild GHOST in
  Pokémon Tower without the Silph Scope loops "too scared to move!" for 30k
  frames before the progress watchdog aborts (seen live 2026-07-08, stall
  232742). The battle engine has no "this fight cannot be won → flee" rule;
  the tower case self-resolves once the Scope is owned, but any future
  no-damage-possible matchup (Wobbuffet-style walls, out-of-PP corners) hits
  the same wedge. Class fix wanted: fight_all_battles should flee when N turns
  produce zero state change.
- **Post-whiteout recovery inside catch_species can wedge.** Seen live
  (catch_Gastly, stall 234206): the party whited out in Pokémon Tower, the
  whiteout handler recovered to the Lavender PC, and the skill then made no
  progress for 30k frames until the watchdog deferred it. The planner's
  deferred-retry pass (retry deferrals while passes make progress) papers over
  it — a fresh skill start succeeds — but the in-skill resume path after
  whiteout deserves the interact()-class treatment. Also unclear why an L47
  Blastoise whited out vs L13-25 tower ghosts; replay the stall fixture.
- **Vs Seeker rematch income is NOT producing sustained returns** (blocks the
  Koga grind, 2026-07-09). Root-caused the first bug — the old sweep walked
  *grass* tiles, missing the trainers' line-of-sight; `_earn_by_vs_seeker` now
  walks each trainer's approach tile (west→east) with a recharge lap before the
  Select, each leg its own run_skill. But every sweep still earns 0: the early
  624/+3456 were one-shot FIRST-TIME trainer fights (now exhausted), not
  rematches. So the Vs Seeker use itself isn't re-arming — needs frame-by-frame
  debugging of the Select→Seeker flow (is it registered to Select? charge
  threshold? per-trainer rematch probability? are the '!!' markers appearing?).
  Until this works, there is no renewable income engine, which blocks buying
  the Koga potion stack and grinding XP. Dedicated M8 task.
- **The economy is thin**: income so far is one-off (Nugget, trainer payouts
  during story treks, junk-item liquidation when broke — FRLG cannot sell TMs,
  the TM Case is unreachable from the mart sell menu). Ball/potion budgets can
  stall catch objectives (they defer, not fail). The M8 engine is Vs Seeker
  trainer rematches (obtainable in Vermilion's Pokémon Center) plus held-item
  collectibles; until then sweeps may need story-trek income between waves.

Honesty over optimism. Current as of M5.

- **Party/box management** (M8, sub-project A — `dexbot/team.py`): the planner
  now assembles a diverse, catch-rate-optimized team (`assemble_party`) before
  each catch objective, leaving one party slot free for the incoming catch
  (a full 6-party still makes upstream's catch fail, so the catch team is 5).
  Replaces the old deposit-to-one behavior. Still TODO: gym-objective team
  assembly is wired (`kind="gym"`) but not yet driven by a planner gym loop
  (sub-project B); leveling the assembled team is B.
- **No weakening before catching**: upstream's CatchStrategy uses status moves +
  balls only. Rate-255 commons cost ~3 balls; low-rate species (Abra 50,
  legendaries 3) will be impractical until M7's damage calc enables safe
  weakening and better balls are purchasable.
- **Trainer battles are survived, not planned** (M7): the default battle strategy
  fights whatever ambushes us. Catch routes currently avoid trainer-heavy maps;
  the Route 22 rival ambush loses if the starter is chipped.
- **KB best-map pick ignores reachability**: `best_encounter_map` may point at a
  gated area (e.g. Pikachu → Power Plant). Callers override the map; M6's
  planner will intersect with the dependency graph.
- **Warp-graph BFS is coarse**: minimizes warp count, not distance; assumes a
  map "level" is internally connected (wrong for e.g. Route 2 — mitigated by
  blacklist-and-replan on persistent path failure). Dynamic warps (elevators)
  are not edges.
- **Route 2 ledge-hop loop**: a leg whose target sits above a ledge line can
  pace a 3x3 box forever (hop down → loop around → hop down). The pacing
  detector now converts it to a defer within ~20k frames (bounding-box test —
  the old ≤4-unique-tiles test missed the 5-7 tile box). Nav-level fix still
  owed; ready repro: `fixtures/_stalls/catch_Magikarp_114906.ss1`.
- **navigate_to script interruptions**: handled generically (A-mash + periodic
  START + B), verified on the Pallet sign lady. Other one-time triggers across
  Kanto may need the same treatment — watch logs/skills.jsonl for timeouts.
- **Vs Seeker rematches never fire — income laps earn ₽0**: extensively
  probed 2026-07-10. What IS known: the registered-item Select shortcut
  silently no-ops in this harness (fire it from the BAG — `Task_VsSeeker_*`
  tasks confirm); after firing, a message box ("The other TRAINERS don't
  appear…") waits on a button press that `wait_for_no_script_to_run` does not
  deliver (no script is active — mash B on `Task_ContinueTaskAfterMessagePrints`);
  the ≥100-step recharge is satisfied by a two-round-trip shuttle between the
  approach x-extremes. Even with all three fixed, every Route 11 fire reports
  no interested trainers and no rematch battle happens. Next probe: read the
  per-trainer defeated flags (`TRAINER_FLAGS_START + id`) — an unbeaten
  trainer is rematch-ineligible, and the original "+₽4.7k lap" was probably
  first-time ambushes, not rematches. The lap-0 +4.7k was never reproduced.
  Meanwhile the economy runs on one-shot patrols, item liquidation, and
  Amulet-Coin-doubled story/gym fights.
- **Cycling Road is downhill-only**: Route 17's slope tiles keep the avatar in
  a perpetual forced-slide state, so legs there use walk_carefully
  (tap-and-settle; a released coast is re-pathed from the landing). Southbound
  (downhill) is verified end-to-end. Northbound climbs need a continuously held
  Up the tap walker can't produce — a northbound leg fails loudly after
  max_repaths and re-plans/defers (the eastern Routes 12–15 corridor covers
  Celadon↔Fuchsia). Add a hold-Up climb special case only if a route ever
  genuinely needs to ascend.
- **`ensure_healthy` heals only at Viridian** — fine while all catch targets are
  in the starting area; switch to `find_closest_pokemon_center` in M6.
- **Deterministic RNG assumption in fixtures**: acceptance runs replay
  identically from savestates. Live runs will diverge (RNG seeded by intro
  timing); skills are state-driven so this should be safe, but it is untested
  beyond the acceptance paths (M10 will tell).
- **dependencies.json gating details** (Sevii timing, Flash aide's 10-dex
  requirement) are documentation-sourced, not yet verified in-game.
