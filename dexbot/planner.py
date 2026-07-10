"""M6: deterministic dex planner v1.

Loop: pick the highest-value missing species whose best *accessible* map is
reachable (map annotations in data/dependencies.json), execute catch_species,
update dex state, repeat. Grinds the lead's level first when a target map is
annotated with a minimum level (trainer ambushes).

Acceptance:  .venv/bin/python -m dexbot.planner   (from fixtures/m4_pokedex.ss1)
→ completes every species catchable pre-Brock.
"""

import json
from typing import Generator

from dexbot import PROJECT_ROOT
from dexbot.catching import catch_species, ensure_healthy, make_catch_decider
from dexbot.kb import encounters
from dexbot.navigation import navigate_to
from dexbot.runner import SkillError, run_skill


def _map_annotations() -> dict:
    deps = json.loads((PROJECT_ROOT / "data" / "dependencies.json").read_text())
    return deps.get("maps", {})


def accessible_maps() -> dict[tuple[int, int], dict]:
    """Maps the bot may currently visit: annotated in dependencies.json with all
    flag requirements satisfied. Unannotated maps are treated as inaccessible
    (annotations grow as story progress unlocks areas)."""
    from modules.memory import get_event_flag

    result = {}
    for key, annotation in _map_annotations().items():
        if key.startswith("_"):
            continue
        if all(get_event_flag(flag) for flag in annotation.get("requires", [])):
            group, number = key.split(",")
            result[(int(group), int(number))] = annotation
    return result


def _graph_reachable(map_key: tuple[int, int], annotation: dict) -> bool:
    """Whether the nav graph can plan a route to this map from here. Story flags
    say a map is *unlocked*; this says it is *walkable-to* (Route 3 is unlocked
    at badge 1 but unreachable from Vermilion without field Cut)."""
    from modules.player import get_player_avatar

    from dexbot.catching import _encounter_tiles
    from dexbot.navigation import _load_nav_graph, _plan_via_graph, _walkable

    if _load_nav_graph() is None:
        return True  # no graph: keep the old optimistic behaviour
    avatar = get_player_avatar()
    pos = (avatar.map_group_and_number, avatar.local_coordinates)
    try:
        if "safe_tile" in annotation:
            tiles = [tuple(annotation["safe_tile"])]
        else:
            # Spread sample — one pocket of the map being unreachable (Route
            # 24's water-locked east grass) must not veto the whole map.
            all_tiles = _encounter_tiles(map_key)
            tiles = all_tiles[:: max(1, len(all_tiles) // 3)][:3]
        return any(_plan_via_graph(pos, (map_key, t), frozenset(), _walkable) is not None for t in tiles)
    except Exception:
        return False


# (encounter table key, catch_species method, required bag item)
_ENCOUNTER_METHODS = (
    ("land_encounters", "spin", None),
    ("old_rod_encounters", "old_rod", "Old Rod"),
    ("good_rod_encounters", "good_rod", "Good Rod"),
    ("super_rod_encounters", "super_rod", "Super Rod"),
)


def _shore_reachable(map_key: tuple[int, int], cache: dict) -> bool:
    """Whether a fishable SHORE tile on this map is walkable-to. Separate from
    land reachability: Fuchsia's pond is a fenced zoo pen — land tiles reach,
    shore tiles don't."""
    if map_key not in cache:
        from modules.player import get_player_avatar

        from dexbot.catching import _shore_tiles
        from dexbot.navigation import _plan_via_graph, _walkable

        try:
            tiles = [c for c, _f in _shore_tiles(map_key)]
        except Exception:
            cache[map_key] = False
            return False
        sample = tiles[:: max(1, len(tiles) // 3)][:3]
        avatar = get_player_avatar()
        pos = (avatar.map_group_and_number, avatar.local_coordinates)
        cache[map_key] = any(
            _plan_via_graph(pos, (map_key, t), frozenset(), _walkable) is not None for t in sample
        )
    return cache[map_key]


def missing_catchable() -> list[tuple[str, tuple[int, int], int, dict, str]]:
    """(species, map, rate%, annotation, method) for every missing species
    catchable on an accessible AND currently-reachable map — land spinning
    plus rod fishing for rods we own — most-common-first."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.pokedex import get_pokedex

    owned = {s.name for s in get_pokedex().owned_species}
    best: dict[str, tuple[tuple[int, int], int, dict, str]] = {}
    shore_cache: dict = {}
    for map_key, annotation in accessible_maps().items():
        table = encounters().get(f"{map_key[0]},{map_key[1]}")
        if table is None:
            continue
        land_ok = None  # lazy: only computed when the map has missing land species
        for kind, method, rod_item in _ENCOUNTER_METHODS:
            entries = table.get(kind) or []
            if not entries:
                continue
            if rod_item is not None and get_item_bag().quantity_of(get_item_by_name(rod_item)) == 0:
                continue
            rates: dict[str, int] = {}
            for entry in entries:
                rates[entry["species_name"]] = rates.get(entry["species_name"], 0) + entry["encounter_rate"]
            if all(s in owned for s in rates):
                continue
            if rod_item is None:
                if land_ok is None:
                    land_ok = _graph_reachable(map_key, annotation)
                if not land_ok:
                    continue
            elif not _shore_reachable(map_key, shore_cache):
                continue
            for species, rate in rates.items():
                if species in owned:
                    continue
                if species not in best or rate > best[species][1]:
                    best[species] = (map_key, rate, annotation, method)
    queue = [(species, *info) for species, info in best.items()]
    # visit_last maps (one-way descents) go to the back regardless of rate.
    queue.sort(key=lambda item: (item[3].get("visit_last", False), -item[2], item[0]))
    return queue


# Route 2 south grass: mostly Rattata/Pidgey (Weedle only 5%, so little poison),
# no trainers, one screen from the Viridian Pokémon Center.
GRIND_SPOT = ((3, 20), (9, 58))
# Route 3 east grass: L6-8 wilds (double the XP), unlocked with badge 1.
GRIND_SPOT_BADGE1 = ((3, 21), (71, 14))
# Route 11 grass: L11-15 wilds, next to Vermilion — the badge-2+ era spot
# (Route 3 is unreachable from eastern Kanto without field Cut).
GRIND_SPOT_BADGE2 = ((3, 29), (35, 9))


def _default_grind_spot() -> tuple[tuple[int, int], tuple[int, int]]:
    from modules.memory import get_event_flag

    if get_event_flag("BADGE02_GET"):
        return GRIND_SPOT_BADGE2
    return GRIND_SPOT_BADGE1 if get_event_flag("BADGE01_GET") else GRIND_SPOT


def grind_levels(
    target_level: int,
    map_key: tuple[int, int] | None = None,
    tile: tuple[int, int] | None = None,
) -> Generator:
    """Fight wild encounters until the party's slot-0 Pokémon (the starter)
    reaches `target_level`, healing at a Pokémon Center between stints —
    chip damage and poison would otherwise wipe the party over a long grind."""
    from modules.pokemon import StatusCondition
    from modules.modes.util.higher_level_actions import spin
    from modules.pokemon_party import get_party

    def done() -> bool:
        # "rotate" on faint/low-HP permanently reorders the party, so track the
        # strongest member rather than assuming the starter stays in slot 0.
        return max(p.level for p in get_party() if not p.is_egg) >= target_level

    def needs_heal() -> bool:
        lead = get_party()[0]
        return lead.current_hp / lead.total_hp < 0.4 or lead.status_condition != StatusCondition.Healthy

    from dexbot.catching import _encounter_tiles
    from dexbot.runner import _log_event

    if map_key is None:
        map_key, tile = _default_grind_spot()

    while not done():
        _log_event(
            skill="grind_levels",
            status="progress",
            levels=[(p.species.name, p.level) for p in get_party()],
        )
        yield from ensure_healthy(minimum_fraction=0.95)
        yield from navigate_to(map_key, tile or _encounter_tiles(map_key)[0])
        yield from spin(stop_condition=lambda: done() or needs_heal())


def restock_pokeballs_if_low(minimum: int = 15) -> None:
    """Top up Poké Balls to at least `minimum` before a catch trip (as affordable).

    Catch trips can be deep (Mt Moon B1F is ~10 minutes from a mart), so running
    dry mid-trip aborts the objective — stock up generously beforehand.
    """
    from modules.items import get_item_bag, get_item_by_name
    from modules.player import get_player

    from dexbot.openings import buy_pokeballs

    # Count every catch-capable ball — the upstream catch strategy picks the
    # best one in the bag, so 39 Great Balls with 1 Poké Ball is NOT "low"
    # (counting only Poké Balls sent the bot marching to a mart mid-corridor).
    balls = sum(
        get_item_bag().quantity_of(get_item_by_name(name))
        for name in ("Poké Ball", "Great Ball", "Ultra Ball")
    )
    needed = minimum - balls
    if needed <= 0:
        return
    if get_player().money < needed * 200:
        _fund_by_selling(needed * 200 + 1000)
    if get_player().money < needed * 200:
        if not _earn_by_vs_seeker():
            _earn_by_patrol()
        _fund_by_selling(needed * 200 + 1000)
    from dexbot.openings import buy_items

    # Great Balls (1.5x) when funded — full-HP throws at rate-190 targets ate
    # 10-15 Poké Balls apiece; the multiplier pays for itself. The upstream
    # catch strategy picks the best ball in the bag automatically.
    if get_player().money >= (needed + 3) * 600:
        quantity = min(needed + 5, get_player().money // 600, 40)
        run_skill(
            buy_items([("Great Ball", quantity)], _nearest_mart()),
            f"restock_{quantity}_greatballs",
            timeout_frames=120_000,
        )
        return
    affordable = get_player().money // 200
    if affordable < 1:
        return
    quantity = min(needed + 5, affordable, 40)
    run_skill(buy_pokeballs(quantity, _nearest_mart()), f"restock_{quantity}_pokeballs", timeout_frames=120_000)


# Trainer-gauntlet routes for one-shot income patrols: walking end to end
# triggers line-of-sight fights (each pays out) via the battle listener.
# Beaten trainers never re-pay, so each route patrols once per process.
# Route 9, Route 11, Rock Tunnel 1F/B1F (trainer-dense), Route 10, Route 6.
_PATROL_ROUTES = [(3, 27), (3, 29), (1, 81), (1, 82), (3, 28), (3, 24)]
_patrolled: set = set()


def _route11_trainer_approach_tiles() -> list[tuple[int, int]]:
    """Walkable tiles adjacent to each Route 11 rematch trainer, west→east.
    Walking these (after a Vs Seeker use) crosses the re-armed trainers'
    line-of-sight — the OLD sweep walked grass tiles and missed them, earning
    ~624 then nothing; visiting the trainers earns ~3.5k/lap (measured)."""
    from modules.map import get_map_data
    from modules.map_data import MapFRLG

    route = MapFRLG.ROUTE11
    trainers = sorted(
        (o.local_coordinates for o in get_map_data(route, (0, 0)).objects
         if getattr(o, "trainer_type", None) is not None and str(getattr(o, "trainer_type", "")) != "None"),
        key=lambda c: c[0],
    )
    approaches = []
    for tx, ty in trainers:
        for dx, dy in ((0, 1), (0, -1), (-1, 0), (1, 0)):
            try:
                if not get_map_data(route, (tx + dx, ty + dy)).collision:
                    approaches.append((tx + dx, ty + dy))
                    break
            except Exception:
                continue
    return approaches


def _earn_by_vs_seeker(on_battle_started=None) -> bool:
    """Renewable income: on Route 11, use the registered Vs Seeker (Select) to
    re-arm rematches, then walk to each trainer — line-of-sight rematch fights
    pay out (~3.5k/lap, doubled while the lead holds the Amulet Coin). Each leg
    is its OWN run_skill so a battle mid-walk can't deadlock the whole lap
    (mirrors _earn_by_patrol). Returns False if the Seeker isn't owned yet
    (caller falls back to one-shot patrols).

    `on_battle_started` overrides the battle policy — pass a level-balancing
    strategy to double the laps as XP training for a low-level party member
    (rematch trainers pay 5-10x wild XP)."""
    from modules.context import context
    from modules.items import get_item_bag, get_item_by_name
    from modules.player import get_player
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run

    from dexbot.catching import ensure_healthy, fight_all_battles
    from dexbot.navigation import navigate_to
    from dexbot.runner import SkillError, SkillTimeout

    if on_battle_started is None:
        on_battle_started = fight_all_battles
    if get_item_bag().quantity_of(get_item_by_name("VS Seeker")) == 0:
        return False
    route_key = (3, 29)  # Route 11
    approaches = _route11_trainer_approach_tiles()
    if not approaches:
        return False
    money_before = get_player().money

    # The Seeker recharges on STEPS (100). The approach list is in object
    # order, so approaches[0]/[-1] can be near-neighbours — shuttling between
    # them walked ~40 steps and every post-first lap re-armed 0 trainers and
    # earned nothing. Shuttle between the true x-extremes for ≥120 steps, then
    # fire it from the BAG at a mid-route tile: the registered-item Select
    # shortcut silently no-ops in this harness, and the Seeker only re-arms
    # trainers VISIBLE ON SCREEN when used (both diagnosed 2026-07-10 —
    # Task_VsSeeker_2/3 fire from the bag flow, nothing fires from Select).
    by_x = sorted(approaches, key=lambda t: t[0])
    near, far = by_x[0], by_x[-1]
    # ponytail: (42,9) is the one Route 11 approach empirically confirmed to
    # arm a rematch (Task_VsSeeker_3 + trainer walk-up); the mid-route tile's
    # neighbour has no rematch table and the scan fizzles at Task_VsSeeker_1.
    # Scan per-tile if this trainer ever dries up.
    fire_tile = (42, 9) if (42, 9) in approaches else by_x[len(by_x) // 2]
    span = abs(far[0] - near[0]) + abs(far[1] - near[1])
    trips = max(2, -(-120 // max(2 * span, 2)))

    def arm_seeker():
        # Manual bag drive: upstream's use_item_from_bag A-mashes through the
        # context menu and the USE never registers for the Seeker (verified:
        # zero VsSeeker tasks via the helper, Task_VsSeeker_2/3 fire with
        # spaced A presses).
        from modules.menuing import StartMenuNavigator, scroll_to_item_in_bag

        yield from ensure_healthy(minimum_fraction=0.6)
        for _ in range(trips):
            yield from navigate_to(route_key, far)
            yield from navigate_to(route_key, near)
        yield from navigate_to(route_key, fire_tile)  # a rematchable trainer is on screen here
        yield from StartMenuNavigator("BAG").step()
        yield from scroll_to_item_in_bag(get_item_by_name("VS Seeker"))
        for _ in range(2):  # A: open context menu; A: USE
            context.emulator.press_button("A")
            for _ in range(45):
                yield
        for _ in range(300):  # scan animation + '!!'; an armed trainer may walk up and fight
            yield
        yield from wait_for_no_script_to_run("B")

    try:
        run_skill(arm_seeker(), "vs_seeker_arm", timeout_frames=400_000, on_battle_started=on_battle_started)
    except (SkillError, SkillTimeout) as e:
        print(f"[planner] vs-seeker arm failed: {e}")
        return True
    for approach in approaches:
        try:
            run_skill(
                navigate_to(route_key, approach),
                "vs_seeker_leg",
                timeout_frames=200_000,
                on_battle_started=on_battle_started,
            )
        except (SkillError, SkillTimeout) as e:
            print(f"[planner] vs-seeker leg {approach} skipped: {str(e)[:60]}")
            continue
    print(f"[planner] vs-seeker income: {get_player().money - money_before}")
    return True


def _earn_by_patrol(on_battle_started=None) -> bool:
    """Fight an unfought trainer route for money when selling can't fund a
    restock. ponytail: Vs Seeker rematches are the renewable M8 income engine;
    unfought route gauntlets are the pre-Seeker bridge (and first-time fights
    are what CREATES rematch inventory — an unbeaten trainer can't be re-armed).
    Returns False when every patrol route has been visited this process.
    `on_battle_started` overrides the battle policy (e.g. level-balancing XP
    training)."""
    from dexbot.catching import _encounter_tiles, ensure_healthy, fight_all_battles
    from dexbot.navigation import _plan_via_graph, _walkable, navigate_to
    from dexbot.runner import SkillError
    from modules.player import get_player_avatar

    if on_battle_started is None:
        on_battle_started = fight_all_battles
    for route_key in _PATROL_ROUTES:
        if route_key in _patrolled:
            continue
        _patrolled.add(route_key)
        avatar = get_player_avatar()
        pos = (avatar.map_group_and_number, avatar.local_coordinates)
        tiles = _encounter_tiles(route_key)
        waypoints = [t for t in (tiles[0], tiles[-1]) if _plan_via_graph(pos, (route_key, t), frozenset(), _walkable)]
        if not waypoints:
            continue
        try:
            run_skill(ensure_healthy(minimum_fraction=0.9), "patrol_heal", timeout_frames=300_000)
            for tile in waypoints:
                run_skill(
                    navigate_to(route_key, tile),
                    f"patrol_{route_key[0]}_{route_key[1]}",
                    timeout_frames=600_000,
                    on_battle_started=on_battle_started,
                )
        except SkillError as e:
            print(f"[planner] patrol {route_key} failed: {e}")
        return True  # one route per call — usually enough for a restock
    return False


# Sold when broke, in order: collectibles, then Super Potions above a reserve
# of 4. TMs are NOT sellable in FRLG (they live in the TM Case, which the mart
# sell menu cannot open).
_SELLABLE = ("Nugget", "Pearl", "Big Pearl", "Stardust", "Star Piece", "Tinymushroom", "Big Mushroom")


def _fund_by_selling(target_money: int) -> None:
    """Best-effort: sell junk-tier bag items at the nearest mart until we have
    `target_money`. ponytail: trainer-rematch income (Vs Seeker) is the real
    M8 economy engine; this liquidation keeps catch trips funded until then."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.player import get_player

    from dexbot.openings import sell_items

    to_sell: list[tuple[str, int]] = []
    projected = get_player().money
    bag = get_item_bag()

    def plan_sale(name: str, quantity: int) -> None:
        nonlocal projected
        item = get_item_by_name(name)
        if quantity > 0 and projected < target_money:
            to_sell.append((name, quantity))
            projected += (item.price // 2) * quantity

    # Free loot first: uncollected item balls on the current map (they hold
    # Nuggets, potions, balls — the bot walked past them for four badges).
    from modules.player import get_player_avatar

    from dexbot.items_ground import collect_item_balls, uncollected_item_balls

    here = get_player_avatar().map_group_and_number
    if uncollected_item_balls(here):
        try:
            from dexbot.catching import fight_all_battles

            run_skill(collect_item_balls(here), "collect_items", timeout_frames=300_000, on_battle_started=fight_all_battles)
        except SkillError as e:
            print(f"[planner] item collection failed: {e}")

    for name in _SELLABLE:
        plan_sale(name, bag.quantity_of(get_item_by_name(name)))
    if projected < target_money:
        reserve = 4
        surplus = bag.quantity_of(get_item_by_name("Super Potion")) - reserve
        plan_sale("Super Potion", max(0, surplus))
    if to_sell:
        run_skill(sell_items(to_sell, _nearest_mart()), f"fund_sell_{len(to_sell)}_items", timeout_frames=120_000)


def _nearest_mart():
    """The mart with the fewest-warp route from here (graph planning only — an
    unreachable mart answers None in milliseconds instead of a 30s live search)."""
    from modules.map_data import MapFRLG
    from modules.player import get_player_avatar

    from dexbot.navigation import _plan_via_graph, _walkable

    avatar = get_player_avatar()
    pos = (avatar.map_group_and_number, avatar.local_coordinates)
    best = None
    for m in MapFRLG:
        if not m.name.endswith("_MART"):
            continue
        route = _plan_via_graph(pos, (m.value, (4, 3)), frozenset(), _walkable)
        if route is not None and (best is None or len(route) < best[1]):
            best = (m, len(route))
    return best[0] if best else MapFRLG.VIRIDIAN_CITY_MART


def plan_and_catch_all() -> int:
    """Main loop. Returns the number of species caught."""
    from modules.pokemon_party import get_party

    from dexbot.llm_planner import choose_objective
    from dexbot.telemetry import capture_state

    from dexbot.runner import SkillError, _log_event

    caught = 0
    caught_since_reset = 0
    deferred: set = set()
    while True:
        queue = [q for q in missing_catchable() if q[0] not in deferred]
        if not queue:
            # Retry deferrals as long as passes make progress: a transient
            # failure (whiteout recovery wedge, wandering NPC wall) usually
            # succeeds on a fresh skill start. No progress twice → truly stuck.
            if deferred and caught_since_reset > 0:
                print(f"[planner] retrying {len(deferred)} deferred: {sorted(deferred)}")
                deferred.clear()
                caught_since_reset = 0
                continue
            return caught
        restock_pokeballs_if_low()
        # Objective boundary: the optional LLM planner may pick any valid queue
        # entry; invalid/disabled/error → deterministic queue head (queue[0]).
        by_name = {f"catch_{entry[0]}": entry for entry in queue}
        chosen_name, rationale = choose_objective(capture_state(), list(by_name))
        species, map_key, rate, annotation, method = by_name[chosen_name]
        print(f"[planner] objective {chosen_name}: {rationale} (method {method})")
        tile = tuple(annotation["safe_tile"]) if method == "spin" and "safe_tile" in annotation else None

        # Field a diverse, catch-rate-optimized team (sleep/False-Swipe/para
        # roles + HM mules), leaving one slot for the catch. No-op when the
        # party already matches, so this is cheap after the first assembly.
        from dexbot.catching import fight_all_battles
        from dexbot.team import TeamObjective, assemble_party

        field_moves = tuple(annotation.get("field_moves", ("Cut",)))
        try:
            run_skill(
                assemble_party(TeamObjective(kind="catch", field_moves=field_moves)),
                "assemble_party",
                timeout_frames=600_000,
                on_battle_started=fight_all_battles,
            )
        except SkillError as e:
            print(f"[planner] team assembly deferred: {e}")  # proceed with whatever party we have

        min_level = annotation.get("min_lead_level", 0)
        if get_party()[0].level < min_level:
            # Grind somewhere already safe (the forest safe tile) before
            # entering a map with trainer ambushes.
            from dexbot.catching import fight_all_battles

            run_skill(
                grind_levels(min_level),
                f"grind_to_{min_level}",
                timeout_frames=600_000,
                on_battle_started=fight_all_battles,
            )

        failed = False
        for attempt in range(2):
            try:
                run_skill(
                    catch_species(species, map_key, tile, method=method),
                    f"catch_{species}",
                    timeout_frames=600_000,
                    on_battle_started=make_catch_decider(species),
                )
                break
            except SkillError as e:
                # Failure boundary: the LLM may pick a recovery action;
                # options[0] ("defer") is the deterministic default — a later
                # story unlock usually fixes it. Never abort the loop.
                action = "defer"
                if attempt == 0:
                    from dexbot.llm_planner import consult_on_failure

                    action, rationale = consult_on_failure(
                        f"catch_{species}", str(e), capture_state(), ["defer", "heal_then_retry", "retry"]
                    )
                    print(f"[planner] {species} failed → {action} ({rationale})")
                if action == "defer":
                    deferred.add(species)
                    failed = True
                    print(f"[planner] deferred {species}: {e}")
                    _log_event(skill=f"catch_{species}", status="deferred", error=str(e))
                    break
                _log_event(skill=f"catch_{species}", status="advisor_retry", error=str(e), action=action)
                if action == "heal_then_retry":
                    from dexbot.catching import ensure_healthy, fight_all_battles

                    run_skill(
                        ensure_healthy(),
                        "advisor_heal",
                        timeout_frames=600_000,
                        on_battle_started=fight_all_battles,
                    )
        if failed:
            continue
        caught += 1
        caught_since_reset += 1
        print(f"[planner] caught {species} ({rate}% on {map_key})")
        # Checkpoint every catch: the 5-minute interval alone can lose several
        # catches to a kill/crash (three re-fished after one mid-wedge kill).
        from modules.context import context as _ctx
        from modules.memory import GameState as _GS, get_game_state as _ggs

        if _ggs() == _GS.OVERWORLD:
            _ctx.emulator.create_save_state(suffix="caught")
        # No post-catch deposit needed: the catch team is assembled fresh
        # before each objective (above), which trims the previous catch (now a
        # 6th party mon) back to a box. `deposit_party_fodder` remains in
        # boxes.py as the primitive assemble_party builds on.


def main() -> None:
    import sys

    from dexbot.emulator import setup_headless_emulator

    fixture = sys.argv[1] if len(sys.argv) > 1 else "m4_pokedex.ss1"
    out = sys.argv[2] if len(sys.argv) > 2 else "m6_pre_brock_dex.ss1"

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / fixture).read_bytes())
    context.emulator.run_single_frame()

    total = plan_and_catch_all()

    from modules.pokedex import get_pokedex

    owned = sorted(s.name for s in get_pokedex().owned_species)
    print(f"[planner] done — caught {total}, dex owns {len(owned)}: {owned}")
    (PROJECT_ROOT / "fixtures" / out).write_bytes(context.emulator.get_save_state())


if __name__ == "__main__":
    main()
