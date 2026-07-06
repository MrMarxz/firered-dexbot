"""Read access to the generated knowledge base in data/."""

import json
from functools import cache

from dexbot import PROJECT_ROOT


@cache
def encounters() -> dict:
    return json.loads((PROJECT_ROOT / "data" / "encounters.json").read_text())


def best_encounter_map(species_name: str, method: str = "land") -> tuple[tuple[int, int], int]:
    """Return ((map_group, map_number), total_rate_percent) of the map where
    `species_name` is most common for the given encounter method."""
    best = None
    for key, table in encounters().items():
        rate = sum(e["encounter_rate"] for e in table[f"{method}_encounters"] if e["species_name"] == species_name)
        if rate > 0 and (best is None or rate > best[1]):
            group, number = key.split(",")
            best = ((int(group), int(number)), rate)
    if best is None:
        raise KeyError(f"No {method} encounters found for {species_name!r} in the knowledge base")
    return best
