"""M8: team roster & PC assembly — assemble the best party for an objective.

`select_party` decides WHO belongs in the party (pure, deterministic);
`assemble_party` realizes that selection at a PC. This replaces the old
"deposit everything but the strongest" behavior so the bot fields a diverse,
catch-rate-optimized team instead of a solo lead.

Catch-rate math (Gen III, all multiplicative): low HP ~×3, sleep ×2, Ultra
Ball ×2. The catch kit therefore wants a sleep user, a False Swipe user (to 1
HP without a KO), a non-powder paralysis backup (Grass targets resist powder),
and a low-level safe chipper — plus the HM mules for the route.
"""

from dataclasses import dataclass
from typing import Generator

# Status / weakening move sets (KB-verified move names).
SLEEP_MOVES = frozenset({"Spore", "Sleep Powder", "Hypnosis", "Sing", "Lovely Kiss", "Grass Whistle"})
PARALYSIS_MOVES = frozenset({"Thunder Wave", "Stun Spore", "Body Slam", "Glare"})
NON_POWDER_PARALYSIS = frozenset({"Thunder Wave", "Body Slam", "Glare"})  # work on Grass-types
# FRLG level-up learners of False Swipe (Cubone L33 → Marowak L39; Scyther L16
# Safari; Farfetch'd L46 Vermilion trade). Verified against species.json.
FALSE_SWIPE_LEARNERS = frozenset({"Cubone", "Marowak", "Scyther", "Farfetch'd", "Farfetch’d"})


@dataclass(frozen=True)
class TeamObjective:
    kind: str  # "catch" | "gym" | "travel"
    field_moves: tuple[str, ...] = ()
    prefer_offense_types: tuple[str, ...] = ()
    avoid_defense_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class RosterMon:
    id_bytes: bytes
    location: str  # "party" | "box:{box}:{slot}"
    species_name: str
    national_dex: int
    level: int
    types: tuple[str, ...]
    moves: tuple[str, ...]


def _mon_to_roster(mon, location: str) -> RosterMon:
    return RosterMon(
        id_bytes=bytes(mon.data[:4]),
        location=location,
        species_name=mon.species.name,
        national_dex=mon.species.national_dex_number,
        level=mon.level,
        types=tuple(t.name for t in mon.species.types),
        moves=tuple(m.move.name for m in mon.moves if m is not None),
    )


def enumerate_roster() -> list[RosterMon]:
    """Every owned individual across party and PC boxes (eggs/empties skipped)."""
    from modules.pokemon_party import get_party
    from modules.pokemon_storage import get_pokemon_storage

    roster: list[RosterMon] = []
    for p in get_party():
        if not p.is_egg:
            roster.append(_mon_to_roster(p, "party"))
    for bi, box in enumerate(get_pokemon_storage().boxes):
        for slot in box.slots:
            if slot is not None and not slot.pokemon.is_egg and not slot.pokemon.is_empty:
                roster.append(_mon_to_roster(slot.pokemon, f"box:{bi}:{slot.slot_index}"))
    return roster
