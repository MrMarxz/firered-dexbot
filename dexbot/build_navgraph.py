"""Precompute the walk-connectivity graph for warp routing.

The problem it solves: pokebot merges every connection-linked map into one
"level" (level 180 is most of Kanto — 122 warps). Live route planning A*-checks
walkability per warp, which is slow (~32s cross-region). But walk-reachability is
static (given the story state), so we compute it ONCE here and cache it.

For each level we partition its *portal tiles* — every warp's source tile plus
every warp's landing tile that sits on that level — into walk-connected
components. Two portal tiles are in the same component iff `calculate_path`
connects them (which honours collision AND story gates like Saffron's guards).
Reachability is an equivalence relation, so we assign each tile by testing it
against one representative per existing component: O(tiles x components), not
O(tiles^2).

Output: data/nav_graph.json
    {"epochs": {"<badge count>": {tile_key: component_id, ...}}}   # "mg,mn,x,y"
Connectivity depends on story gates, so components are keyed by a story epoch
(= badge count). Sections for different epochs coexist; building only ever
adds/updates the current epoch's section. (Warp edges are NOT stored — the
runtime rebuilds them from ROM via _get_warp_edges(), the same source this
script uses.)

Build resumably (save after each level) — long emulator runs can die silently.

Run:  .venv/bin/python -m dexbot.build_navgraph [fixture.ss1]
"""

import json
import sys

from dexbot import PROJECT_ROOT

GRAPH_PATH = PROJECT_ROOT / "data" / "nav_graph.json"


def _tile_key(map_key, coords) -> str:
    return f"{map_key[0]},{map_key[1]},{coords[0]},{coords[1]}"


def build(context, save_every_level: bool = True) -> dict:
    from dexbot.navigation import _get_warp_edges, _global_coords, _map_level, _walkable
    from modules.memory import get_event_flag

    edges = _get_warp_edges()  # {level: [(src_map, src_coords, dst_map, dst_coords)]}

    # Portal tiles per level: warp sources on the level + landings that arrive on it.
    portals: dict[int, set] = {}
    for level, elist in edges.items():
        for src_map, src_coords, dst_map, dst_coords in elist:
            portals.setdefault(level, set()).add((src_map, src_coords))
            portals.setdefault(_map_level(dst_map), set()).add((dst_map, dst_coords))

    # Resume: reuse this epoch's already-computed levels from a prior partial
    # run. Other epochs' sections are left untouched.
    epoch = sum(1 for n in range(1, 9) if get_event_flag(f"BADGE{n:02d}_GET"))
    existing = {}
    if GRAPH_PATH.exists():
        existing = json.loads(GRAPH_PATH.read_text()).get("epochs", {}).get(str(epoch), {})

    components: dict[str, int] = dict(existing)
    next_id = (max(components.values()) + 1) if components else 0

    def _distance(a, b) -> int:
        ga, gb = _global_coords(*a), _global_coords(*b)
        if ga is None or gb is None:
            return 0
        return abs(ga[0] - gb[0]) + abs(ga[1] - gb[1])

    for level in sorted(portals):
        tiles = sorted(portals[level])
        if all(_tile_key(m, c) in components for m, c in tiles):
            continue  # this level already done (resume)
        reps: list[tuple] = []  # (representative_tile, component_id)
        for tile in tiles:
            key = _tile_key(*tile)
            if key in components:
                # Rehydrate a representative for an already-assigned tile.
                cid = components[key]
                if not any(r[1] == cid for r in reps):
                    reps.append((tile, cid))
                continue
            assigned = None
            # Nearest rep first: a failed A* must exhaust the whole reachable
            # region (expensive on level 180), so try the likeliest match first.
            for rep_tile, cid in sorted(reps, key=lambda r: _distance(tile, r[0])):
                if _walkable(tile, rep_tile):
                    assigned = cid
                    break
            if assigned is None:
                assigned = next_id
                next_id += 1
                reps.append((tile, assigned))
            components[key] = assigned
        if save_every_level:
            _write(components, epoch)
            print(f"  level {level}: {len(tiles)} portals, {len(reps)} components", flush=True)

    _write(components, epoch)
    return {"components": components}


def _write(components, epoch: int) -> None:
    epochs = {}
    if GRAPH_PATH.exists():
        epochs = json.loads(GRAPH_PATH.read_text()).get("epochs", {})
    epochs[str(epoch)] = components
    GRAPH_PATH.write_text(json.dumps({"epochs": epochs}) + "\n")


def main() -> None:
    from dexbot.emulator import setup_headless_emulator

    fixture = sys.argv[1] if len(sys.argv) > 1 else "m7_badge_misty.ss1"
    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / fixture).read_bytes())
    context.emulator.run_single_frame()

    import time

    t0 = time.time()
    graph = build(context)
    n_components = len(set(graph["components"].values()))
    print(f"nav graph: {len(graph['components'])} portal tiles, {n_components} components "
          f"in {time.time() - t0:.0f}s -> {GRAPH_PATH}")


if __name__ == "__main__":
    main()
