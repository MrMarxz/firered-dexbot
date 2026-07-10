"""M5: catch_species — navigate to the best encounter spot and catch the target.

Battle-side logic (ball choice by catch-rate math, status moves) is upstream's
CatchStrategy; non-target encounters are fled from. The party lead is healed at
a Pokémon Center whenever it drops below half HP.

Run acceptance:  .venv/bin/python -m dexbot.catching
"""

import sys
from dataclasses import dataclass
from typing import Generator

from dexbot import PROJECT_ROOT
from dexbot.kb import best_encounter_map
from dexbot.navigation import navigate_to
from dexbot.runner import SkillError, run_skill

# HP fraction at/below which False Swipe would risk over-driving past 1 HP is
# irrelevant (it can't KO), but below this we treat the target as "low enough"
# and stop spending turns chipping.
_ONE_HP_FLOOR = 0.05


@dataclass(frozen=True)
class CatchView:
    """Everything choose_catch_action needs — built from a BattleState by the
    strategy adapter, or by hand in unit tests."""

    active_index: int
    active_knows_false_swipe: bool
    party_weakener_index: int | None  # best benched weakener's party index, or None
    opponent_hp_fraction: float
    opponent_is_statused: bool
    one_turn_catch_chance: float
    safe_chip_move_index: int | None
    status_move_index: int | None
    false_swipe_move_index: int | None
    # Per-species playbook flags (dexbot.playbook.catch_plan) — default to the
    # generic policy for hand-built test views.
    is_ghost: bool = False  # False Swipe / Normal chip can't connect
    sleep_first: bool = False  # boomer: never chip while awake
    status_urgent: bool = False  # teleporter: act on the first turn


def choose_catch_action(v: CatchView) -> tuple[str, int | None]:
    """Pure catch-battle policy. Returns one of:
    ("rotate", party_index) | ("move", move_index) | ("ball", None).

    Precedence: good-enough odds → throw; else rotate to the weakener; else
    Sleep (status) first; else False Swipe to 1 HP; else safe non-KO chip;
    else throw. See the sub-project C spec for the rationale (Gen III catch
    math: HP ×~3 at 1 HP, sleep ×2, Ultra Ball ×2, all multiplicative).
    Playbook overrides: ghosts skip the False Swipe plan entirely; boomers are
    never chipped while awake; teleporters get status-or-ball immediately."""
    if v.one_turn_catch_chance >= 0.5:
        return ("ball", None)
    if v.status_urgent:
        # One free turn before it Teleports: status if we can, else throw.
        if not v.opponent_is_statused and v.status_move_index is not None:
            return ("move", v.status_move_index)
        return ("ball", None)
    can_false_swipe = v.active_knows_false_swipe and not v.is_ghost
    # Rotate to the designated weakener if the active mon isn't it.
    if (
        not can_false_swipe
        and not v.is_ghost
        and v.party_weakener_index is not None
        and v.party_weakener_index != v.active_index
    ):
        return ("rotate", v.party_weakener_index)
    # Sleep (or best status) before anything else — ×2 and it doesn't spend HP.
    if not v.opponent_is_statused and v.status_move_index is not None:
        return ("move", v.status_move_index)
    if v.sleep_first and not v.opponent_is_statused:
        # Boomer still awake and we can't put it to sleep: chipping invites a
        # Selfdestruct — just throw.
        return ("ball", None)
    # False Swipe drives to exactly 1 HP without a KO.
    if can_false_swipe and v.false_swipe_move_index is not None and v.opponent_hp_fraction > _ONE_HP_FLOOR:
        return ("move", v.false_swipe_move_index)
    # No False Swipe: chip with the strongest move that can't KO, while HP high.
    if v.opponent_hp_fraction > 0.5 and v.safe_chip_move_index is not None:
        return ("move", v.safe_chip_move_index)
    return ("ball", None)


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


def _shore_tiles(map_group_and_number: tuple[int, int]) -> list[tuple[tuple[int, int], str]]:
    """(tile, facing) pairs for fishing: standable land tiles whose neighbour
    is SURFABLE (upstream's own fishability test — elevation alone misfired:
    Fuchsia's pond read as land and every cast got 'not the time to use
    that'). Facing points at the water; nearest the map centre first."""
    from modules.map import get_map_data
    from modules.map_path import _get_all_maps_metadata

    path_map = _get_all_maps_metadata()[map_group_and_number]
    width, height = path_map.size
    surfable_cache: dict[tuple[int, int], bool] = {}

    def is_water(c: tuple[int, int]) -> bool:
        # In-bounds only: negative/overflow coords resolve into CONNECTED maps
        # (Route 19's (12,-1) reads as Fuchsia's edge water — surfable but
        # collision-blocked, and every cast at it is refused forever).
        if not (0 <= c[0] < width and 0 <= c[1] < height):
            return False
        if c not in surfable_cache:
            try:
                tile = get_map_data(map_group_and_number, c)
                surfable_cache[c] = bool(tile.is_surfable) and not tile.collision
            except Exception:
                surfable_cache[c] = False
        return surfable_cache[c]

    def is_dry_land(c: tuple[int, int]) -> bool:
        try:
            tile = get_map_data(map_group_and_number, c)
            return not tile.is_surfable and not tile.collision
        except Exception:
            return False

    shore: list[tuple[tuple[int, int], str]] = []
    for t in path_map.tiles:
        c = t.local_coordinates
        if not is_dry_land(c):
            continue  # blocked water at map borders masqueraded as "shore"
        x, y = c
        for neighbour, facing in (((x, y - 1), "Up"), ((x, y + 1), "Down"),
                                  ((x - 1, y), "Left"), ((x + 1, y), "Right")):
            if is_water(neighbour):
                shore.append((c, facing))
                break
    if not shore:
        raise SkillError(f"Map {map_group_and_number} has no shore tiles to fish from")
    cx = sum(t[0][0] for t in shore) / len(shore)
    cy = sum(t[0][1] for t in shore) / len(shore)
    return sorted(shore, key=lambda s: abs(s[0][0] - cx) + abs(s[0][1] - cy))


def _fish_until(rod_name: str, facing: str | None, stop_condition) -> Generator:
    """Cast the rod repeatedly until `stop_condition`. Casts from the BAG
    (the registered-item Select shortcut silently no-ops in this harness —
    same finding as the Vs Seeker); upstream's fish() drives the bite/reel
    stages once Task_Fishing is up. Task-driven waits, not blind frame gaps —
    a fixed gap left the USE menu open forever."""
    from modules.context import context
    from modules.items import get_item_by_name
    from modules.memory import GameState, get_game_state
    from modules.menuing import StartMenuNavigator, scroll_to_item_in_bag
    from modules.modes.util.higher_level_actions import TaskFishing
    from modules.modes.util.walking import ensure_facing_direction
    from modules.player import player_avatar_is_controllable
    from modules.tasks import get_task, task_is_active

    def drive_fishing_task() -> Generator:
        while (task := get_task("Task_Fishing")) is not None:
            stage = task.data[0]
            if stage in (
                TaskFishing.WAIT_FOR_A.value,
                TaskFishing.START_ENCOUNTER.value,
                TaskFishing.END_NO_MON.value,
            ):
                context.emulator.press_button("A")
            elif stage == TaskFishing.NOT_EVEN_NIBBLE.value:
                context.emulator.press_button("B")
            yield

    while not stop_condition():
        if get_game_state() != GameState.OVERWORLD or not player_avatar_is_controllable():
            yield  # battle (listeners drive it) or transition — wait it out
            continue
        if facing is not None:
            yield from ensure_facing_direction(facing)
        yield from StartMenuNavigator("BAG").step()
        yield from scroll_to_item_in_bag(get_item_by_name(rod_name))
        context.emulator.press_button("A")  # open the item context menu
        for _ in range(120):
            yield
            if task_is_active("Task_FieldItemContextMenuHandleInput"):
                break
        context.emulator.press_button("A")  # USE → casts
        for _ in range(300):
            yield
            if get_task("Task_Fishing") is not None:
                break
        else:
            # Cast never started ("can't use here"?) — back out and retry;
            # mash B to close whatever is open.
            for _ in range(120):
                if get_game_state() == GameState.OVERWORLD and player_avatar_is_controllable():
                    break
                if _ % 8 == 0:
                    context.emulator.press_button("B")
                yield
            continue
        yield from drive_fishing_task()
        for _ in range(60):  # battle intro / message settle
            yield


class WeakeningCatchStrategy:
    """CatchStrategy that first chips the target down (never risking a KO) to
    roughly double per-ball catch odds — halves ball spend vs. full-HP throws."""

    def __new__(cls):
        from modules.battle_strategies import BattleStrategyUtil, TurnAction
        from modules.battle_strategies.catch import CatchStrategy

        from dexbot.team import SLEEP_MOVES

        def _knows_false_swipe(battler) -> tuple[bool, int | None]:
            for i, lm in enumerate(battler.moves):
                if lm is not None and lm.pp > 0 and lm.move.name == "False Swipe":
                    return True, i
            return False, None

        class _Strategy(CatchStrategy):
            def decide_turn(self, battle_state):
                opponent = battle_state.opponent.active_battler
                own = battle_state.own_side.active_battler
                util = BattleStrategyUtil(battle_state)

                # Safe non-KO chip: strongest damaging move whose worst-case
                # (max roll + crit) still can't KO the target.
                safe_chip = None
                best_dmg = -1
                for index, learned in enumerate(own.moves):
                    if learned is None or learned.pp == 0 or learned.move.base_power == 0:
                        continue
                    crit_max = util.calculate_move_damage_range(learned.move, own, opponent, True).max
                    dmg = util.calculate_move_damage_range(learned.move, own, opponent).max
                    # dmg > 0: an immune matchup (Normal vs Ghost) is not a
                    # chip — it would be chosen forever and never chip anything.
                    if 0 < dmg and crit_max < opponent.current_hp and dmg > best_dmg:
                        safe_chip, best_dmg = index, dmg

                knows_fs, fs_index = _knows_false_swipe(own)

                # Map the active battler + find the best benched weakener by
                # real party index (rotate_lead takes a party index). Match on
                # personality_value (stable per individual).
                from modules.pokemon_party import get_party

                party = [p for p in get_party()]
                active_index = 0
                for i, p in enumerate(party):
                    if not p.is_egg and p.personality_value == own.personality_value:
                        active_index = i
                        break
                weakener_index = None
                for i, p in enumerate(party):
                    if p.is_egg or p.current_hp == 0 or i == active_index:
                        continue
                    names = {m.move.name for m in p.moves if m is not None}
                    if "False Swipe" in names or (names & SLEEP_MOVES):
                        weakener_index = i
                        break

                ball = self._get_best_poke_ball(battle_state)
                if ball is None:
                    return TurnAction.switch_to_manual()
                odds = util.calculate_catch_success_chance(
                    battle_state, self._get_poke_ball_catch_rate_multiplier(battle_state, ball)
                )

                from modules.pokemon import StatusCondition

                from dexbot.playbook import catch_plan

                plan = catch_plan(opponent.species.name)
                view = CatchView(
                    active_index=active_index,
                    active_knows_false_swipe=knows_fs and fs_index is not None,
                    party_weakener_index=weakener_index,
                    opponent_hp_fraction=opponent.current_hp / opponent.total_hp,
                    opponent_is_statused=opponent.status_permanent != StatusCondition.Healthy,
                    one_turn_catch_chance=odds,
                    safe_chip_move_index=safe_chip,
                    status_move_index=self._get_best_status_changing_move(battle_state),
                    false_swipe_move_index=fs_index,
                    is_ghost=plan.is_ghost,
                    sleep_first=plan.sleep_first,
                    status_urgent=plan.status_urgent,
                )
                kind, arg = choose_catch_action(view)
                if kind == "rotate" and arg is not None and arg != view.active_index:
                    return TurnAction.rotate_lead(arg)
                if kind == "move" and arg is not None:
                    return TurnAction.use_move(arg)
                return super().decide_turn(battle_state)  # throws the best ball

        return _Strategy()


def make_healing_battle_strategy(flee_below: float = 0.5):
    """Universal battle policy for a solo/overleveled champion with thin supplies:

    - low HP + a potion in the bag → drink the STRONGEST one (survival beats
      potion-efficiency; a 20-HP Potion can't out-heal Toxic + Sludge on a big
      mon, which lost us Koga);
    - low HP, no potion, WILD battle → run away (the grind/catch loop heals
      between battles, so this avoids whiteout thrash);
    - low HP, no potion, TRAINER battle → fight on (can't flee) and let a
      faint trigger whiteout recovery rather than a hard "cannot battle" error.
    """
    from modules.battle_strategies import BattleStrategyUtil, DefaultBattleStrategy, TurnAction
    from modules.items import get_item_bag, get_item_by_name

    class HealingBattleStrategy(DefaultBattleStrategy):
        def decide_turn(self, battle_state):
            own = battle_state.own_side.active_battler
            if own is not None and own.current_hp / own.total_hp < flee_below:
                bag = get_item_bag()
                for name in ("Full Restore", "Hyper Potion", "Super Potion", "Potion"):
                    item = get_item_by_name(name)
                    if item is not None and bag.quantity_of(item) > 0:
                        return TurnAction.use_item_on(item, own.party_index)
                if not battle_state.is_trainer_battle:
                    # Escape-aware: a blind run_away() against Arena Trap
                    # (wild Diglett) fails every turn forever — the Diglett
                    # Cave 30k-frame stall. When trapped, fight through.
                    escape = BattleStrategyUtil(battle_state).get_best_escape_method()
                    if escape is not None:
                        return escape
            return super().decide_turn(battle_state)

        def decide_turn_in_safari_zone(self, battle_state):
            # Non-catch context inside the Safari (loot walks, transit):
            # fleeing is free — the Default base has no safari logic and
            # drops to Manual mode.
            from modules.battle_strategies import SafariTurnAction

            return SafariTurnAction.run_away()

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
    starter = get_party()[0]
    if not (
        lead is None
        or lead.current_hp / lead.total_hp < minimum_fraction
        or lead.status_condition != StatusCondition.Healthy
        # Slot 0 fainted counts as heal-worthy: faints rotate the party, and
        # the catch/grind loops' needs_heal() keys on party[0] — a fainted
        # Paras in slot 0 with a healthy Blastoise behind it livelocked
        # navigate→spin→"heal"(no-op) at 400 plans/second for a whole morning.
        or starter.current_hp == 0
        or starter.status_condition != StatusCondition.Healthy
    ):
        return

    if center is None:
        try:
            center = _pick_reachable_center()
        except SkillError:
            # The graph can see no exit. Typical case: standing ON a tile
            # that straddles two components (a respawned cut tree under our
            # feet) whose connecting edge is disabled (fainted Cut mule) —
            # one physical step lands in a component that CAN reach a center.
            # Try each direction, re-picking after every step.
            from dexbot.story import _tap_and_settle

            center = None
            for direction in ("Down", "Left", "Right", "Up"):
                yield from _tap_and_settle(direction)
                try:
                    center = _pick_reachable_center()
                    break
                except SkillError:
                    continue
            if center is None:
                raise SkillError("No reachable Pokémon Center from here (even after stepping off)")

    yield from navigate_to(center.value[0], (center.value[1][0], center.value[1][1] + 1))
    yield from heal_in_pokemon_center(center)


_ROD_METHODS = {"old_rod": "Old Rod", "good_rod": "Good Rod", "super_rod": "Super Rod"}


def catch_species(
    species_name: str,
    map_key: tuple[int, int] | None = None,
    tile: tuple[int, int] | None = None,
    method: str = "spin",
) -> Generator:
    """Catch one specimen of `species_name` at its best (KB) encounter map.

    :param map_key: Optional explicit map (group, number) — overrides the KB pick,
                    which is reachability-blind (e.g. Pikachu's global best map is
                    the Surf-gated Power Plant). The M6 planner will choose maps
                    with the dependency graph instead.
    :param tile: Optional explicit tile to spin on (overrides the centroid pick —
                 use when the centroid would walk through trainer line-of-sight).
    :param method: "spin" (land encounters) or "old_rod"/"good_rod"/"super_rod"
                   (fish from a shore tile facing water).
    """
    from modules.map_data import MapFRLG
    from modules.modes._interface import BotModeError
    from modules.modes.util.higher_level_actions import spin
    from modules.modes.util.walking import ensure_facing_direction

    if _species_is_owned(species_name):
        return

    from modules.items import get_item_bag, get_item_by_name

    if _ball_count() == 0:
        raise SkillError(f"No Poké Balls — cannot catch {species_name}")
    rod_name = _ROD_METHODS.get(method)
    if rod_name is not None and get_item_bag().quantity_of(get_item_by_name(rod_name)) == 0:
        raise SkillError(f"No {rod_name} — cannot fish for {species_name}")

    yield from ensure_healthy()

    if map_key is None:
        map_key, _rate = best_encounter_map(species_name)
    facing_by_tile: dict = {}
    if rod_name is not None:
        shore = _shore_tiles(map_key)
        facing_by_tile = dict(shore)
        candidates = [tile] if tile is not None else [c for c, _f in shore[:: max(1, len(shore) // 5)][:5]]
    elif tile is not None:
        candidates = [tile]
    else:
        # Spread sample: the N nearest-centroid tiles can all sit in the same
        # unreachable pocket (Route 24's east grass is water-locked). Keep only
        # graph-plannable ones — a bad candidate otherwise costs a 30s live
        # search before we try the next.
        tiles = _encounter_tiles(map_key)
        candidates = tiles[:: max(1, len(tiles) // 5)][:5]
    from modules.player import get_player_avatar

    from dexbot.navigation import _plan_via_graph, _walkable

    avatar = get_player_avatar()
    pos = (avatar.map_group_and_number, avatar.local_coordinates)
    feasible = [c for c in candidates if _plan_via_graph(pos, (map_key, c), frozenset(), _walkable) is not None]
    if rod_name is not None and not feasible:
        # Fishable-looking water can be pure decoration (Fuchsia's pond is a
        # fenced zoo pen) — churning plans against it stalls for 30k frames.
        raise SkillError(f"No reachable shore tile on {MapFRLG(map_key).name} to fish for {species_name}")
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
        arrived = None
        for candidate in candidates:
            try:
                yield from navigate_to(map_key, candidate)
                arrived = candidate
                break
            except (BotModeError, SkillError):
                # SkillError covers plan failures (no route to THIS tile) —
                # the next candidate may sit in a reachable pocket.
                continue
        if arrived is None:
            raise SkillError(f"Could not reach an encounter tile on {MapFRLG(map_key).name}")

        stop = lambda: _species_is_owned(species_name) or needs_heal()  # noqa: E731
        if rod_name is not None:
            yield from _fish_until(rod_name, facing_by_tile.get(tuple(arrived)), stop)
        else:
            # Spin until caught — or break out to heal when the starter is
            # chipped down (fled encounters and catch battles chip over time).
            yield from spin(stop_condition=stop)


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
