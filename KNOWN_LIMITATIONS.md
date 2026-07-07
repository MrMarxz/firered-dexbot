# Known limitations

- **nav_graph.json is story-epoch-stamped (badge count) and not auto-rebuilt.**
  Planning uses the precomputed connectivity graph (data/nav_graph.json,
  rebuilt in ~10s via `python -m dexbot.build_navgraph <fixture>`); when the
  badge count no longer matches, navigation silently falls back to the slow
  live search (~32s cross-region). Rebuild after each badge, or automate the
  rebuild in the ops loop. Badge count is also only a *proxy* for gates that
  open without a badge (e.g. Saffron's guards want a drink, not a badge).
- **Connectivity components assume walk-reachability is symmetric**, but
  ledges are one-way. If a portal pair is only connected via a ledge drop,
  the component (and hence a planned route) can be wrong in one direction —
  corrected at execution time by the blacklist-and-replan machinery.

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
