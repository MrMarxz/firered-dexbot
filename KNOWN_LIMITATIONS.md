# Known limitations

- **`_pick_reachable_center` / warp route-planning is slow from far-apart
  positions.** `_plan_warp_route` runs a full A* (`calculate_path`) per warp
  edge during BFS; from mid-Route-24, planning to every candidate Pokémon
  Center can hang >90s. Skills currently pass an explicit `center=` to avoid
  it. Proper fix: precompute a static warp-connectivity graph from the ROM
  (offline) and cache per-region walkability, instead of live per-edge A*.

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
