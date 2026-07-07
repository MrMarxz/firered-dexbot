"""M8: PC box management.

The party is a battle roster, not a storage unit: caught fodder in the party
turns unwinnable rotations into stalls. Before trainer gauntlets, everything
except the strongest member gets deposited (they stay owned in the dex).
"""

from typing import Generator

from dexbot.navigation import navigate_to
from dexbot.runner import SkillError


def _find_pc_tile(map_key: tuple[int, int]) -> tuple[int, int]:
    from modules.map import get_map_data

    map_data = get_map_data(map_key, (0, 0))
    for y in range(map_data.map_size[1]):
        for x in range(map_data.map_size[0]):
            if get_map_data(map_key, (x, y)).tile_type == "PC":
                return (x, y)
    raise SkillError(f"No PC tile found on map {map_key}")


def deposit_party_fodder(keep: int = 1) -> Generator:
    """Deposit all but the strongest `keep` party members at the nearest center's PC."""
    from modules.map_data import PokemonCenter
    from modules.modes.util.pc_interaction import PCAction, interact_with_pc
    from modules.modes.util.walking import ensure_facing_direction
    from modules.pokemon_party import get_party

    party = [p for p in get_party() if not p.is_egg]
    if len(party) <= keep:
        return
    keepers = sorted(party, key=lambda p: -p.level)[:keep]
    keeper_data = {bytes(p.data[:4]) for p in keepers}
    to_deposit = [p for p in get_party() if not p.is_egg and bytes(p.data[:4]) not in keeper_data]
    if not to_deposit:
        return

    # One center visit: enter, heal at the nurse, then use the PC — the
    # upstream heal helper exits the building, so we do the trip ourselves.
    from dexbot.catching import _pick_reachable_center
    from modules.context import context
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import wait_for_player_avatar_to_be_standing_still
    from modules.player import get_player_avatar

    center = _pick_reachable_center()
    yield from navigate_to(center.value[0], center.value[1])  # door warp → inside
    interior = get_player_avatar().map_group_and_number

    yield from navigate_to(interior, (7, 4))  # in front of the nurse
    context.emulator.press_button("A")
    yield
    yield from wait_for_yes_no_question("Yes")
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_standing_still("B")

    pc_tile = _find_pc_tile(interior)
    yield from navigate_to(interior, (pc_tile[0], pc_tile[1] + 1))
    yield from ensure_facing_direction("Up")
    # One PC session per deposit: batching stales the party indices upstream
    # captures at action-creation time (the party shrinks after each deposit).
    from modules.state_cache import state_cache

    for pokemon in to_deposit:
        current = [p for p in get_party() if not p.is_egg and bytes(p.data[:4]) == bytes(pokemon.data[:4])]
        if not current:
            continue
        yield from interact_with_pc([PCAction.deposit_pokemon_to_box(current[0])])
    # The party changed shape outside of battle — drop cached reads so battle
    # strategies don't capture stale slot indices.
    state_cache.reset()

    yield from navigate_to(interior, (7, 8))  # exit mat

    if len([p for p in get_party() if not p.is_egg]) > keep:
        raise SkillError("Deposit incomplete — party still has fodder")
