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


def missing_catchable() -> list[tuple[str, tuple[int, int], int, dict]]:
    """(species, map, rate%, annotation) for every missing species catchable on an
    accessible map, most-common-first — deterministic priority queue."""
    from modules.pokedex import get_pokedex

    owned = {s.name for s in get_pokedex().owned_species}
    best: dict[str, tuple[tuple[int, int], int, dict]] = {}
    for map_key, annotation in accessible_maps().items():
        table = encounters().get(f"{map_key[0]},{map_key[1]}")
        if table is None:
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
    queue.sort(key=lambda item: (-item[2], item[0]))
    return queue


# Route 2 south grass: mostly Rattata/Pidgey (Weedle only 5%, so little poison),
# no trainers, one screen from the Viridian Pokémon Center.
GRIND_SPOT = ((3, 20), (9, 58))


def grind_levels(
    target_level: int,
    map_key: tuple[int, int] = GRIND_SPOT[0],
    tile: tuple[int, int] | None = GRIND_SPOT[1],
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

    while not done():
        yield from ensure_healthy(minimum_fraction=0.95)
        yield from navigate_to(map_key, tile or _encounter_tiles(map_key)[0])
        yield from spin(stop_condition=lambda: done() or needs_heal())


def plan_and_catch_all() -> int:
    """Main loop. Returns the number of species caught."""
    from modules.pokemon_party import get_party

    from dexbot.llm_planner import choose_objective
    from dexbot.telemetry import capture_state

    caught = 0
    while True:
        queue = missing_catchable()
        if not queue:
            return caught
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

        run_skill(
            catch_species(species, map_key, tile),
            f"catch_{species}",
            timeout_frames=600_000,
            on_battle_started=make_catch_decider(species),
        )
        caught += 1
        print(f"[planner] caught {species} ({rate}% on {map_key})")


def main() -> None:
    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m4_pokedex.ss1").read_bytes())
    context.emulator.run_single_frame()

    from dexbot.openings import buy_pokeballs

    run_skill(buy_pokeballs(5), "buy_more_pokeballs", timeout_frames=60_000)

    total = plan_and_catch_all()

    from modules.pokedex import get_pokedex

    owned = sorted(s.name for s in get_pokedex().owned_species)
    print(f"[planner] done — caught {total}, dex owns {len(owned)}: {owned}")
    (PROJECT_ROOT / "fixtures" / "m6_pre_brock_dex.ss1").write_bytes(context.emulator.get_save_state())


if __name__ == "__main__":
    main()
