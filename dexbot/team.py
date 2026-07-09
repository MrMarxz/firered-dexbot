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


def _viability(m: RosterMon) -> tuple:
    # ponytail: level captures "trained-ness" and correlates with evolution
    # stage, so we skip a species-data stage lookup; deterministic dex-number
    # tie-break. Add a stage multiplier only if selection quality demands it.
    return (m.level, -m.national_dex)


def _knows_any(m: RosterMon, moves: frozenset) -> bool:
    return any(mv in moves for mv in m.moves)


def _is_false_swipe_user(m: RosterMon) -> bool:
    return "False Swipe" in m.moves or m.species_name in FALSE_SWIPE_LEARNERS


def select_party(objective: TeamObjective, roster: list[RosterMon], cap: int = 6) -> list[RosterMon]:
    """Deterministically pick ≤cap mons: mandatory HM mules, then catch-kit
    roles (sleep / False-Swipe / non-powder paralysis) for catch objectives,
    then viability-fill under a type-diversity cap."""
    chosen: dict[bytes, RosterMon] = {}

    def add(m):
        if m is not None and m.id_bytes not in chosen and len(chosen) < cap:
            chosen[m.id_bytes] = m

    # 1. Mandatory HM mules (highest-viability holder per field move).
    for fm in objective.field_moves:
        holders = sorted((m for m in roster if fm in m.moves), key=_viability, reverse=True)
        if holders:
            add(holders[0])

    # 2. Catch-kit roles — add the best available for each missing role.
    if objective.kind == "catch":
        for pred in (
            lambda m: _knows_any(m, SLEEP_MOVES),  # ×2 status, strongest lever
            _is_false_swipe_user,  # guaranteed 1 HP (Cubone→False Swipe)
            lambda m: _knows_any(m, NON_POWDER_PARALYSIS),  # Grass-safe paralysis backup
        ):
            if not any(pred(m) for m in chosen.values()):
                cands = sorted((m for m in roster if pred(m) and m.id_bytes not in chosen),
                               key=_viability, reverse=True)
                add(cands[0] if cands else None)

    # 3. Fill remaining slots by viability under a type-diversity cap
    #    (≤2 mons sharing a primary type unless nothing else remains).
    def primary(m):
        return m.types[0] if m.types else "?"

    type_count: dict[str, int] = {}
    for m in chosen.values():
        type_count[primary(m)] = type_count.get(primary(m), 0) + 1

    remaining = sorted((m for m in roster if m.id_bytes not in chosen), key=_viability, reverse=True)
    deferred = []
    for m in remaining:
        if len(chosen) >= cap:
            break
        if type_count.get(primary(m), 0) >= 2:
            deferred.append(m)
            continue
        add(m)
        type_count[primary(m)] = type_count.get(primary(m), 0) + 1
    for m in deferred:  # relax the diversity cap only if slots remain
        if len(chosen) >= cap:
            break
        add(m)

    return sorted(chosen.values(), key=_viability, reverse=True)


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
