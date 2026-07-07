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
from dexbot.runner import run_skill


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


def missing_catchable() -> list[tuple[str, tuple[int, int], int, dict]]:
    """(species, map, rate%, annotation) for every missing species catchable on an
    accessible AND currently-reachable map, most-common-first."""
    from modules.pokedex import get_pokedex

    owned = {s.name for s in get_pokedex().owned_species}
    best: dict[str, tuple[tuple[int, int], int, dict]] = {}
    for map_key, annotation in accessible_maps().items():
        table = encounters().get(f"{map_key[0]},{map_key[1]}")
        if table is None:
            continue
        if not _graph_reachable(map_key, annotation):
            continue
        rates: dict[str, int] = {}
        for entry in table["land_encounters"]:
            rates[entry["species_name"]] = rates.get(entry["species_name"], 0) + entry["encounter_rate"]
        for species, rate in rates.items():
            if species in owned:
                continue
            if species not in best or rate > best[species][1]:
                best[species] = (map_key, rate, annotation)
    queue = [(species, *info) for species, info in best.items()]
    # visit_last maps (one-way descents) go to the back regardless of rate.
    queue.sort(key=lambda item: (item[3].get("visit_last", False), -item[2], item[0]))
    return queue


# Route 2 south grass: mostly Rattata/Pidgey (Weedle only 5%, so little poison),
# no trainers, one screen from the Viridian Pokémon Center.
GRIND_SPOT = ((3, 20), (9, 58))
# Route 3 east grass: L6-8 wilds (double the XP), unlocked with badge 1.
GRIND_SPOT_BADGE1 = ((3, 21), (71, 14))


def _default_grind_spot() -> tuple[tuple[int, int], tuple[int, int]]:
    from modules.memory import get_event_flag

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


def restock_pokeballs_if_low(minimum: int = 10) -> None:
    """Top up Poké Balls to at least `minimum` before a catch trip (as affordable).

    Catch trips can be deep (Mt Moon B1F is ~10 minutes from a mart), so running
    dry mid-trip aborts the objective — stock up generously beforehand.
    """
    from modules.items import get_item_bag, get_item_by_name
    from modules.player import get_player

    from dexbot.openings import buy_pokeballs

    balls = get_item_bag().quantity_of(get_item_by_name("Poké Ball"))
    affordable = get_player().money // 200
    needed = minimum - balls
    if needed <= 0 or affordable < 1:
        return
    quantity = min(needed + 5, affordable, 40)
    run_skill(buy_pokeballs(quantity, _nearest_mart()), f"restock_{quantity}_pokeballs", timeout_frames=120_000)


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
    deferred: set = set()
    while True:
        queue = [q for q in missing_catchable() if q[0] not in deferred]
        if not queue:
            return caught
        restock_pokeballs_if_low()
        # Objective boundary: the optional LLM planner may pick any valid queue
        # entry; invalid/disabled/error → deterministic queue head (queue[0]).
        by_name = {f"catch_{entry[0]}": entry for entry in queue}
        chosen_name, rationale = choose_objective(capture_state(), list(by_name))
        species, map_key, rate, annotation = by_name[chosen_name]
        print(f"[planner] objective {chosen_name}: {rationale}")
        tile = tuple(annotation["safe_tile"]) if "safe_tile" in annotation else None

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

        try:
            run_skill(
                catch_species(species, map_key, tile),
                f"catch_{species}",
                timeout_frames=600_000,
                on_battle_started=make_catch_decider(species),
            )
        except SkillError as e:
            # Objective failed (unreachable, stranded, ...): defer it and move
            # on — a later story unlock usually fixes it. Never abort the loop.
            deferred.add(species)
            print(f"[planner] deferred {species}: {e}")
            _log_event(skill=f"catch_{species}", status="deferred", error=str(e))
            continue
        caught += 1
        print(f"[planner] caught {species} ({rate}% on {map_key})")
        # Keep slots open: a full party makes the next catch fail. HM mules
        # are kept by deposit_party_fodder itself.
        if len(get_party()) >= 5:
            from dexbot.boxes import deposit_party_fodder
            from dexbot.catching import fight_all_battles

            run_skill(
                deposit_party_fodder(keep=1),
                "deposit_fodder",
                timeout_frames=600_000,
                on_battle_started=fight_all_battles,
            )


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
