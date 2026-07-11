"""M8 evolution pass: dex entries obtainable by evolving mons we already own.

Stone evolutions first (no grinding: buy the stone, use it, done). Level-up
evolutions ride the existing grind machinery separately. Trade evolutions
(Gengar/Alakazam/Machamp/Golem/...) are out of scope for a single cart —
see KNOWN_LIMITATIONS.md.
"""

from typing import Generator

from dexbot.runner import SkillError, _log_event

# (pre-evolution we own, stone, evolution target). Fire/Water/Thunder/Leaf
# are buyable at Celadon Dept 4F (₽2100); Moon Stones only come from item
# balls (Mt Moon, Rocket Hideout, Mansion...), so those plans run only when
# a Moon Stone is already in the bag.
STONE_PLANS = [
    ("Growlithe", "Fire Stone", "Arcanine"),
    ("Pikachu", "Thunderstone", "Raichu"),
    ("Poliwhirl", "Water Stone", "Poliwrath"),
    ("Gloom", "Leaf Stone", "Vileplume"),
    ("Exeggcute", "Leaf Stone", "Exeggutor"),
    ("Nidorina", "Moon Stone", "Nidoqueen"),
    ("Nidorino", "Moon Stone", "Nidoking"),
    ("Clefairy", "Moon Stone", "Clefable"),
    ("Jigglypuff", "Moon Stone", "Wigglytuff"),
]
_BUYABLE_STONES = {"Fire Stone", "Water Stone", "Thunderstone", "Leaf Stone"}
_STONE_PRICE = 2100


def _owned() -> set:
    from modules.pokedex import get_pokedex

    return {s.name for s in get_pokedex().owned_species}


def _apply_item_to_party_mon(item_name: str, party_index: int) -> Generator:
    """Use a bag item (evolution stone) on a party mon and ride out the
    evolution scene. Clone of upstream apply_rare_candy's bag→party→confirm
    flow, minus the candy-specific guards."""
    from modules.battle_evolution_scene import handle_evolution_scene
    from modules.battle_move_replacing import handle_move_replacement_dialogue
    from modules.battle_strategies import DefaultBattleStrategy
    from modules.context import context
    from modules.items import get_item_bag, get_item_by_name
    from modules.memory import GameState, get_game_state, read_symbol
    from modules.menuing import StartMenuNavigator, is_fade_active
    from modules.modes.util.items import scroll_to_item_in_bag
    from modules.tasks import task_is_active

    item = get_item_by_name(item_name)
    if get_item_bag().quantity_of(item) == 0:
        raise SkillError(f"No {item_name} in bag")

    if get_game_state() is not GameState.BAG_MENU:
        yield from StartMenuNavigator("BAG").step()
    yield from scroll_to_item_in_bag(item)
    while get_game_state() != GameState.PARTY_MENU:
        context.emulator.press_button("A")
        yield
    while True:
        current_slot_index = read_symbol("gPartyMenu", offset=9, size=1)[0]
        if current_slot_index < party_index:
            context.emulator.press_button("Down")
            yield
        elif current_slot_index > party_index:
            context.emulator.press_button("Up")
            yield
        else:
            break
    strategy = DefaultBattleStrategy()
    while True:
        if task_is_active("Task_HandleReplaceMoveYesNoInput") or task_is_active("sub_806F390"):
            yield from handle_move_replacement_dialogue(strategy)
        if task_is_active("Task_EvolutionScene"):
            yield from handle_evolution_scene(strategy, allow_evolution=True)
        if get_game_state() in (GameState.BAG_MENU, GameState.OVERWORLD) and not is_fade_active():
            break
        context.emulator.press_button("A")
        yield
    # Back out of whatever menu is left.
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    yield from wait_for_player_avatar_to_be_controllable("B")


def _fetch_to_party(species: str) -> Generator:
    """Ensure a mon of `species` is in the party (withdraw from box, making
    room by depositing a non-essential mon if needed). Yields; leaves the
    player at the PC. Returns nothing — callers re-read the party."""
    from modules.modes.util.pc_interaction import PCAction, interact_with_pc
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_standing_still
    from modules.player import get_player_avatar
    from modules.pokemon_party import get_party
    from modules.state_cache import state_cache

    from dexbot.boxes import _find_pc_tile
    from dexbot.catching import _pick_reachable_center
    from dexbot.navigation import enter_center, navigate_to
    from dexbot.team import _find_box_mon, enumerate_roster

    if any(p.species.name == species and not p.is_egg for p in get_party()):
        return

    roster = [m for m in enumerate_roster() if m.species_name == species and m.location.startswith("box")]
    if not roster:
        raise SkillError(f"No boxed {species} to withdraw")

    center = _pick_reachable_center()
    yield from enter_center(center)
    interior = get_player_avatar().map_group_and_number
    pc_tile = _find_pc_tile(interior)
    yield from navigate_to(interior, (pc_tile[0], pc_tile[1] + 1))
    yield from wait_for_player_avatar_to_be_standing_still("B")
    yield from ensure_facing_direction("Up")

    if len(get_party()) >= 6:
        # Deposit the last non-egg party mon that isn't itself a pending
        # stone target's pre-evolution (cheap heuristic: keep slot 0).
        fodder = next(p for p in reversed(list(get_party())) if not p.is_egg)
        yield from interact_with_pc([PCAction.deposit_pokemon_to_box(fodder)])
        state_cache.reset()
    boxed = _find_box_mon(roster[0].id_bytes)
    if boxed is None:
        raise SkillError(f"Boxed {species} vanished mid-fetch")
    yield from interact_with_pc([PCAction.withdraw_pokemon_from_box(boxed)])
    state_cache.reset()


def evolve_stones() -> Generator:
    """Run every currently-satisfiable stone plan: buy buyable stones at
    Celadon Dept 4F in one trip, then withdraw each pre-evolution and use
    the stone. Each evolution is one new dex entry."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.player import get_player
    from modules.pokemon_party import get_party

    from dexbot.openings import buy_items

    owned = _owned()
    plans = [
        (pre, stone, target)
        for pre, stone, target in STONE_PLANS
        if target not in owned
        and pre in owned
        and (stone in _BUYABLE_STONES or get_item_bag().quantity_of(get_item_by_name(stone)) > 0)
    ]
    if not plans:
        return

    to_buy: dict[str, int] = {}
    for _pre, stone, _target in plans:
        if stone in _BUYABLE_STONES:
            have = get_item_bag().quantity_of(get_item_by_name(stone))
            need = sum(1 for p in plans if p[1] == stone)
            if need > have:
                to_buy[stone] = need - have
    if to_buy and get_player().money < _STONE_PRICE:
        raise SkillError("No money for evolution stones")
    shopping = list(to_buy.items())  # buy_items clamps quantities by wallet
    if shopping:
        _log_event(skill="evolve_stones", status="phase", phase="shop")
        # The clerk (3,13) stands in a walled pocket behind the counter row
        # (y=12); the buyer stands ABOVE the counter and talks across it.
        yield from buy_items(
            shopping, MapFRLG.CELADON_CITY_DEPARTMENT_STORE_4F, counter=(3, 11), facing="Down"
        )

    for pre, stone, target in plans:
        if get_item_bag().quantity_of(get_item_by_name(stone)) == 0:
            continue  # couldn't afford this one
        _log_event(skill="evolve_stones", status="phase", phase=f"evolve_{target}")
        yield from _fetch_to_party(pre)
        index = next(i for i, p in enumerate(get_party()) if p.species.name == pre and not p.is_egg)
        yield from _apply_item_to_party_mon(stone, index)
        if target not in _owned():
            raise SkillError(f"{pre} did not evolve into {target}")
    _log_event(skill="evolve_stones", status="success")
