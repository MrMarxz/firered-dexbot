"""M5: catch_species — navigate to the best encounter spot and catch the target.

Battle-side logic (ball choice by catch-rate math, status moves) is upstream's
CatchStrategy; non-target encounters are fled from. The party lead is healed at
a Pokémon Center whenever it drops below half HP.

Run acceptance:  .venv/bin/python -m dexbot.catching
"""

import sys
from typing import Generator

from dexbot import PROJECT_ROOT
from dexbot.kb import best_encounter_map
from dexbot.navigation import navigate_to
from dexbot.runner import SkillError, run_skill


def _species_is_owned(species_name: str) -> bool:
    from modules.pokedex import get_pokedex

    return any(s.name == species_name for s in get_pokedex().owned_species)


def _encounter_tiles(map_group_and_number: tuple[int, int]) -> list[tuple[int, int]]:
    """Tiles on the map that can spawn encounters, inner tiles first (nicer to
    spin on). Land (grass/cave) only — surf tiles are unreachable without Surf;
    water maps fall back to their water tiles (for when Surf exists)."""
    from modules.map_path import _get_all_maps_metadata

    path_map = _get_all_maps_metadata()[map_group_and_number]
    all_tiles = [t for t in path_map.tiles if t.has_encounters]
    # Water is elevation 1 (ponds) or 0 (ocean — Route 12's surf tiles read 0,
    # slipping past an `!= 1` check and feeding the reachability probe nothing
    # but water); land stands at 3+.
    land = [t for t in all_tiles if t.elevation not in (0, 1)]
    tiles = [t.local_coordinates for t in (land or all_tiles)]
    if not tiles:
        raise SkillError(f"Map {map_group_and_number} has no encounter tiles")
    center_x = sum(t[0] for t in tiles) / len(tiles)
    center_y = sum(t[1] for t in tiles) / len(tiles)
    return sorted(tiles, key=lambda t: abs(t[0] - center_x) + abs(t[1] - center_y))


class WeakeningCatchStrategy:
    """CatchStrategy that first chips the target down (never risking a KO) to
    roughly double per-ball catch odds — halves ball spend vs. full-HP throws."""

    def __new__(cls):
        from modules.battle_strategies import BattleStrategyUtil, TurnAction
        from modules.battle_strategies.catch import CatchStrategy

        class _Strategy(CatchStrategy):
            def decide_turn(self, battle_state):
                opponent = battle_state.opponent.active_battler
                if opponent.current_hp / opponent.total_hp > 0.4:
                    util = BattleStrategyUtil(battle_state)
                    own = battle_state.own_side.active_battler
                    best = None
                    for index, learned in enumerate(own.moves):
                        if learned is None or learned.pp == 0 or learned.move.base_power == 0:
                            continue
                        damage = util.calculate_move_damage_range(learned.move, own, opponent)
                        # Worst case (max roll, crit) must not KO the target.
                        crit_max = util.calculate_move_damage_range(learned.move, own, opponent, True).max
                        if crit_max < opponent.current_hp and (best is None or damage.max > best[1]):
                            best = (index, damage.max)
                    if best is not None:
                        return TurnAction.use_move(best[0])
                return super().decide_turn(battle_state)

        return _Strategy()


def make_healing_battle_strategy(flee_below: float = 0.35):
    """Universal battle policy for a solo/overleveled champion with thin supplies:

    - low HP + a potion in the bag → drink it (works in any battle);
    - low HP, no potion, WILD battle → run away (the grind/catch loop heals
      between battles, so this avoids whiteout thrash);
    - low HP, no potion, TRAINER battle → fight on (can't flee) and let a
      faint trigger whiteout recovery rather than a hard "cannot battle" error.
    """
    from modules.battle_strategies import DefaultBattleStrategy, TurnAction
    from modules.items import get_item_bag, get_item_by_name

    class HealingBattleStrategy(DefaultBattleStrategy):
        def decide_turn(self, battle_state):
            own = battle_state.own_side.active_battler
            if own is not None and own.current_hp / own.total_hp < flee_below:
                bag = get_item_bag()
                for name in ("Potion", "Super Potion", "Hyper Potion"):
                    item = get_item_by_name(name)
                    if bag.quantity_of(item) > 0:
                        return TurnAction.use_item_on(item, own.party_index)
                if not battle_state.is_trainer_battle:
                    return TurnAction.run_away()
            return super().decide_turn(battle_state)

    return HealingBattleStrategy()


def fight_all_battles(encounter):
    """on_battle_started policy for every context (grind, gym, story): drink
    potions when low, flee low wild battles, fight trainers to the end."""
    return make_healing_battle_strategy()


# Grinding uses the same universal policy.
grind_battles = fight_all_battles


def make_catch_decider(target_species: str):
    """on_battle_started callback: catch the target, fight trainers (no choice),
    flee from other wild encounters."""

    def on_battle_started(encounter):
        from modules.modes._interface import BattleAction

        if encounter is None:
            return None  # trainer battle — default strategy fights it
        if encounter.pokemon.species.name == target_species:
            return WeakeningCatchStrategy()
        return BattleAction.RunAway

    return on_battle_started




def _ball_count() -> int:
    """Total usable balls in the bag (any kind the catch strategy can throw)."""
    from modules.items import get_item_bag, get_item_by_name

    return sum(
        get_item_bag().quantity_of(get_item_by_name(name))
        for name in ("Poké Ball", "Great Ball", "Ultra Ball", "Net Ball", "Nest Ball", "Repeat Ball", "Timer Ball")
    )


def _pick_reachable_center():
    """The fewest-warps *reachable* Pokémon Center, GRAPH-ONLY planning.

    Never fall back to the live search here: an unreachable candidate answers
    None in milliseconds via the graph, but burns MINUTES of uncached failed
    A* in the live fallback (this spun a run at 100% CPU for two hours)."""
    from dexbot.navigation import _plan_via_graph, _walkable
    from modules.map_data import PokemonCenter
    from modules.player import get_player_avatar

    avatar = get_player_avatar()
    position = (avatar.map_group_and_number, avatar.local_coordinates)
    candidates = [
        PokemonCenter.ViridianCity,
        PokemonCenter.PewterCity,
        PokemonCenter.Route4,
        PokemonCenter.CeruleanCity,
        PokemonCenter.VermilionCity,
        PokemonCenter.Route10,
        PokemonCenter.LavenderTown,
        PokemonCenter.CeladonCity,
    ]
    best = None
    for candidate in candidates:
        route = _plan_via_graph(
            position, (candidate.value[0].value, candidate.value[1]), frozenset(), _walkable
        )
        if route is None:
            continue
        if best is None or len(route) < best[1]:
            best = (candidate, len(route))
            if len(route) <= 1:  # already at/adjacent to this center
                break
    if best is None:
        raise SkillError("No reachable Pokémon Center from here")
    return best[0]


def ensure_healthy(minimum_fraction: float = 0.5, center=None) -> Generator:
    """Heal at a Pokémon Center if the lead is below `minimum_fraction` HP.

    :param center: a modules.map_data.PokemonCenter member; defaults to Viridian.
    """
    # ponytail: caller picks the center — switch to find_closest_pokemon_center
    # when catching spreads across Kanto.
    from modules.map_data import PokemonCenter
    from modules.modes.util.higher_level_actions import heal_in_pokemon_center
    from modules.pokemon_party import get_party

    from modules.pokemon import StatusCondition

    lead = get_party().first_non_fainted
    if not (
        lead is None
        or lead.current_hp / lead.total_hp < minimum_fraction
        or lead.status_condition != StatusCondition.Healthy
        or get_party()[0].status_condition != StatusCondition.Healthy
    ):
        return

    if center is None:
        center = _pick_reachable_center()

    yield from navigate_to(center.value[0], (center.value[1][0], center.value[1][1] + 1))
    yield from heal_in_pokemon_center(center)


def catch_species(
    species_name: str,
    map_key: tuple[int, int] | None = None,
    tile: tuple[int, int] | None = None,
) -> Generator:
    """Catch one specimen of `species_name` at its best (KB) encounter map.

    :param map_key: Optional explicit map (group, number) — overrides the KB pick,
                    which is reachability-blind (e.g. Pikachu's global best map is
                    the Surf-gated Power Plant). The M6 planner will choose maps
                    with the dependency graph instead.
    :param tile: Optional explicit tile to spin on (overrides the centroid pick —
                 use when the centroid would walk through trainer line-of-sight).
    """
    from modules.map_data import MapFRLG
    from modules.modes._interface import BotModeError
    from modules.modes.util.higher_level_actions import spin

    if _species_is_owned(species_name):
        return

    from modules.items import get_item_bag, get_item_by_name

    if _ball_count() == 0:
        raise SkillError(f"No Poké Balls — cannot catch {species_name}")

    yield from ensure_healthy()

    if map_key is None:
        map_key, _rate = best_encounter_map(species_name)
    if tile is not None:
        candidates = [tile]
    else:
        # Spread sample: the N nearest-centroid tiles can all sit in the same
        # unreachable pocket (Route 24's east grass is water-locked). Keep only
        # graph-plannable ones — a bad candidate otherwise costs a 30s live
        # search before we try the next.
        from modules.player import get_player_avatar

        from dexbot.navigation import _plan_via_graph, _walkable

        tiles = _encounter_tiles(map_key)
        candidates = tiles[:: max(1, len(tiles) // 5)][:5]
        avatar = get_player_avatar()
        pos = (avatar.map_group_and_number, avatar.local_coordinates)
        feasible = [c for c in candidates if _plan_via_graph(pos, (map_key, c), frozenset(), _walkable) is not None]
        candidates = feasible or candidates

    from modules.pokemon import StatusCondition
    from modules.pokemon_party import get_party

    def needs_heal() -> bool:
        starter = get_party()[0]
        return starter.current_hp / starter.total_hp < 0.3 or starter.status_condition != StatusCondition.Healthy

    while not _species_is_owned(species_name):
        if _ball_count() == 0:
            # Balls ran dry mid-hunt (a stubborn target can eat a whole
            # restock): defer cleanly instead of letting the catch strategy
            # abort to manual mode and churn.
            raise SkillError(f"Out of Poké Balls hunting {species_name}")
        yield from ensure_healthy(minimum_fraction=0.5)
        arrived = False
        for candidate in candidates:
            try:
                yield from navigate_to(map_key, candidate)
                arrived = True
                break
            except (BotModeError, SkillError):
                # SkillError covers plan failures (no route to THIS tile) —
                # the next candidate may sit in a reachable pocket.
                continue
        if not arrived:
            raise SkillError(f"Could not reach an encounter tile on {MapFRLG(map_key).name}")

        # Spin until caught — or break out to heal when the starter is chipped
        # down (fled encounters and catch battles still deal damage over time).
        yield from spin(stop_condition=lambda: _species_is_owned(species_name) or needs_heal())


# (species, explicit map or None, explicit tile or None) — forest tiles chosen
# near the south entrance, away from bug catcher line-of-sight. Pikachu's KB-best
# map is the Power Plant (unreachable pre-Surf), so it gets the forest explicitly.
VIRIDIAN_FOREST = (1, 0)
ACCEPTANCE_TARGETS = [
    ("Rattata", None, None),
    ("Pidgey", None, None),
    ("Caterpie", VIRIDIAN_FOREST, (4, 58)),
    ("Weedle", VIRIDIAN_FOREST, (4, 58)),
    ("Pikachu", VIRIDIAN_FOREST, (4, 58)),
]


def main() -> None:
    from dexbot.emulator import setup_headless_emulator

    if len(sys.argv) > 1:
        targets = [(name, None, None) for name in sys.argv[1:]]
    else:
        targets = ACCEPTANCE_TARGETS

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m4_pokedex.ss1").read_bytes())
    context.emulator.run_single_frame()

    from dexbot.openings import buy_pokeballs

    run_skill(buy_pokeballs(5), "buy_more_pokeballs", timeout_frames=60_000)

    for species, map_key, tile in targets:
        run_skill(
            catch_species(species, map_key, tile),
            f"catch_{species}",
            timeout_frames=400_000,
            on_battle_started=make_catch_decider(species),
        )
        print(f"caught {species}")

    (PROJECT_ROOT / "fixtures" / "m5_five_species.ss1").write_bytes(context.emulator.get_save_state())

    from modules.pokedex import get_pokedex

    print("owned:", [s.name for s in get_pokedex().owned_species])


if __name__ == "__main__":
    main()
