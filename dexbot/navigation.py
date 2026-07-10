"""L1 navigate_to: cross-map, cross-warp navigation.

Upstream's `calculate_path`/`navigate_to` already do A* over walkable tiles
(collision, ledges, NPCs) across *connected* maps, and will follow a warp if it
is the final destination. What they cannot do is route *through* warps (doors,
stairs, caves). This module adds that: a BFS over the warp graph picks a
sequence of warps, and each leg is delegated to upstream navigation.
"""

from typing import Generator

from dexbot.runner import SkillError

# ponytail: BFS minimizes warp count, not walking distance; weight edges by
# leg length if routes ever look dumb.


def _map_level(map_group_and_number: tuple[int, int]) -> int:
    from modules.map_path import _get_all_maps_metadata

    return _get_all_maps_metadata()[tuple(map_group_and_number)].level


# Tile behaviours that actually trigger a warp when stepped on/into (FRLG names).
# Warp *events* on tiles without one of these (e.g. behaviour "Normal") are ignored
# by the game engine, so they must not become graph edges.
WARP_BEHAVIOURS = frozenset(
    {
        "Cave Door",
        "Ladder",
        "East Arrow Warp",
        "West Arrow Warp",
        "North Arrow Warp",
        "South Arrow Warp",
        "Fall Warp",
        "Regular Warp",
        "Door Warp",
        "Escalator Up",
        "Escalator Down",
        "Stair Warp Up/Right",
        "Stair Warp Up/Left",
        "Stair Warp Down/Right",
        "Stair Warp Down/Left",
        "Union Room Warp",
    }
)

_warp_edges: dict[int, list[tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]]] | None = None


def _get_warp_edges() -> dict:
    """level -> [(warp_map, warp_coords, dest_map, dest_coords)], built once from ROM map data."""
    global _warp_edges
    if _warp_edges is None:
        from modules.map import get_map_data
        from modules.map_path import _get_all_maps_metadata

        _warp_edges = {}
        for map_key, path_map in _get_all_maps_metadata().items():
            try:
                warps = get_map_data(map_key, (0, 0)).warps
            except Exception:
                continue
            for warp in warps:
                if get_map_data(map_key, warp.local_coordinates).tile_type not in WARP_BEHAVIOURS:
                    continue
                dest = warp.destination_location
                dest_key = (dest.map_group, dest.map_number)
                if dest_key == (127, 127) or dest_key not in _get_all_maps_metadata():
                    continue  # dynamic warps (elevators etc.) handled by story scripts, not navigation
                _warp_edges.setdefault(path_map.level, []).append(
                    (map_key, warp.local_coordinates, dest_key, dest.local_position)
                )
    return _warp_edges


_walkable_cache: set = set()  # proven-walkable pairs — permanent (see below)
_walkable_neg: dict = {}  # failed pairs -> monotonic expiry (TTL — see below)
# Must comfortably exceed a worst-case component scan (~2-3 min), or the scan
# re-expires its own entries and recomputes forever. Execution-time NPC blocks
# are handled by the blacklist machinery, so staleness here is low-risk.
_NEG_TTL_SECONDS = 900.0


def _walkable(
    source: tuple[tuple[int, int], tuple[int, int]],
    dest: tuple[tuple[int, int], tuple[int, int]],
    max_nodes: int = 20_000,
) -> bool:
    """Whether the A* finds a walking path between two positions (no player needed).

    Map "levels" are not internally connected (Kanto's outdoors is split by the
    forest, caves, ...), so warp-route planning verifies every same-level leg
    with the real pathfinder instead of trusting level identity.

    Successes cache permanently (FRLG gates only ever open). Failures cache
    with a short TTL: `calculate_path` blocks the live NPCs' tiles, so a
    wandering NPC in a choke point makes checks fail *transiently* — a
    permanent False poisons all future plans ("No warp route" forever), but NO
    negative caching lets component scans re-run identical multi-second failed
    A* for hours of CPU (USR1-diagnosed twice). 90s bounds the staleness: a
    blocked plan retries and self-heals within ~one NPC wander cycle.
    """
    import time as _time

    from modules.map_path import calculate_path

    key = (source, dest)
    if key in _walkable_cache:
        return True
    expiry = _walkable_neg.get(key)
    if expiry is not None:
        if expiry > _time.monotonic():
            return False
        del _walkable_neg[key]
    try:
        # max_nodes: a reachability probe only needs yes/no. An unbudgeted
        # failure exhausts the whole connected region (post-Snorlax Kanto,
        # tens of seconds); real paths expand a few thousand nodes at most.
        # Component probes pass a much tighter budget still (~3k): a
        # containing-component rep is nearby by construction, so a probe that
        # needs more nodes than that is a "no" — twelve 20k failures inside
        # one _find_component were the 60-120s planning wedges.
        calculate_path(source, dest, max_nodes=max_nodes)
        _walkable_cache.add(key)
        return True
    except Exception:
        _walkable_neg[key] = _time.monotonic() + _NEG_TTL_SECONDS
        return False


# Max A* checks per LIVE-fallback plan. Kept tight: since failed checks are
# never cached (transient NPC walls), each can cost ~200-500ms of pure CPU on
# level 180 — 2000 of them froze a run for two hours with zero frames advanced.
# The graph answers almost everything now; the fallback only needs enough for
# same-level direct walks and stale-graph gaps.
_WALKABLE_BUDGET = 250


def _global_coords(map_key: tuple[int, int], local: tuple[int, int]) -> tuple[int, int] | None:
    """Approximate global coordinates for cross-map distance heuristics."""
    from modules.map_path import _get_all_maps_metadata

    pm = _get_all_maps_metadata().get(tuple(map_key))
    if pm is None or pm.offset is None:
        return None
    return (local[0] + pm.offset[0], local[1] + pm.offset[1])


def perform_cut(map_key, tree_tile: tuple[int, int], stand_tile: tuple[int, int], facing: str) -> Generator:
    """Cut the tree at `tree_tile` from `stand_tile` facing `facing` (needs a
    party member with Cut + Cascade Badge). FRLG flow: face tree → A → yes.
    No-op if the tree object is already gone (cut earlier this map load)."""
    from modules.context import context
    from modules.map import get_map_objects
    from modules.map_data import MapFRLG
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )

    from modules.player import get_player_avatar

    if isinstance(map_key, MapFRLG):
        map_key = map_key.value
    # Same-level walk only: the stand tile is in the cut edge's from-component,
    # where the route's earlier legs deliver us. Full navigate_to here can
    # recurse (route to the stand crosses another cut edge → perform_cut →
    # navigate_to → ...); if we're NOT where the plan assumed, this raises a
    # path error and the caller's replan machinery takes over.
    yield from navigate_same_level(map_key, tuple(stand_tile))
    tree_present = any(
        o.current_coords == tuple(tree_tile) and "isPlayer" not in o.flags for o in get_map_objects()
    )
    if tree_present:
        yield from ensure_facing_direction(facing)
        context.emulator.press_button("A")
        yield
        yield from wait_for_yes_no_question("Yes")
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")
    if tree_present:
        # Verify the cut actually happened — a fainted/absent Cut user leaves
        # the tree standing and the old code shuffled against it forever.
        still_there = any(
            o.current_coords == tuple(tree_tile) and "isPlayer" not in o.flags for o in get_map_objects()
        )
        if still_there:
            raise SkillError(
                f"Cut on {map_key} {tuple(tree_tile)} did not remove the tree "
                "(Cut user fainted or unavailable?)"
            )

    # Step ACROSS the (now-cleared) tree tile into the destination component.
    # Essential even when the tree was already cut: the graph still models the
    # two sides as joined ONLY by this cut edge, so without physically crossing,
    # the next re-plan re-selects the same edge and perform_cut no-ops forever
    # (a yieldless tight loop). Bounded + position-checked (a raw hold into a
    # wall never terminates); stop as soon as a step stalls.
    for _ in range(2):
        before = get_player_avatar().local_coordinates
        context.emulator.reset_held_buttons()
        context.emulator.hold_button(facing)
        for _ in range(24):
            yield
        context.emulator.reset_held_buttons()
        for _ in range(8):
            yield
        if get_player_avatar().local_coordinates == before:
            break


def _story_gated_warp_dests() -> frozenset:
    """Destination maps the graph can walk into geometrically but the game
    blocks with a SCRIPT (not collision, so calculate_path can't see it):
    - Saffron's four gate guards refuse entry until you hand over tea.
    - The Cycling Road (Route 17 + its gates) has a `NeedBikeTrigger` that
      refuses entry without a Bicycle — the graph otherwise routes UP the
      Cycling Road (fewer warps) to reach Route 16, hitting the bike wall.
    Both are item/flag gates the badge-count epoch key misses."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.memory import get_event_flag

    gated = set()
    if not get_event_flag("GOT_TEA"):
        gated.add((3, 10))  # SAFFRON_CITY
    bike = get_item_by_name("Bicycle")
    if bike is None or get_item_bag().quantity_of(bike) == 0:
        gated |= {(3, 35), (26, 0), (26, 1)}  # ROUTE17 (Cycling Road) + Route 18 East gate 1F/2F
    return frozenset(gated)


def _cut_available() -> bool:
    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    if not get_event_flag("BADGE02_GET"):
        return False
    # The Cut user must be CONSCIOUS: a fainted mule can't cut, and plans that
    # offer un-executable cut edges shuffle at the tree forever (Route 16
    # pocket, mule at 0 HP — the plan kept saying "cut", the cut kept silently
    # not happening). With cut edges off, plans route around; after a heal
    # they come back.
    return any(
        p.current_hp > 0 and any(lm is not None and lm.move.name == "Cut" for lm in p.moves)
        for p in get_party()
        if not p.is_egg
    )


_nav_graphs: dict[str, dict | None] = {}  # epoch -> parsed graph | None
_rebuild_attempted: set[str] = set()


def story_epoch() -> str:
    """Graph section key: badge count plus the story flags that permanently
    change walkable geometry within a badge epoch (a cleared Snorlax opens a
    road no badge marks). Extend the flag list when a new permanent-roadblock
    class appears (Silph Co doors, ...) — an unlisted one leaves the graph
    stale until the next badge."""
    from modules.memory import get_event_flag

    badges = sum(1 for n in range(1, 9) if get_event_flag(f"BADGE{n:02d}_GET"))
    suffix = "".join(
        tag
        for tag, flag in (
            ("+snx12", "HIDE_ROUTE_12_SNORLAX"),
            ("+snx16", "HIDE_ROUTE_16_SNORLAX"),
            # Silph cleared: the Rocket guarding the Saffron gym door is gone
            # — the gym's whole interior was orphaned in pre-clear graphs.
            ("+silph", "HIDE_SAFFRON_ROCKETS"),
        )
        if get_event_flag(flag)
    )
    return f"{badges}{suffix}"


def _load_nav_graph() -> dict | None:
    """The current story epoch's graph from data/nav_graph.json:
    {"comp": {tile: component_id}, "walk": {cid: [cid, ...]}} (walk = directed
    same-level one-way edges: ledges, guard-gated gaps).

    Connectivity depends on story gates, so sections are keyed by an epoch
    (story_epoch(): badge count + geometry-changing flags). A missing epoch
    section is built in-process — pure calculate_path computation, no frames
    advanced. None means graph planning is unavailable (build failed);
    callers fall back to live search.
    """
    epoch = story_epoch()
    if epoch in _nav_graphs:
        return _nav_graphs[epoch]

    import json

    from dexbot import PROJECT_ROOT

    path = PROJECT_ROOT / "data" / "nav_graph.json"

    def read_section() -> dict | None:
        try:
            raw = json.loads(path.read_text())["epochs"][epoch]
            comp = {}
            for key, cid in raw["components"].items():
                mg, mn, x, y = (int(v) for v in key.split(","))
                comp[((mg, mn), (x, y))] = cid
            walk: dict[int, list] = {}
            for a, b in raw["walk_edges"]:
                walk.setdefault(a, []).append(b)
            cut: dict[int, list] = {}
            for a, b, tree_map, tree, stand, facing in raw["cut_edges"]:
                cut.setdefault(a, []).append(
                    (b, {"cut": True, "map": tuple(tree_map), "tree": tuple(tree), "stand": tuple(stand), "facing": facing})
                )
            return {"comp": comp, "walk": walk, "cut": cut}
        except Exception:
            return None

    graph = read_section()
    if graph is None and epoch not in _rebuild_attempted:
        _rebuild_attempted.add(epoch)
        try:
            from dexbot.build_navgraph import build

            build(None)
            graph = read_section()
        except Exception:
            graph = None
    _nav_graphs[epoch] = graph
    return graph


def _find_component(
    position, comp, walkable, mutual_only: bool = False, max_candidates: int = 6, exclude: frozenset = frozenset()
) -> int | None:
    """The component CONTAINING `position` (mutual reachability with its
    representative, tested nearest-first). One-way reachability is not enough:
    the nearest rep can belong to a ledge pocket below the player — enterable
    but exitless — and BFS from that dead-end component reaches nothing.
    Falls back to the first one-way-reachable component if none is mutual.

    The scan is CAPPED: any sane position's containing component is among the
    nearest few reps, and each failed reverse check is a multi-second
    full-region A* — an uncapped scan from a walled-in strip costs minutes and
    re-runs forever (the two-hour standstills)."""
    level = _map_level(position[0])
    pos_global = _global_coords(position[0], position[1])

    def distance(tile) -> int:
        g = _global_coords(tile[0], tile[1])
        if g is None or pos_global is None:
            return 0
        return abs(g[0] - pos_global[0]) + abs(g[1] - pos_global[1])

    nearest_rep: dict[int, tuple] = {}
    for tile, cid in comp.items():
        if _map_level(tile[0]) != level:
            continue
        if cid not in nearest_rep or distance(tile) < distance(nearest_rep[cid]):
            nearest_rep[cid] = tile
    one_way = None
    # Same-map reps first: interiors have NO global coordinates, so pure
    # distance ranking degenerates to arbitrary order there and the capped
    # scan can miss the position's own component entirely (every plan from
    # inside a Pokémon Center failed). A position's containing component
    # always includes its map's own portal tiles.
    ranked = sorted(
        ((cid, tile) for cid, tile in nearest_rep.items() if cid not in exclude),
        key=lambda kv: (kv[1][0] != position[0], distance(kv[1])),
    )
    for cid, tile in ranked[:max_candidates]:
        # Tight A* budget: the containing component's rep is nearby by
        # construction, so a probe needing >3k nodes is a "no" — full-budget
        # failures here were the 60-120s planning wedges.
        if walkable(position, tile, max_nodes=3_000):
            if walkable(tile, position, max_nodes=3_000):
                return cid
            if one_way is None:
                one_way = cid
    return None if mutual_only else one_way


def _plan_via_graph(start, dest, blacklist, walkable) -> list | None:
    """BFS over precomputed components joined by warp edges (cost 1) and
    directed one-way walk edges (cost 0: ledge drops etc.).

    Returns the warp-tile route, or None to fall back to live planning (graph
    missing, no component reachable from start, or no route to dest).
    """
    from collections import deque

    graph = _load_nav_graph()
    if graph is None:
        return None
    comp = graph["comp"]

    # Per-plan failure memo: a failed A* is expensive (never cached globally —
    # transient NPC walls) but deterministic WITHIN one plan; without this, the
    # dest scan re-ran identical failures for hours of CPU (USR1-diagnosed).
    failed: set = set()
    outer_walkable = walkable

    def walkable(a, b, max_nodes: int = 20_000) -> bool:  # noqa: A001 — deliberate shadow
        key = (a, b)
        if key in failed:
            return False
        result = outer_walkable(a, b, max_nodes=max_nodes)
        if not result:
            failed.add(key)
        return result

    gated = _story_gated_warp_dests()
    warp_adj: dict[int, list] = {}
    for elist in _get_warp_edges().values():
        for src_map, src_coords, dst_map, dst_coords in elist:
            src_tile = (src_map, src_coords)
            if src_tile in blacklist or tuple(dst_map) in gated:
                continue
            a = comp.get(src_tile)
            b = comp.get((dst_map, dst_coords))
            if a is not None and b is not None:
                warp_adj.setdefault(a, []).append((b, src_tile))

    # Stitch split TINY interiors (gate buildings): their bike-check trigger /
    # counter tiles read as walls when the map isn't loaded, so the build cuts
    # e.g. the Route 15 and Route 18 gates into two components each and the
    # whole Fuchsia corridor "vanishes" (get_rods stalled in Lavender with
    # every plan returning None). Crossing a LOADED gate executes fine — the
    # badge-5 runs crossed both. Story gating is unaffected: it drops the warp
    # edges INTO a gated map, not interior edges. Dungeons (real splits:
    # Strength boulders) are excluded by the size cap.
    from modules.map_path import _get_all_maps_metadata

    stitch: dict[tuple, set] = {}
    for (m, _xy), cid in comp.items():
        stitch.setdefault(m, set()).add(cid)
    extra_walk: dict[int, list] = {}
    for m, cids in stitch.items():
        pm = _get_all_maps_metadata().get(tuple(m))
        if len(cids) > 1 and pm is not None and pm.size[0] * pm.size[1] <= 200:
            for a in cids:
                for b in cids:
                    if a != b:
                        extra_walk.setdefault(a, []).append(b)
    # Pokémon Mansion switch doors (fork map_path._FLAG_DOORS): with the
    # switch SET, the 1F drop-pocket's doors stand open — stitch pocket and
    # hall so post-key exits plan (the static build saw them closed; the
    # size cap above excludes a map this big).
    from modules.memory import get_event_flag

    if get_event_flag("POKEMON_MANSION_SWITCH_STATE"):
        pocket = comp.get(((1, 59), (19, 22)))  # 3F-hole drop landing
        hall = comp.get(((1, 59), (10, 13)))  # 2F stairs / entrance region
        if pocket is not None and hall is not None and pocket != hall:
            extra_walk.setdefault(pocket, []).append(hall)
            extra_walk.setdefault(hall, []).append(pocket)
    # Lazily test "can this component walk to dest" only for components with a
    # tile on dest's level, using the component tile nearest to dest.
    dest_level = _map_level(dest[0])
    dest_global = _global_coords(dest[0], dest[1])

    def distance_to_dest(tile) -> int:
        g = _global_coords(tile[0], tile[1])
        if g is None or dest_global is None:
            return 0
        return abs(g[0] - dest_global[0]) + abs(g[1] - dest_global[1])

    dest_reps: dict[int, list] = {}
    for tile, cid in comp.items():
        if _map_level(tile[0]) != dest_level:
            continue
        dest_reps.setdefault(cid, []).append(tile)
    for cid in dest_reps:
        # Spread sample (nearest / middle / farthest): the nearest tiles can
        # all sit in one sub-pocket that cannot walk to dest even though the
        # component mostly can (Vermilion's dock pocket vs. the rest of the
        # city after the ship departs — story drift the epoch key misses).
        tiles = sorted(dest_reps[cid], key=distance_to_dest)
        dest_reps[cid] = list(dict.fromkeys([tiles[0], tiles[len(tiles) // 2], tiles[-1]]))

    # Fast path: find dest's CONTAINING component up front (mutual with a rep,
    # nearest-first) and BFS to that id — a few A* total, instead of testing
    # every popped dest-level component against dest (the expensive scan below
    # stays only as fallback for one-way pockets, bounded by the failure memo).
    dest_cid = None
    # Same-map first, then distance — see _find_component for why (interiors
    # have no global coordinates, so distance alone mis-ranks them).
    ranked_dest = sorted(
        dest_reps.items(), key=lambda kv: (kv[1][0][0] != dest[0], distance_to_dest(kv[1][0]))
    )
    for cid, tiles in ranked_dest[:6]:  # capped like the entry scan — see _find_component
        rep = tiles[0]
        if walkable(rep, dest, max_nodes=3_000) and walkable(dest, rep, max_nodes=3_000):
            dest_cid = cid
            break

    # Direct-walk short-circuit: if the destination is simply walkable from the
    # start (same level, no obstruction right now), the answer is the empty
    # route — no warps, no cuts. Without this, a plan from a spot that already
    # walks to dest can still route through a (redundant) cut edge, and after
    # physically crossing that tree the re-plan picks it AGAIN — a no-op loop.
    # GUARDED by component knowledge: when start and dest belong to KNOWN
    # DIFFERENT components, the direct A* is guaranteed to fail — and a failed
    # A* exhausts the whole connected region (post-Snorlax level 180 = most of
    # Kanto, tens of seconds); five candidate tiles per catch objective blew
    # the 120s step budget on pure exhausts. Skip it and let the BFS route.
    def _finalize(route):
        # A route made ONLY of cut edges deserves a direct-walk double-check:
        # cut trees respawn per map load, so the graph's split can be STALE
        # (tree currently down = both sides one region). Returning the cut
        # route then shuttles the player across the tree line forever — walk
        # to the stand, no-op cut, step back across, re-plan, repeat (203
        # plans/stall observed). If start already walks to dest, say so.
        if (
            route
            and all(isinstance(s, dict) and s.get("cut") for s in route)
            and _map_level(start[0]) == _map_level(dest[0])
            and walkable(start, dest)
        ):
            return []
        return route

    # Entry-component fallback: the nearest mutual component can be a SHADOW
    # (a single-tile comp minted for a cut-edge stand when a transient NPC
    # walled the build's mutual check) whose only edge is disabled — the BFS
    # then finds nothing even though the NEXT-nearest mutual comp routes fine.
    # Try up to 3 distinct entry components before giving up.
    cut_ok = _cut_available()
    direct_walk_tried = False
    excluded: set = set()
    for _entry_attempt in range(3):
        entry = _find_component(start, comp, walkable, exclude=frozenset(excluded))

        # Direct-walk short-circuit (first attempt only): if the destination is
        # simply walkable from the start, the answer is the empty route.
        # GUARDED by component knowledge: known-different components mean the
        # direct A* is guaranteed to fail, and a failed A* exhausts the whole
        # connected region (post-Snorlax Kanto — tens of seconds each).
        if (
            not direct_walk_tried
            and _map_level(start[0]) == _map_level(dest[0])
            and (entry is None or dest_cid is None or entry == dest_cid)
            and walkable(start, dest)
        ):
            return []
        direct_walk_tried = True
        if entry is None:
            return None

        # 0-1 BFS: walk edges are free, warp edges cost one leg. Cut edges
        # (cost 1) are traversable when a party member can use Cut — the route
        # then carries an action step ({"cut": ...}) executed at that point.
        queue = deque([(entry, [])])
        seen = {entry}
        while queue:
            cid, route = queue.popleft()
            if dest_cid is not None:
                if cid == dest_cid:
                    return _finalize(route)
            elif any(walkable(rep, dest) for rep in dest_reps.get(cid, ())):
                return _finalize(route)
            for next_cid in graph["walk"].get(cid, []):
                if next_cid not in seen:
                    seen.add(next_cid)
                    queue.appendleft((next_cid, route))
            for next_cid in extra_walk.get(cid, []):
                if next_cid not in seen:
                    seen.add(next_cid)
                    queue.appendleft((next_cid, route))
            for next_cid, src_tile in warp_adj.get(cid, []):
                if next_cid not in seen:
                    seen.add(next_cid)
                    queue.append((next_cid, [*route, src_tile]))
            if cut_ok:
                for next_cid, action in graph["cut"].get(cid, []):
                    if next_cid not in seen:
                        seen.add(next_cid)
                        queue.append((next_cid, [*route, action]))
        excluded.add(entry)
    return None  # no graph route (e.g. blacklisted bridge) — let live search try


def _plan_warp_route(
    start: tuple[tuple[int, int], tuple[int, int]],
    dest: tuple[tuple[int, int], tuple[int, int]],
    blacklist: frozenset = frozenset(),
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Plan the warp-tile route from `start` to `dest`.

    Fast path: BFS over the precomputed connectivity graph (a handful of live
    A* to place start/dest in components). Fallback: the live best-first
    search below, kept for a missing/stale graph.
    """
    import os as _os
    import time as _time

    if _os.environ.get("DEXBOT_NAV_DEBUG"):
        print(f"[nav] plan {start} -> {dest} (blacklist {len(blacklist)})", flush=True)
    t0 = _time.monotonic()
    route = _plan_via_graph(start, dest, frozenset(blacklist), _walkable)
    graph_seconds = _time.monotonic() - t0
    if graph_seconds > 5:
        print(f"[nav] slow graph plan {graph_seconds:.1f}s {start} -> {dest} (route: {route is not None})")
    if route is not None:
        return route
    t0 = _time.monotonic()
    try:
        return _plan_warp_route_live(start, dest, blacklist)
    finally:
        live_seconds = _time.monotonic() - t0
        if live_seconds > 5:
            print(f"[nav] slow LIVE plan {live_seconds:.1f}s {start} -> {dest}")


def _plan_warp_route_live(
    start: tuple[tuple[int, int], tuple[int, int]],
    dest: tuple[tuple[int, int], tuple[int, int]],
    blacklist: frozenset = frozenset(),
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Best-first search over reachable warp endpoints; returns the warp tiles.

    Each candidate leg is A*-verified with `_walkable`, because map "levels" are
    NOT reliably walkable-contiguous: whole regions share a level yet are only
    linked through warps (Cerulean↔Vermilion via the Underground Path, Saffron
    gated between). A pure graph would emit a direct walk the executor can't
    follow. To stay fast we explore warps *best-first* by global-coordinate
    distance to the destination (heads toward the goal instead of opening every
    building door), backed by the `_walkable` cache and a per-plan A* budget.
    """
    import heapq

    edges = _get_warp_edges()
    checks = [0]

    def walkable(a, b) -> bool:
        checks[0] += 1
        if checks[0] > _WALKABLE_BUDGET:
            raise SkillError(f"Route planning budget exceeded from {start} to {dest}")
        return _walkable(a, b)

    dest_level = _map_level(dest[0])
    dest_map = tuple(dest[0])
    dest_global = _global_coords(dest[0], dest[1])
    if _map_level(start[0]) == dest_level and walkable(start, dest):
        return []

    # Fast path — direct entry into the destination MAP (e.g. a building door on
    # the current overworld level). Building interiors have no global offset, so
    # the distance heuristic can't rank their doors and the search would fan into
    # every building; check same-level warps that land in the target map first.
    for warp_map, warp_coords, warp_dest_map, warp_dest_coords in edges.get(_map_level(start[0]), []):
        if tuple(warp_dest_map) == dest_map and (warp_map, warp_coords) not in blacklist:
            if walkable(start, (warp_map, warp_coords)):
                return [(warp_map, warp_coords)]

    def priority(landing) -> int:
        g = _global_coords(landing[0], landing[1])
        if g is None or dest_global is None:
            return 0
        return abs(g[0] - dest_global[0]) + abs(g[1] - dest_global[1])

    visited: set = set()
    counter = 0
    # Priority: (warp-count so far, distance heuristic, tiebreak). Minimising the
    # number of warps first makes this a verified-walkable Dijkstra — it returns
    # the *shortest* real route (e.g. Cerulean→Vermilion via the 2-warp
    # Underground Path) instead of a convoluted building-weave the pure distance
    # heuristic would wander into (interiors have no global coords).
    heap: list = [(0, 0, 0, start, [])]  # (num_warps, heuristic, tiebreak, position, route)
    while heap:
        _, _, _, position, route = heapq.heappop(heap)
        for warp_map, warp_coords, warp_dest_map, warp_dest_coords in edges.get(_map_level(position[0]), []):
            key = (warp_map, warp_coords)
            if key in visited or key in blacklist:
                continue
            if not walkable(position, (warp_map, warp_coords)):
                continue
            visited.add(key)
            landing = (warp_dest_map, warp_dest_coords)
            if _map_level(warp_dest_map) == dest_level and walkable(landing, dest):
                return [*route, key]
            counter += 1
            heapq.heappush(heap, (len(route) + 1, priority(landing), counter, landing, [*route, key]))
    raise SkillError(f"No warp route from {start} to {dest}")


def enter_center(center) -> Generator:
    """Navigate to a Pokémon Center's door coordinate and GUARANTEE we end up
    inside. Standing on the door coordinate already (Silph Co's exit lands
    exactly on Saffron's) makes navigate_to a no-op with no warp — step up
    into the door explicitly and wait for the map change."""
    from modules.context import context
    from modules.player import get_player_avatar

    outdoor_map = center.value[0].value if hasattr(center.value[0], "value") else tuple(center.value[0])
    yield from navigate_to(center.value[0], center.value[1])
    if tuple(get_player_avatar().map_group_and_number) == tuple(outdoor_map):
        context.emulator.reset_held_buttons()
        context.emulator.hold_button("Up")
        for _ in range(24):
            yield
        context.emulator.reset_held_buttons()
        for _ in range(180):
            if tuple(get_player_avatar().map_group_and_number) != tuple(outdoor_map):
                break
            yield
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    yield from wait_for_player_avatar_to_be_controllable("B")
    if tuple(get_player_avatar().map_group_and_number) == tuple(outdoor_map):
        raise SkillError(f"Could not enter the {center.name} Pokémon Center")


def walk_carefully(map_key, dest: tuple[int, int], max_repaths: int = 8) -> Generator:
    """Walk to `dest` on the current level with TAP-AND-SETTLE inputs — for
    forced-movement areas (spin-tile mazes). Upstream's walker holds the
    direction key, which fights the slides and retries internally forever;
    here each waypoint is one short tap, then we wait for the slide to resolve
    and re-path from wherever the maze actually delivered us. calculate_path
    models slides exactly (waypoint coords are slide LANDINGS)."""
    from modules.context import context
    from modules.map_data import MapFRLG
    from modules.map_path import PathFindingError, calculate_path
    from modules.player import get_player_avatar, player_avatar_is_controllable

    if isinstance(map_key, MapFRLG):
        map_key = map_key.value
    dest = tuple(dest)

    def settle(max_frames: int = 900) -> Generator:
        # Position stable for 20 frames = the slide finished. (The controllable
        # flag flickers true mid-slide and exits too early.)
        last = None
        stable = 0
        for _ in range(max_frames):
            yield
            avatar = get_player_avatar()
            cur = (avatar.map_group_and_number, avatar.local_coordinates)
            if cur == last:
                stable += 1
                if stable >= 20 and player_avatar_is_controllable():
                    return
            else:
                stable = 0
                last = cur

    for _ in range(max_repaths):
        yield from settle()
        avatar = get_player_avatar()
        pos = (avatar.map_group_and_number, avatar.local_coordinates)
        if pos == (map_key, dest):
            return
        try:
            waypoints = calculate_path(pos, (map_key, dest))
        except PathFindingError as e:
            raise SkillError(f"walk_carefully: no path {pos} -> {dest}: {e}")
        derailed = False
        for wp in waypoints:
            avatar = get_player_avatar()
            tap_from = (avatar.map_group_and_number, avatar.local_coordinates)
            context.emulator.reset_held_buttons()
            context.emulator.hold_button(wp.walking_direction)
            # Release on the FIRST coord change (probe_maze's technique), cap 40
            # frames (turn + on-foot step ≈ 24). A fixed 12-frame tap overshoots
            # on the bike (8 frames/tile → 2 tiles/tap), derailing every step
            # and exhausting max_repaths.
            for _ in range(40):
                yield
                avatar = get_player_avatar()
                if (avatar.map_group_and_number, avatar.local_coordinates) != tap_from:
                    break
            context.emulator.reset_held_buttons()
            yield from settle()
            avatar = get_player_avatar()
            if avatar.map_group_and_number != map_key:
                return  # a warp fired (stairs/door) — the caller continues from there
            if (avatar.map_group_and_number, avatar.local_coordinates) != (tuple(wp.map), tuple(wp.coordinates)):
                derailed = True  # a slide took us elsewhere — re-path from here
                break
        if not derailed:
            avatar = get_player_avatar()
            if (avatar.map_group_and_number, avatar.local_coordinates) == (map_key, dest):
                return
    raise SkillError(f"walk_carefully: could not reach {dest} on {map_key} after {max_repaths} re-paths")


_spinner_maps: dict = {}

# Route 17's Cycling Road is one continuous forced-movement slope ("Cycling
# Road Pull Down" tiles — ROM-scanned: the only map that has them). Parked
# against an obstacle there, the engine keeps the avatar in a perpetual
# sliding state (running_state MOVING, heldMovementActive never set), so every
# upstream held-direction wait — ensure_facing_direction, standing-still,
# controllable — yields forever with zero input (the beat_koga 30k-frame
# stall at (11,18)). Held taps DO register, and a released coast downhill is
# just a big derail walk_carefully re-paths from.
_FORCED_SLOPE_MAPS = frozenset({(3, 35)})  # ROUTE17


def _has_spinners(map_key) -> bool:
    """Whether a map contains forced-movement tiles (spin tiles, the Cycling
    Road slope) — those defeat the held-direction walker, so legs there use
    walk_carefully instead."""
    key = tuple(map_key)
    if key in _FORCED_SLOPE_MAPS:
        return True
    if key not in _spinner_maps:
        from modules.map_path import _get_all_maps_metadata

        pm = _get_all_maps_metadata().get(key)
        # Ledge hops are ALSO forced movement now (jump waypoints are
        # landings), but the held-direction walker handles those fine —
        # only omnidirectional forced tiles (spin arrows, ice, currents:
        # all four directions set) defeat it.
        _spinner_maps[key] = bool(pm) and any(
            t.forced_movement_to and len(t.forced_movement_to) >= 4 for t in pm.tiles
        )
    return _spinner_maps[key]


def _walk_out_of_pocket(max_steps: int = 24) -> Generator:
    """Blind-step out of an unmodeled pocket (a ledge strip with no portal
    tiles): try each direction until the position changes, up to `max_steps`
    tiles total, stopping as soon as the position resolves to a component.
    Down first — ledge drains point down far more often than not."""
    from modules.context import context
    from modules.player import get_player_avatar

    graph = _load_nav_graph()
    for _ in range(max_steps):
        avatar = get_player_avatar()
        position = (avatar.map_group_and_number, avatar.local_coordinates)
        # Mutual only: a one-way match means we can still be inside an
        # exitless strip that merely LOOKS connected downhill.
        if graph is not None and _find_component(position, graph["comp"], _walkable, mutual_only=True) is not None:
            return  # back on modeled ground
        for direction in ("Down", "Left", "Right", "Up"):
            before = get_player_avatar().local_coordinates
            context.emulator.reset_held_buttons()
            context.emulator.hold_button(direction)
            for _ in range(24):
                yield
            context.emulator.reset_held_buttons()
            for _ in range(12):  # let a ledge-hop animation finish
                yield
            if get_player_avatar().local_coordinates != before:
                break
        else:
            return  # walled in every direction — nothing more we can do here


def navigate_to(map, coordinates: tuple[int, int], run: bool = True) -> Generator:
    """Walk the player to `coordinates` on `map`, routing through warps if needed.

    A generator skill: drive it with dexbot.runner.run_skill.
    """
    from modules.map_data import MapFRLG
    from modules.modes._interface import BotModeError
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar
    from modules.tasks import get_global_script_context

    if isinstance(map, MapFRLG):
        map = map.value

    # Recover from an inherited script-lock: a skill may start with a dialogue
    # already open (a gate guard the previous objective walked into, a savestate
    # captured mid-script). Nothing can move until it closes, so drain it first
    # — B (not A) so an NPC we're facing doesn't just re-trigger.
    from modules.context import context as _ctx
    from modules.player import player_avatar_is_controllable

    for _frame in range(240):
        script = get_global_script_context()
        if player_avatar_is_controllable() and not (script and script.is_active):
            break
        if _frame % 12 == 0:
            _ctx.emulator.press_button("B")
        yield

    interruptions = 0
    blacklist: set = set()
    current_target = None
    target_failures = 0
    cached_route: list | None = None  # plan once; re-plan only after a failure
    while True:
        avatar = get_player_avatar()
        position = (avatar.map_group_and_number, avatar.local_coordinates)
        try:
            # Planning is expensive across Kanto, so amortize it over the whole
            # journey: plan once, then consume warp legs in sequence. A failure
            # clears the cache to force a fresh plan (with any new blacklist).
            if cached_route is None:
                for plan_attempt in range(3):
                    try:
                        cached_route = _plan_warp_route(position, (tuple(map), tuple(coordinates)), frozenset(blacklist))
                        break
                    except SkillError:
                        # Planning sees the world as it is *right now*: an NPC
                        # in a choke point (or a mid-door-exit object state)
                        # can transiently wall us in and fail every check.
                        # Wait for the world to settle and re-plan.
                        if plan_attempt == 2:
                            # A mid-leg ledge hop can strand us in a strip the
                            # graph can't model (no portal tiles, or only
                            # one-way reachable) — every plan fails. Step out
                            # physically (ledge strips always drain), then let
                            # the caller's retry re-plan from modeled ground.
                            # Unconditional: _walk_out_of_pocket no-ops fast
                            # when we're already on mutually-reachable ground.
                            yield from _walk_out_of_pocket()
                            raise
                        for _ in range(120):
                            yield
                        avatar = get_player_avatar()
                        position = (avatar.map_group_and_number, avatar.local_coordinates)
            if not cached_route:
                if _has_spinners(position[0]) or _has_spinners(map):
                    yield from walk_carefully(map, coordinates)
                else:
                    yield from navigate_same_level(map, coordinates, run=run)
                return
            step = cached_route[0]
            if isinstance(step, dict) and step.get("cut"):
                # Conditional edge: cut the tree, then continue the route.
                yield from perform_cut(step["map"], step["tree"], step["stand"], step["facing"])
                cached_route = cached_route[1:] or None
                target_failures = 0
                continue
            # Step onto the next warp; upstream follows it (final waypoint).
            warp_map, warp_coords = step
            current_target = (warp_map, warp_coords)
            if _has_spinners(position[0]) or _has_spinners(warp_map):
                # Spin-tile floors defeat the held-direction walker (it fights
                # the slides and retries internally forever) — tap-and-settle.
                yield from walk_carefully(warp_map, warp_coords)
            else:
                yield from navigate_same_level(warp_map, warp_coords, run=run)
            cached_route = cached_route[1:] or None  # consume; None re-plans final walk
            target_failures = 0
        except SkillError:
            # A leg desynced from reality (e.g. spin-maze slide momentum
            # carried us through a warp ahead of the route pointer, making the
            # next leg cross-level). Re-plan from wherever we actually are.
            cached_route = None
            interruptions += 1
            if interruptions > 30:
                raise
            yield  # one frame: keep each (possibly slow) re-plan in its own
            # controller step — 30 back-to-back re-plans in one step blew the
            # 120s watchdog with the avatar frozen.
            continue
        except BotModeError as e:
            # One-time overworld triggers (tutorial NPCs, etc.) interrupt walking.
            # Mash through the script, then re-plan from wherever we ended up.
            cached_route = None  # invalidate: re-plan from the new position
            interruptions += 1
            if interruptions > 30:
                raise
            if "are not on connected maps" in str(e) and current_target is not None:
                # The graph over-merged: this leg pairs maps in different
                # upstream connection clusters (Route 14 → Saffron through a
                # gate building). Permanently impossible as a walk — blacklist
                # at once and re-plan; letting it propagate crash-loops the
                # supervisor.
                blacklist.add(current_target)
                target_failures = 0
                yield  # own step per re-plan (see the SkillError path)
                continue
            if "Could not find a path" in str(e):
                # Either a wandering NPC (current + previous tile both count as
                # blocked) sitting in a choke point — wait it out — or the warp
                # is genuinely unreachable from this part of the level (levels
                # are not always internally connected): blacklist and re-plan.
                target_failures += 1
                if target_failures >= 3 and current_target is not None:
                    blacklist.add(current_target)
                    target_failures = 0
                    yield  # own step per re-plan (see the SkillError path)
                    continue
                for _ in range(120):
                    yield
                continue
            if not (get_global_script_context() and get_global_script_context().is_active):
                # Not a script interruption — e.g. "player not controllable" right
                # after a menu/dialogue closed. Give it a moment and retry once.
                from modules.player import player_avatar_is_controllable

                for _ in range(120):
                    if player_avatar_is_controllable():
                        break
                    yield
                else:
                    raise
                continue
            from modules.context import context
            from modules.tasks import task_is_active

            # Upstream's error path can leave movement buttons held, and resuming
            # while an NPC's scripted walk is still in flight can re-trigger the
            # event and deadlock the game script. Clear both before re-planning.
            context.emulator.reset_held_buttons()
            frame = 0
            while get_global_script_context() and get_global_script_context().is_active:
                frame += 1
                if frame % 48 == 24:
                    # Some FRLG tutorial boxes (sign lady's "press START to open
                    # the MENU") only dismiss on Start — A/B are swallowed.
                    context.emulator.press_button("Start")
                elif frame % 16 == 0:
                    context.emulator.press_button("A")
                elif frame % 16 == 8:
                    # B matters: facing an NPC, a pure A-mash closes a dialogue
                    # and immediately re-talks, looping forever (S.S. Anne ferry
                    # sailor). B advances text, answers NO, and never re-talks.
                    context.emulator.press_button("B")
                yield
            for frame in range(40):  # close a menu if a Start press opened one
                if frame % 10 == 0:
                    context.emulator.press_button("B")
                yield
            while task_is_active("ScriptMovement_MoveObjects"):
                yield
            yield from wait_for_player_avatar_to_be_controllable("A")
