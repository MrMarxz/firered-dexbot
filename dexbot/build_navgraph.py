"""Precompute the walk-connectivity graph for warp routing.

The problem it solves: pokebot merges every connection-linked map into one
"level" (level 180 is most of Kanto — 122 warps). Live route planning A*-checks
walkability per warp, which is slow (~32s cross-region). But walk-reachability
is static (given the story state), so we compute it ONCE here and cache it.

For each level we partition its *portal tiles* — every warp's source tile plus
every warp's landing tile that sits on that level — into components. Two portal
tiles are in the same component iff `calculate_path` connects them IN BOTH
DIRECTIONS: walk-reachability is NOT symmetric (ledges are one-way; Cerulean's
south gap is blocked by a policeman while the reverse approach works), so
components are strongly-connected sets, found incrementally against one
representative per existing component. One-way passages are then captured as
DIRECTED WALK EDGES between same-level components (rep-to-rep A*).

Output: data/nav_graph.json
    {"epochs": {"<badge count>": {
        "components": {tile_key: component_id, ...},   # tile_key = "mg,mn,x,y"
        "walk_edges": [[from_id, to_id], ...],         # directed, same-level
        "levels_done": [level, ...],                   # resume bookkeeping
    }}}
Connectivity depends on story gates, so sections are keyed by a story epoch
(= badge count) and coexist; building only ever touches the current epoch's
section. (Warp edges are NOT stored — the runtime rebuilds them from ROM via
_get_warp_edges(), the same source this script uses.)

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

    # Resume this epoch's prior partial run; other epochs' sections are
    # untouched. Sections from before the cut-edge format are rebuilt.
    from dexbot.navigation import story_epoch

    epoch = story_epoch()
    section = {"components": {}, "walk_edges": [], "cut_edges": [], "levels_done": []}
    if GRAPH_PATH.exists():
        prior = json.loads(GRAPH_PATH.read_text()).get("epochs", {}).get(str(epoch))
        if prior and "levels_done" in prior and "cut_edges" in prior:
            section = prior

    components: dict[str, int] = section["components"]
    walk_edges = {tuple(e) for e in section["walk_edges"]}
    cut_edges: list = section["cut_edges"]
    levels_done = set(section["levels_done"])
    next_id = max(components.values(), default=-1) + 1

    def _distance(a, b) -> int:
        ga, gb = _global_coords(*a), _global_coords(*b)
        if ga is None or gb is None:
            return 0
        return abs(ga[0] - gb[0]) + abs(ga[1] - gb[1])

    for level in sorted(portals):
        if level in levels_done:
            continue
        tiles = sorted(portals[level])
        reps: list[tuple] = []  # (representative_tile, component_id)
        for tile in tiles:
            assigned = None
            # Nearest rep first: a failed A* must exhaust the whole reachable
            # region (expensive on level 180), so try the likeliest match first.
            for rep_tile, cid in sorted(reps, key=lambda r: _distance(tile, r[0])):
                if _walkable(tile, rep_tile) and _walkable(rep_tile, tile):
                    assigned = cid
                    break
            if assigned is None:
                assigned = next_id
                next_id += 1
                reps.append((tile, assigned))
            components[_tile_key(*tile)] = assigned
        # One-way passages (ledges, guard-gated gaps) between this level's
        # components become directed walk edges.
        for rep_a, ca in reps:
            for rep_b, cb in reps:
                if ca != cb and _walkable(rep_a, rep_b):
                    walk_edges.add((ca, cb))
        cut_edges.extend(_cut_edges_for_level(level, reps, components, _distance, _walkable))
        # _cut_edges_for_level mints component ids for warpless pocket sides;
        # resync the portal counter or the next level's portals reuse those
        # ids (a Saffron portal collided with Route 14's pocket — one "component"
        # spanning two levels routed walking legs through gate buildings).
        next_id = max(components.values(), default=-1) + 1
        levels_done.add(level)
        if save_every_level:
            _write(components, walk_edges, cut_edges, levels_done, epoch)
            print(f"  level {level}: {len(tiles)} portals, {len(reps)} components", flush=True)

    _write(components, walk_edges, cut_edges, levels_done, epoch)
    return {"components": components, "walk_edges": walk_edges, "cut_edges": cut_edges}


_FACING = {(0, -1): "Up", (0, 1): "Down", (-1, 0): "Left", (1, 0): "Right"}


def _cut_edges_for_level(level, reps, components, _distance, _walkable) -> list:
    """Conditional edges across this level's cuttable trees: for each pair of
    tree-adjacent tiles in DIFFERENT components, an edge traversable by cutting
    (trees respawn on map reload, so the cut is an action per traversal, not
    state). Edge: [from_comp, to_comp, tree_map, tree_xy, stand_xy, facing].

    A tree side matching NO existing component gets a fresh one minted for it:
    a warpless pocket (Route 12's grass — no warp inside, only the tree gate)
    has no portal tiles, so without this it stays invisible to the graph and
    the planner vetoes every species in it."""
    from modules.map import get_map_data
    from modules.map_path import _get_all_maps_metadata

    result = []
    next_id = max(components.values(), default=-1) + 1
    for map_key, pm in _get_all_maps_metadata().items():
        if pm.level != level:
            continue
        try:
            objects = get_map_data(map_key, (0, 0)).objects
        except Exception:
            continue
        for obj in objects:
            if str(getattr(obj, "script_symbol", "")) != "EventScript_CutTree":
                continue
            tree = tuple(obj.local_coordinates)
            # Which component does each adjacent tile belong to (mutual test
            # against this level's reps, nearest first)?
            sides = []  # (stand_tile, facing, comp)
            for (dx, dy), facing in ((d, f) for d, f in _FACING.items()):
                stand = (tree[0] + dx * -1, tree[1] + dy * -1)  # tile the delta points FROM
                if stand[0] < 0 or stand[1] < 0:
                    continue
                try:
                    if get_map_data(map_key, stand).collision:
                        continue  # walled side — never mint a component for a wall
                except Exception:
                    continue
                pos = (map_key, stand)
                comp = None
                for rep_tile, cid in sorted(reps, key=lambda r: _distance(pos, r[0])):
                    if _walkable(pos, rep_tile) and _walkable(rep_tile, pos):
                        comp = cid
                        break
                if comp is None:
                    comp = next_id
                    next_id += 1
                    reps.append((pos, comp))
                    components[_tile_key(*pos)] = comp
                sides.append((stand, facing, comp))
            for stand_a, facing_a, ca in sides:
                for _stand_b, _facing_b, cb in sides:
                    if ca != cb:
                        result.append([ca, cb, list(map_key), list(tree), list(stand_a), facing_a])
    return result


def _write(components, walk_edges, cut_edges, levels_done, epoch: int) -> None:
    epochs = {}
    if GRAPH_PATH.exists():
        epochs = json.loads(GRAPH_PATH.read_text()).get("epochs", {})
    epochs[str(epoch)] = {
        "components": components,
        "walk_edges": sorted(walk_edges),
        "cut_edges": cut_edges,
        "levels_done": sorted(levels_done),
    }
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
    print(f"nav graph: {len(graph['components'])} portal tiles, {n_components} components, "
          f"{len(graph['walk_edges'])} one-way walk edges, {len(graph['cut_edges'])} cut edges "
          f"in {time.time() - t0:.0f}s -> {GRAPH_PATH}")


if __name__ == "__main__":
    main()
