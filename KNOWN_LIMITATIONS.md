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
- **Nav-graph walk edges are rep-to-rep**: a directed walk edge A→B is proven
  between one representative tile pair; if a component is internally mutual
  but the one-way passage only works from part of it (shouldn't happen for
  SCCs, but NPC templates can shift with story state), a leg can fail at
  execution — corrected by the blacklist-and-replan machinery.

- **The economy is thin**: income so far is one-off (Nugget, trainer payouts
  during story treks, junk-item liquidation when broke — FRLG cannot sell TMs,
  the TM Case is unreachable from the mart sell menu). Ball/potion budgets can
  stall catch objectives (they defer, not fail). The M8 engine is Vs Seeker
  trainer rematches (obtainable in Vermilion's Pokémon Center) plus held-item
  collectibles; until then sweeps may need story-trek income between waves.

Honesty over optimism. Current as of M5.

- **No party/box management yet** (M8): `catch_species` will fail once the party
  is full (6 slots). The living-dex loop needs deposit-after-catch.
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
- **navigate_to script interruptions**: handled generically (A-mash + periodic
  START + B), verified on the Pallet sign lady. Other one-time triggers across
  Kanto may need the same treatment — watch logs/skills.jsonl for timeouts.
- **`ensure_healthy` heals only at Viridian** — fine while all catch targets are
  in the starting area; switch to `find_closest_pokemon_center` in M6.
- **Deterministic RNG assumption in fixtures**: acceptance runs replay
  identically from savestates. Live runs will diverge (RNG seeded by intro
  timing); skills are state-driven so this should be safe, but it is untested
  beyond the acceptance paths (M10 will tell).
- **dependencies.json gating details** (Sevii timing, Flash aide's 10-dex
  requirement) are documentation-sourced, not yet verified in-game.
