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
    """Tiles on the map that can spawn encounters, inner tiles first (nicer to spin on)."""
    from modules.map_path import _get_all_maps_metadata

    path_map = _get_all_maps_metadata()[map_group_and_number]
    tiles = [t.local_coordinates for t in path_map.tiles if t.has_encounters]
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


def fight_all_battles(encounter):
    """on_battle_started policy: fight every battle (grinding, gym runs)."""
    from modules.modes._interface import BattleAction

    return BattleAction.Fight


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

    if center is None:
        center = PokemonCenter.ViridianCity
    lead = get_party().first_non_fainted
    if (
        lead is None
        or lead.current_hp / lead.total_hp < minimum_fraction
        or lead.status_condition != StatusCondition.Healthy
        or get_party()[0].status_condition != StatusCondition.Healthy
    ):
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

    yield from ensure_healthy()

    if map_key is None:
        map_key, _rate = best_encounter_map(species_name)
    candidates = [tile] if tile is not None else _encounter_tiles(map_key)[:5]

    from modules.pokemon import StatusCondition
    from modules.pokemon_party import get_party

    def needs_heal() -> bool:
        starter = get_party()[0]
        return starter.current_hp / starter.total_hp < 0.3 or starter.status_condition != StatusCondition.Healthy

    while not _species_is_owned(species_name):
        yield from ensure_healthy(minimum_fraction=0.5)
        arrived = False
        for candidate in candidates:
            try:
                yield from navigate_to(map_key, candidate)
                arrived = True
                break
            except BotModeError:
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
