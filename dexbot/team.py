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
    # Catch objectives leave one party slot free: the caught mon lands there
    # (a full 6-party makes upstream's catch fail — M8 limitation). The next
    # objective's assemble trims the previous catch back to a box.
    if objective.kind == "catch":
        cap = min(cap, 5)
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


def _party_ids() -> set:
    from modules.pokemon_party import get_party

    return {bytes(p.data[:4]) for p in get_party() if not p.is_egg}


def _party_size() -> int:
    from modules.pokemon_party import get_party

    return len([p for p in get_party() if not p.is_egg])


def _find_box_mon(id_bytes: bytes):
    from modules.pokemon_storage import get_pokemon_storage

    for box in get_pokemon_storage().boxes:
        for slot in box.slots:
            if slot is not None and not slot.pokemon.is_empty and bytes(slot.pokemon.data[:4]) == id_bytes:
                return slot.pokemon
    return None


def give_item_to_party_mon(item_name: str, party_index: int = 0) -> Generator:
    """Give a bag item to a party mon (start menu → POKéMON → mon → ITEM →
    GIVE — upstream's PokemonPartyMenuNavigator drives the menus). No-op if
    the mon already holds it; raises if it holds something else."""
    from modules.context import context
    from modules.items import get_item_bag, get_item_by_name
    from modules.memory import GameState, get_game_state
    from modules.menuing import PokemonPartyMenuNavigator, StartMenuNavigator
    from modules.player import player_avatar_is_controllable
    from modules.pokemon_party import get_party

    from dexbot.runner import SkillError

    item = get_item_by_name(item_name)
    holder = get_party()[party_index]
    if holder.held_item is not None:
        if holder.held_item.name == item_name:
            return
        raise SkillError(
            f"Party slot {party_index} already holds {holder.held_item.name}; won't overwrite with {item_name}"
        )
    if get_item_bag().quantity_of(item) == 0:
        raise SkillError(f"No {item_name} in the bag to give")

    yield from StartMenuNavigator("POKEMON").step()
    yield from PokemonPartyMenuNavigator(party_index, "give_item", item_to_give=item).step()

    for frame in range(600):  # back out to a controllable overworld
        if get_game_state() == GameState.OVERWORLD and player_avatar_is_controllable():
            break
        if frame % 8 == 0:
            context.emulator.press_button("B")
        yield
    held = get_party()[party_index].held_item
    if held is None or held.name != item_name:
        raise SkillError(f"Failed to give {item_name} to party slot {party_index}")


def make_false_swipe_trainer(species: str = "Cubone", move: str = "False Swipe"):
    """Battle strategy for training the catch-kit weakener: upstream's
    LevelBalancingBattleStrategy keeps the lowest-level mon as lead (switching
    in the strongest when it runs low, so the runt still gets shared XP), plus:
    - evolution VETO while the trainee hasn't learned the move yet (Cubone gets
      False Swipe at 33; evolved Marowak not until 39);
    - the move is always accepted when offered, replacing a junk status move."""
    from modules.battle_strategies.level_balancing import LevelBalancingBattleStrategy

    class FalseSwipeTrainer(LevelBalancingBattleStrategy):
        def party_can_battle(self) -> bool:
            # LevelBalancing refuses to battle when the trainee is fainted —
            # fatal mid-rematch (trainers can't be declined). Any conscious
            # mon can battle; the trainee just misses that fight's XP.
            return super(LevelBalancingBattleStrategy, self).party_can_battle()

        def should_allow_evolution(self, pokemon, party_index: int) -> bool:
            if pokemon.species.name == species and not any(
                lm is not None and lm.move.name == move for lm in pokemon.moves
            ):
                return False
            return super().should_allow_evolution(pokemon, party_index)

        def which_move_should_be_replaced(self, pokemon, new_move) -> int:
            if new_move.name == move:
                for junk in ("Growl", "Tail Whip", "Leer", "Focus Energy"):
                    for i, lm in enumerate(pokemon.moves):
                        if lm is not None and lm.move.name == junk:
                            return i
            return super().which_move_should_be_replaced(pokemon, new_move)

    return FalseSwipeTrainer()


def train_false_swipe(species: str = "Cubone", move: str = "False Swipe") -> Generator:
    """Level the catch-kit weakener until it knows `move` (Cubone → False Swipe
    at L33): assemble a party that includes it (select_party's False-Swipe role
    picks it by species), then grind wilds with heal stints. Drive via
    run_skill(..., on_battle_started=lambda e: make_false_swipe_trainer())."""
    from modules.pokemon_party import get_party

    from dexbot.runner import SkillError, _log_event

    def trainee():
        for p in get_party():
            if not p.is_egg and p.species.name == species:
                return p
        return None

    def knows_move() -> bool:
        p = trainee()
        return p is not None and any(lm is not None and lm.move.name == move for lm in p.moves)

    if knows_move():
        return
    yield from assemble_party(TeamObjective(kind="catch", field_moves=("Cut",)))
    if trainee() is None:
        raise SkillError(f"train_false_swipe: no {species} in party after assembly")

    from modules.modes.util.higher_level_actions import spin
    from modules.pokemon import StatusCondition

    from dexbot.catching import ensure_healthy
    from dexbot.navigation import navigate_to
    from dexbot.planner import GRIND_SPOT_BADGE2

    def needs_heal() -> bool:
        p = trainee()
        lead = get_party()[0]
        return (
            p is None
            or p.current_hp == 0
            or lead.current_hp / lead.total_hp < 0.4
            or lead.status_condition != StatusCondition.Healthy
        )

    map_key, tile = GRIND_SPOT_BADGE2
    while not knows_move():
        p = trainee()
        _log_event(skill="train_false_swipe", status="progress", trainee_level=p.level if p else None)
        yield from ensure_healthy(minimum_fraction=0.95)
        yield from navigate_to(map_key, tile)
        yield from spin(stop_condition=lambda: knows_move() or needs_heal())
    _log_event(skill="train_false_swipe", status="learned", trainee_level=trainee().level)


def assemble_party(objective: TeamObjective) -> Generator:
    """Walk to the nearest PC and realize `select_party(objective)`: deposit
    party mons not wanted, withdraw wanted mons from boxes. Keeps ≥1 conscious
    mon in the party throughout and never exceeds 6."""
    from modules.context import context
    from modules.modes.util.pc_interaction import PCAction, interact_with_pc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_standing_still
    from modules.player import get_player_avatar
    from modules.pokemon_party import get_party
    from modules.state_cache import state_cache

    from dexbot.boxes import _find_pc_tile
    from dexbot.catching import _pick_reachable_center
    from dexbot.navigation import navigate_to
    from dexbot.runner import SkillError, _log_event

    target = select_party(objective, enumerate_roster())
    target_ids = {m.id_bytes for m in target}
    if _party_ids() == target_ids:
        return  # no-op: don't walk to a PC to do nothing

    _log_event(skill="assemble_party", status="phase", phase="to_pc")
    center = _pick_reachable_center()
    yield from navigate_to(center.value[0], center.value[1])  # door warp → inside
    interior = get_player_avatar().map_group_and_number
    pc_tile = _find_pc_tile(interior)
    yield from navigate_to(interior, (pc_tile[0], pc_tile[1] + 1))
    yield from wait_for_player_avatar_to_be_standing_still("B")
    yield from ensure_facing_direction("Up")

    # Deposit unwanted party mons — one interact_with_pc per mon (batching
    # stales upstream's captured indices as the party shrinks), reset the cache
    # after each. Never drop below one conscious mon.
    _log_event(skill="assemble_party", status="phase", phase="deposit")
    for p in list(get_party()):
        if p.is_egg or bytes(p.data[:4]) in target_ids:
            continue
        if _party_size() <= 1:
            break
        yield from interact_with_pc([PCAction.deposit_pokemon_to_box(p)])
        state_cache.reset()

    # Withdraw wanted mons still in boxes — one per call, re-finding the box
    # object each time (slot objects go stale after a withdrawal).
    _log_event(skill="assemble_party", status="phase", phase="withdraw")
    for want in target:
        if want.id_bytes in _party_ids() or _party_size() >= 6:
            continue
        boxed = _find_box_mon(want.id_bytes)
        if boxed is not None:
            yield from interact_with_pc([PCAction.withdraw_pokemon_from_box(boxed)])
            state_cache.reset()

    yield from wait_for_no_script_to_run("B")
    result = _party_ids()
    if result != target_ids:
        raise SkillError(f"assemble_party: party {sorted(result)} != target {sorted(target_ids)}")
