"""Per-species catch playbook, DERIVED from the knowledge base (species.json)
— the constitution's rule: game facts come from the KB, never improvised.

The generic weakening policy (False Swipe → sleep → chip → ball) assumes a
target that stands still, can be hit by Normal moves, and won't blow itself
up. Three KB-derivable species classes break those assumptions:

- **Ghosts** (Gastly line …): False Swipe and Normal chip moves can't connect
  — rotating to the Marowak weakener loops forever (the catch_Gastly 600k-
  frame timeout).
- **Boomers** (Voltorb, Koffing, Graveler … learn Selfdestruct/Explosion):
  never chip one that's awake — sleep first or throw.
- **Teleporters** (Abra line, Natu line): gone on their first free turn — no
  setup; status immediately if possible, else throw at full HP.

Everything else keeps the generic policy. Safari species are separately
covered by upstream's documented bait/rock tables.
"""

from dataclasses import dataclass
from functools import lru_cache

# KB move ids (moves are stored by id in species.json learnsets).
_BOOM_MOVE_IDS = {"120", "153"}  # Selfdestruct, Explosion
_TELEPORT_MOVE_ID = "100"


@dataclass(frozen=True)
class CatchPlan:
    is_ghost: bool  # no False Swipe, no Normal-type chip
    sleep_first: bool  # knows a boom move — never chip while awake
    status_urgent: bool  # teleports away — act on the first turn


@lru_cache(maxsize=None)
def _species_index() -> dict:
    import json

    from dexbot import POKEBOT_ROOT

    data = json.loads((POKEBOT_ROOT / "modules" / "data" / "species.json").read_text())
    return {s["name"]: s for s in data}


@lru_cache(maxsize=None)
def catch_plan(species_name: str) -> CatchPlan:
    sp = _species_index().get(species_name)
    if sp is None:
        return CatchPlan(False, False, False)
    level_up_ids = set(sp.get("learnset", {}).get("level_up", {}).keys())
    return CatchPlan(
        is_ghost="Ghost" in sp.get("types", ()),
        sleep_first=bool(level_up_ids & _BOOM_MOVE_IDS),
        status_urgent=_TELEPORT_MOVE_ID in level_up_ids,
    )
