"""Story-progression skills (the brief's progress_story): each clears one
roadblock, is idempotent, and is verified by an event flag.

Run:  .venv/bin/python -m dexbot.story clear_mt_moon <in_fixture> <out_fixture>
"""

import sys
from typing import Generator

from dexbot import PROJECT_ROOT
from dexbot.catching import ensure_healthy
from dexbot.navigation import navigate_to
from dexbot.runner import SkillError, run_skill

MT_MOON_B2F = (1, 3)


def clear_mt_moon() -> Generator:
    """Beat Super Nerd Miguel and take the Helix Fossil, opening the east exit.

    Deterministic fossil choice: Helix (Omanyte) — one fossil per cart, documented
    in KNOWN_LIMITATIONS.
    """
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable

    if get_event_flag("GOT_FOSSIL_FROM_MT_MOON"):
        return

    # The B2F tunnel chains several grunt fights plus Miguel (Grimer/Voltorb/
    # Koffing L12, resists Fighting) with no healing in between — overlevel first.
    from dexbot.planner import grind_levels
    from modules.pokemon_party import get_party

    if max(p.level for p in get_party() if not p.is_egg) < 16:
        yield from grind_levels(16)

    # Stock up on potions for the gauntlet (as affordable).
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.player import get_player

    if get_item_bag().quantity_of(get_item_by_name("Potion")) < 5:
        affordable = get_player().money // 300
        if affordable > 0:
            from dexbot.openings import buy_items

            yield from buy_items([("Potion", min(8, affordable))], MapFRLG.PEWTER_CITY_MART)

    yield from ensure_healthy(minimum_fraction=0.9)

    # Walk up to Miguel (grunt line-of-sight fights on the way are handled by
    # the battle listener via the navigation interruption handler).
    yield from navigate_to(MT_MOON_B2F, (13, 12))
    yield from talk_to_npc(3)  # Super Nerd Miguel — battle starts via listener
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    # Take the Helix Fossil (right one of the pair on the platform).
    from modules.context import context

    yield from navigate_to(MT_MOON_B2F, (14, 8))
    yield from ensure_facing_direction("Up")
    context.emulator.press_button("A")
    yield
    yield from wait_for_yes_no_question("Yes")
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("GOT_FOSSIL_FROM_MT_MOON"):
        raise SkillError("Fossil not obtained — Mt Moon east exit still blocked")


def cross_nugget_bridge() -> Generator:
    """Fight up Nugget Bridge (rival + five trainers + the Rocket recruiter)."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag, get_event_var
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    def rocket_done() -> bool:
        # The Nugget Bridge Rocket sets VAR_MAP_SCENE_ROUTE24=1 on defeat
        # (the HIDE_NUGGET_BRIDGE_ROCKET flag is unrelated).
        return get_event_var("MAP_SCENE_ROUTE24") >= 1

    if rocket_done():
        return

    # The Cerulean rival (Pidgeotto 17/Abra 16/Rattata 15/Bulbasaur 18) ambushes
    # north of town. Caught fodder in the party makes in-battle rotation
    # possible, and the rotation flow can stall unwinnable fights — deposit
    # everything but the champion, then overlevel it (solo XP is faster too).
    from dexbot.boxes import deposit_party_fodder
    from dexbot.planner import grind_levels
    from modules.pokemon_party import get_party

    yield from deposit_party_fodder(keep=1)
    if max(p.level for p in get_party() if not p.is_egg) < 26:
        yield from grind_levels(26)

    # Climb with heal stops (Cerulean's PC is one screen south; beaten trainers
    # stay beaten). Stop one tile SOUTH of the Rocket's trigger row (y=15) so the
    # last heal actually lands before the fight — then full-heal and step in.
    from modules.context import context
    from modules.player import get_player_avatar

    for waypoint in [(11, 31), (11, 24), (11, 18), (11, 16)]:
        yield from ensure_healthy(minimum_fraction=0.6)
        yield from navigate_to(MapFRLG.ROUTE24, waypoint)
    # Full heal right before the Rocket — a chipped lead just faints and loops.
    yield from ensure_healthy(minimum_fraction=2.0)
    yield from navigate_to(MapFRLG.ROUTE24, (11, 16))
    # Step onto the trigger row (y=15) and A-mash: holding Up reaches the tile
    # but only A advances the Rocket's "Halt!" dialogue into his battle, which
    # the battle listener then fights at full HP.
    for _ in range(600):
        if get_player_avatar().local_coordinates[1] > 15:
            context.emulator.hold_button("Up")
        else:
            context.emulator.reset_held_buttons()
            context.emulator.press_button("A")
        yield
        if rocket_done():
            break
    context.emulator.reset_held_buttons()
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not rocket_done():
        raise SkillError("Nugget Bridge Rocket not defeated (VAR_MAP_SCENE_ROUTE24 unset)")


def _face_and_talk(map_enum, coords, facing) -> Generator:
    """Stand at `coords` (same-map A*), face `facing`, press A, mash the dialogue."""
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as nav_same,
        wait_for_player_avatar_to_be_controllable,
    )

    map_key = map_enum.value if hasattr(map_enum, "value") else map_enum
    yield from nav_same(map_key, coords)
    yield from ensure_facing_direction(facing)
    _ctx().emulator.press_button("A")
    yield
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")


_ADJACENT = [((0, 1), "Up"), ((0, -1), "Down"), ((1, 0), "Left"), ((-1, 0), "Right")]


def _approach_tile_for(map_key, target):
    """A walkable tile adjacent to `target` and the direction to face it from there."""
    from modules.map import get_map_data

    for (dx, dy), facing in _ADJACENT:
        tile = (target[0] + dx, target[1] + dy)
        try:
            if not get_map_data(map_key, tile).collision:
                return tile, facing
        except Exception:
            continue
    return None, None


def _talk_to_live_object(map_enum, script_substr, answer=None) -> Generator:
    """Find the live (visible) object whose script contains `script_substr`,
    stand next to it, and talk. If `answer` is given, respond to its Yes/No.

    Uses same-map A* (not the warp planner) to approach — routing a move through
    a door warp would reset the map's TEMP flags (e.g. BILL_IN_TELEPORTER)."""
    from modules.map import get_map_data, get_map_objects
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as nav_same,
        wait_for_player_avatar_to_be_controllable,
    )

    map_key = map_enum.value if hasattr(map_enum, "value") else map_enum
    # Templates carry the script symbol; live ObjectEvents carry local_id +
    # current position. Cross-reference by local_id.
    matching_ids = {
        t.local_id
        for t in get_map_data(map_key, (0, 0)).objects
        if script_substr.lower() in (getattr(t, "script_symbol", "") or "").lower()
    }
    target = None
    for obj in get_map_objects():
        if "isPlayer" in obj.flags:
            continue
        if obj.local_id in matching_ids:
            target = obj.current_coords
            break
    if target is None:
        raise SkillError(f"No live object matching {script_substr!r} in {map_key}")

    tile, facing = _approach_tile_for(map_key, target)
    if tile is None:
        raise SkillError(f"No walkable tile adjacent to object at {target}")
    yield from nav_same(map_key, tile)
    yield from ensure_facing_direction(facing)
    _ctx().emulator.press_button("A")
    yield
    if answer is not None:
        yield from wait_for_yes_no_question(answer)
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")


def visit_bill() -> Generator:
    """Route 25 → Sea Cottage; help Bill (talk→YES, run the teleporter console,
    talk again); receive the SS Ticket.

    Cottage layout (from pret map.json): Bill obj at (7,5) — talk from (7,6)↑;
    the Computer/teleporter console is a sign bg-event at (4,5) — activate from
    (4,6)↑; door drops the player at (6-8,9).
    """
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.tasks_scripts import wait_for_yes_no_question, wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    from modules.player import get_player_avatar

    COTTAGE = (30, 0)

    def in_cottage() -> bool:
        return get_player_avatar().map_group_and_number == COTTAGE

    def ensure_in_cottage() -> Generator:
        # Re-entrant: a poison/faint whiteout during the Route 25 gauntlet ejects
        # the player to a Pokémon Center (and heals + cures status). Warp-navigate
        # back in each time. Trainers stay beaten, so re-entry gets progressively
        # cleaner until an uninterrupted in-cottage stint completes the handshake.
        if not in_cottage():
            yield from navigate_to(MapFRLG.ROUTE25_SEA_COTTAGE, (7, 7))

    if get_event_flag("GOT_SS_TICKET"):
        return

    # Enter the cottage at FULL HP (poison cured): a full-HP Wartortle survives
    # one Route 25 crossing, so poison can't faint it during the battle-free
    # interior handshake. Heal at Cerulean explicitly — the multi-center
    # "nearest reachable" search is too slow from here (see KNOWN_LIMITATIONS).
    from modules.map_data import PokemonCenter

    yield from ensure_healthy(minimum_fraction=2.0, center=PokemonCenter.CeruleanCity)

    if not get_event_flag("HELPED_BILL_IN_SEA_COTTAGE"):
        # The help→teleporter→console pair must run in ONE in-cottage stint
        # (a whiteout between clears BILL_IN_TELEPORTER). If ejected, retry.
        yield from ensure_in_cottage()
        if not in_cottage():
            raise SkillError("Could not reach the Sea Cottage")
        # Talk to the live Bill (Clefairy form) → Yes → he enters the teleporter.
        yield from _talk_to_live_object(MapFRLG.ROUTE25_SEA_COTTAGE, "Bill", answer="Yes")
        if not in_cottage():
            raise SkillError("Whited out mid-handshake; retrying")  # caller re-runs
        # Run the cell separator at the console (sign bg-event at (4,5)).
        yield from _face_and_talk(MapFRLG.ROUTE25_SEA_COTTAGE, (4, 6), "Up")

    if not get_event_flag("HELPED_BILL_IN_SEA_COTTAGE"):
        raise SkillError("Cell separator did not run (Bill not restored)")

    # Talk to restored (human) Bill for the SS Ticket.
    yield from ensure_in_cottage()
    yield from _talk_to_live_object(MapFRLG.ROUTE25_SEA_COTTAGE, "Bill")

    if not get_event_flag("GOT_SS_TICKET"):
        raise SkillError("SS Ticket not obtained from Bill")

    # After the ticket, Bill launches into "go to the S.S. Anne!". Close it with
    # B (A while facing him re-triggers the talk in a loop) and walk out of the
    # cottage, so the skill ends in a clean, controllable overworld state rather
    # than script-locked next to Bill.
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")
    yield from navigate_to(MapFRLG.ROUTE25, (44, 5))  # step out onto Route 25


def _ctx():
    from modules.context import context

    return context


def get_hm_cut() -> Generator:
    """Board the S.S. Anne (needs SS Ticket), reach the Captain for HM01, and
    teach Cut to the strongest party member (over its weakest move).

    The on-ship rival fight and any trainers en route are handled by the caller's
    Fight battle policy + navigate_to's interruption handling.
    """
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.items import teach_hm_or_tm
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.player import get_player_avatar
    from modules.pokemon_party import get_party

    from dexbot.runner import _log_event

    if not get_event_flag("GOT_HM01"):
        # Full-heal before boarding (the ship chains a rival + trainers with no
        # PC aboard); Vermilion's center is closest to the harbour.
        _log_event(skill="get_hm_cut", status="phase", phase="heal")
        # Heal only if actually hurt — the party is usually full here, and a
        # forced heal treks all the way to Vermilion's PC for nothing.
        yield from ensure_healthy(minimum_fraction=0.6, center=PokemonCenter.VermilionCity)
        # Split the trek into feasible plans: planning a single cross-Kanto +
        # into-ship route is too expensive. Walk to the Vermilion harbour first,
        # step onto the gangplank (ticket-gated board), then navigate the small
        # ship level to the Captain.
        # Stock potions for the ship gauntlet FIRST (no PC aboard; the rival's
        # Grass starter resists our Wartortle's Water). Must happen before the
        # gangplank: arriving at (23,33) triggers the sailor's ticket-check
        # script, and any navigation from there fights that dialogue forever.
        _log_event(skill="get_hm_cut", status="phase", phase="buy_potions")
        if get_item_bag().quantity_of(get_item_by_name("Super Potion")) < 5:
            from dexbot.openings import buy_items
            from modules.player import get_player

            affordable = get_player().money // 700
            if affordable > 0:
                yield from buy_items([("Super Potion", min(8, affordable))], MapFRLG.VERMILION_CITY_MART)
        _log_event(skill="get_hm_cut", status="phase", phase="to_vermilion")
        yield from navigate_to(MapFRLG.VERMILION_CITY, (23, 33))  # just above the gangplank warp
        # Board: arriving on/near the gangplank triggers VermilionCity_
        # EventScript_CheckTicket(Right) (a msgbox that only advances on A —
        # plain walking stalls on it forever). Walk down + mash A until aboard.
        _log_event(skill="get_hm_cut", status="phase", phase="board")
        from modules.context import context as _c

        for _ in range(600):
            if get_player_avatar().map_group_and_number[0] == 1:  # on the ship
                break
            _c.emulator.hold_button("Down")
            if _ % 8 == 0:
                _c.emulator.press_button("A")
            yield
        _c.emulator.reset_held_buttons()
        yield from wait_for_no_script_to_run("A")
        yield from wait_for_player_avatar_to_be_controllable("A")
        if get_player_avatar().map_group_and_number[0] != 1:
            raise SkillError("Failed to board the S.S. Anne")

        _log_event(skill="get_hm_cut", status="phase", phase="ship_to_captain")
        yield from navigate_to(MapFRLG.SSANNE_CAPTAINS_OFFICE, (5, 5))  # through ship to Captain
        _log_event(skill="get_hm_cut", status="phase", phase="talk_captain")
        yield from talk_to_npc(1)  # Captain — seasick dialogue, then hands over HM01
        # Close out with B: pressing A while still facing the Captain re-opens
        # his "the ship will set sail" box in a loop (same trap as Bill's cottage).
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")

    if not get_event_flag("GOT_HM01"):
        raise SkillError("Did not receive HM01 from the S.S. Anne Captain")

    # Teach Cut to the strongest party member that CAN learn it — the Squirtle
    # line cannot in FRLG (verified against the ROM's sTMHMLearnsets), so with
    # a solo-starter party we first withdraw the best boxed learner (Paras).
    if not get_party().has_pokemon_with_move("Cut"):
        hm01 = get_item_by_name("HM01")

        def learners():
            return [p for p in get_party() if not p.is_egg and p.species.can_learn_tm_hm(hm01)]

        if not learners():
            _log_event(skill="get_hm_cut", status="phase", phase="withdraw_learner")
            yield from _withdraw_learner_of(hm01)
        if not learners():
            raise SkillError("No Cut-capable Pokémon in party or PC")
        mon = max(learners(), key=lambda p: p.level)
        party_index = get_party().get_index_for_pokemon(mon)
        replace_index = min(
            range(len(mon.moves)),
            key=lambda i: mon.moves[i].move.base_power if mon.moves[i] else 999,
        )
        _log_event(skill="get_hm_cut", status="phase", phase="teach_cut")
        yield from teach_hm_or_tm(hm01, party_index, replace_index)
        if not get_party().has_pokemon_with_move("Cut"):
            raise SkillError("Failed to teach Cut")


def _withdraw_learner_of(hm_or_tm) -> Generator:
    """Withdraw the highest-level boxed Pokémon that can learn the given HM/TM
    (at the Vermilion center's PC — the party must have a free slot)."""
    from modules.map_data import MapFRLG
    from modules.modes.util.pc_interaction import PCAction, interact_with_pc
    from modules.modes.util.walking import ensure_facing_direction
    from modules.pokemon_storage import get_pokemon_storage

    candidates = [
        slot.pokemon
        for box in get_pokemon_storage().boxes
        for slot in box.slots
        if slot.pokemon.species.can_learn_tm_hm(hm_or_tm)
    ]
    if not candidates:
        raise SkillError(f"No boxed Pokémon can learn {hm_or_tm.name}")
    best = max(candidates, key=lambda p: p.level)
    yield from navigate_to(MapFRLG.VERMILION_CITY_POKEMON_CENTER_1F, (11, 2))  # below the PC
    yield from ensure_facing_direction("Up")
    yield from interact_with_pc([PCAction.withdraw_pokemon_from_box(best)])


def _ctx_placeholder():
    pass


def get_tea() -> Generator:
    """Collect the tea from the old woman in Celadon Condominiums 1F.
    GOT_TEA opens Saffron City's four guard gates — a major routing unlock
    (the nav graph excludes Saffron-entering warps until this flag is set)."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    if get_event_flag("GOT_TEA"):
        return
    # (3,9): beside the tea woman (obj 4 @ 2,9). Her nook is only reachable
    # from the mansion's BACK door region; (2,10) south of her is a counter.
    yield from navigate_to(MapFRLG.CELADON_CITY_CONDOMINIUMS_1F, (3, 9))
    yield from talk_to_npc(4)
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")
    if not get_event_flag("GOT_TEA"):
        raise SkillError("Tea woman did not hand over the tea (GOT_TEA unset)")


def get_vs_seeker() -> Generator:
    """Collect the Vs Seeker (Vermilion Pokémon Center, obj 5) and register it
    to Select. Trainer rematches are the renewable income engine (M8)."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.items import register_key_item
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    seeker = get_item_by_name("VS Seeker")
    if get_item_bag().quantity_of(seeker) == 0:
        yield from navigate_to(MapFRLG.VERMILION_CITY_POKEMON_CENTER_1F, (6, 5))  # below the woman (obj 5 @ 6,4)
        yield from talk_to_npc(5)
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")
        if get_item_bag().quantity_of(seeker) == 0:
            raise SkillError("Vs Seeker woman did not hand it over")
    yield from register_key_item(seeker)


def get_bicycle() -> Generator:
    """Bike Voucher from the Vermilion Fan Club Chairman (obj 1), then swap it
    for a free Bicycle at the Cerulean Bike Shop clerk (obj 1). The Bicycle
    opens the Cycling Road (Route 17/18) — its own trainers for income, dex
    access, and it lifts the bike-gate that was walling navigation to Route 16.
    """
    from modules.context import context
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )

    bicycle = get_item_by_name("Bicycle")
    voucher = get_item_by_name("Bike Voucher")
    if get_item_bag().quantity_of(bicycle) > 0:
        return

    def talk_until(npc_id: int, item, tries: int = 8) -> Generator:
        # Gift/exchange dialogues vary (text-only or a yes/no); mash A through
        # them until the expected item lands, then settle.
        for _ in range(tries):
            if get_item_bag().quantity_of(item) > 0:
                return
            yield from talk_to_npc(npc_id)
            for _ in range(90):
                context.emulator.press_button("A")
                for _ in range(6):
                    yield
            yield from wait_for_no_script_to_run("B")
            yield from wait_for_player_avatar_to_be_controllable("B")

    if get_item_bag().quantity_of(voucher) == 0:
        yield from navigate_to(MapFRLG.VERMILION_CITY_POKEMON_FAN_CLUB, (5, 5))  # below Chairman (obj 1 @ 5,4)
        yield from navigate_same_level(MapFRLG.VERMILION_CITY_POKEMON_FAN_CLUB, (5, 5))
        yield from talk_until(1, voucher)
        if get_item_bag().quantity_of(voucher) == 0:
            raise SkillError("Fan Club Chairman did not give the Bike Voucher")

    yield from navigate_to(MapFRLG.CERULEAN_CITY_BIKE_SHOP, (9, 4))  # below the clerk (obj 1 @ 9,3)
    yield from navigate_same_level(MapFRLG.CERULEAN_CITY_BIKE_SHOP, (9, 4))
    yield from talk_until(1, bicycle)
    if get_item_bag().quantity_of(bicycle) == 0:
        raise SkillError("Bike Shop clerk did not hand over the Bicycle")


def get_amulet_coin() -> Generator:
    """Collect the Amulet Coin from Oak's aide (Route 16 North gate 2F, obj 3).
    Available once the dex has ≥40 owned; it DOUBLES a battle's prize money when
    the holder participates — the biggest single income multiplier available,
    and it works with one-shot first-time trainer fights (no Vs Seeker needed).
    Give it to the battle lead afterward so gym/patrol payouts double."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.pokedex import get_pokedex

    coin = get_item_by_name("Amulet Coin")
    if get_item_bag().quantity_of(coin) > 0:
        return
    if len(get_pokedex().owned_species) < 40:
        raise SkillError("Amulet Coin needs 40+ owned species")

    yield from navigate_to(MapFRLG.ROUTE16_NORTH_ENTRANCE_2F, (10, 7))  # below the aide (obj 3 @ 10,6)
    yield from navigate_same_level(MapFRLG.ROUTE16_NORTH_ENTRANCE_2F, (10, 7))
    yield from talk_to_npc(3)
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")
    if get_item_bag().quantity_of(coin) == 0:
        raise SkillError("Aide did not hand over the Amulet Coin")


def _descend_hidden_stairs() -> Generator:
    """Game Corner (11,2) → the opened hidden stairs at (15,2). The stairs are
    a metatile swap so cached collision blocks pathing — walk right blind
    (bounded, position-checked) until the map flips to Rocket Hideout B1F."""
    from modules.context import context
    from modules.map_data import MapFRLG
    from modules.modes.util.walking import navigate_to as navigate_same_level
    from modules.player import get_player_avatar

    yield from navigate_same_level(MapFRLG.CELADON_CITY_GAME_CORNER, (11, 2))
    for _ in range(8):
        avatar = get_player_avatar()
        if avatar.map_group_and_number == MapFRLG.ROCKET_HIDEOUT_B1F.value:
            return
        before = avatar.local_coordinates
        context.emulator.reset_held_buttons()
        context.emulator.hold_button("Right")
        for _ in range(24):
            yield
        context.emulator.reset_held_buttons()
        for _ in range(12):
            yield
        if get_player_avatar().local_coordinates == before:
            break
    if get_player_avatar().map_group_and_number != MapFRLG.ROCKET_HIDEOUT_B1F.value:
        raise SkillError("Did not reach Rocket Hideout B1F via the hidden stairs")


def _tap_and_settle(direction: str) -> Generator:
    """Probe-proven step executor for spin/conveyor tiles: hold only until the
    first coord change (longer holds derail slides), then wait out the slide
    until the position is stable."""
    from modules.context import context
    from modules.player import get_player_avatar

    before = tuple(get_player_avatar().local_coordinates)
    context.emulator.reset_held_buttons()
    context.emulator.hold_button(direction)
    for _ in range(40):
        yield
        if tuple(get_player_avatar().local_coordinates) != before:
            break
    context.emulator.reset_held_buttons()
    stable, last = 0, tuple(get_player_avatar().local_coordinates)
    for _ in range(900):
        yield
        cur = tuple(get_player_avatar().local_coordinates)
        stable = stable + 1 if cur == last else 0
        last = cur
        if stable >= 24:
            break


def _walk_route(route) -> Generator:
    """Replay a probe-discovered (step, landing) route. "A+Dir" steps press A
    first (item-ball pickup / talk-fight clearing the tile). Battles that
    interrupt are handled by the battle listener; positions are asserted so
    any divergence fails loudly for dev_resume."""
    from modules.context import context
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable
    from modules.player import get_player_avatar

    for step, expected in route:
        if step.startswith("A+"):
            direction = step[2:]
            yield from ensure_facing_direction(direction)
            context.emulator.press_button("A")
            yield
            yield from wait_for_no_script_to_run("B")
            yield from wait_for_player_avatar_to_be_controllable("B")
            yield from _tap_and_settle(direction)
        else:
            yield from _tap_and_settle(step)
        got = tuple(get_player_avatar().local_coordinates)
        if expected is not None and got != expected:
            raise SkillError(f"Hideout route diverged: pressed {step}, expected {expected}, got {got}")


def _ride_hideout_elevator(floor_presses: tuple[str, ...], target_map) -> Generator:
    """From just inside the elevator car: select a floor and walk out.
    The panel is a bg event at (0,2), faced Up from (0,3); the floor menu
    defaults to the CURRENT floor (list order B1F/B2F/B4F), so callers pass
    the Up/Down presses relative to the boarding floor. Input during the
    prompt's print is swallowed, so the whole interaction retries on a wrong
    landing. Exit is the South Arrow Warp at (2,5) (dynamic destination)."""
    from modules.context import context
    from modules.map_data import MapFRLG
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable
    from modules.player import get_player_avatar

    for _attempt in range(3):
        yield from wait_for_player_avatar_to_be_controllable()
        for step in ("Left", "Left", "Up", "Up"):
            yield from _tap_and_settle(step)
        if tuple(get_player_avatar().local_coordinates) != (0, 3):
            raise SkillError("Could not stand at the lift panel (0,3)")
        yield from ensure_facing_direction("Up")
        context.emulator.press_button("A")
        for _ in range(180):  # let "Which floor?" fully print
            yield
        for press in floor_presses:
            context.emulator.press_button(press)
            for _ in range(12):
                yield
        context.emulator.press_button("A")
        for _ in range(300):  # ride animation (same map throughout)
            yield
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")
        for step in ("Down", "Down", "Right", "Right"):
            yield from _tap_and_settle(step)
        for _ in range(8):
            if get_player_avatar().map_group_and_number != MapFRLG.ROCKET_HIDEOUT_ELEVATOR.value:
                break
            yield from _tap_and_settle("Down")
        arrived = get_player_avatar().map_group_and_number
        if arrived == target_map.value:
            return
        if arrived == MapFRLG.ROCKET_HIDEOUT_ELEVATOR.value:
            raise SkillError("Could not leave the lift car")
        # Wrong floor: walk back into the car (door above the landing) and retry.
        yield from ensure_facing_direction("Up")
        context.emulator.press_button("A")
        yield
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")
        for _ in range(6):
            if get_player_avatar().map_group_and_number == MapFRLG.ROCKET_HIDEOUT_ELEVATOR.value:
                break
            yield from _tap_and_settle("Up")
    raise SkillError(f"Elevator did not deliver us to {target_map}")


def _exit_rocket_hideout() -> Generator:
    """Leave the hideout from the Giovanni pocket (elevator-only territory):
    ride the lift to B1F, defeat Grunt5 (TRAINER_GRUNT_12 — his defeat script
    removes the (20-21,19-21) barrier with an unlock sound), walk the column
    north into B1F's main section, and take the (12,2) stairs to the Game
    Corner. Without this the skill strands the player in a pocket the nav
    graph cannot plan out of (dynamic elevator warps are not graph edges) and
    the planner sees an empty queue."""
    from modules.context import context
    from modules.map_data import MapFRLG
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar

    def drain() -> Generator:
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")

    here = get_player_avatar().map_group_and_number
    if here == MapFRLG.ROCKET_HIDEOUT_B4F.value:
        # Giovanni's room exits blind (the guard barrier is a swapped metatile,
        # cached collision is stale above row 14).
        if tuple(get_player_avatar().local_coordinates) == (19, 5):
            yield from _walk_route([("Left", (18, 5)), ("Left", (17, 5))] + [("Down", (17, y)) for y in range(6, 15)])
        yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B4F, (20, 24))
        yield from ensure_facing_direction("Up")
        context.emulator.press_button("A")  # door may want the Lift Key used
        yield
        yield from drain()
        for _ in range(6):
            if get_player_avatar().map_group_and_number == MapFRLG.ROCKET_HIDEOUT_ELEVATOR.value:
                break
            yield from _tap_and_settle("Up")
        if get_player_avatar().map_group_and_number != MapFRLG.ROCKET_HIDEOUT_ELEVATOR.value:
            raise SkillError("Could not board the lift on B4F")
        yield from _ride_hideout_elevator(("Up", "Up"), MapFRLG.ROCKET_HIDEOUT_B1F)  # B4F is last in the list

    if get_player_avatar().map_group_and_number == MapFRLG.ROCKET_HIDEOUT_B1F.value:
        x, y = get_player_avatar().local_coordinates
        if y >= 19:  # in the lift pocket, below the barrier
            yield from talk_to_npc(5)  # Grunt5 @ (21,27) — defeat removes the barrier
            yield from drain()
            yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B1F, (21, 26))
            # Barrier tiles are freshly swapped open — walk the column blind.
            yield from _walk_route([("Up", (21, y2)) for y2 in range(25, 17, -1)])
        yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B1F, (12, 2))  # stairs → Game Corner
        for _ in range(120):
            if get_player_avatar().map_group_and_number == MapFRLG.CELADON_CITY_GAME_CORNER.value:
                break
            yield
    if get_player_avatar().map_group_and_number != MapFRLG.CELADON_CITY_GAME_CORNER.value:
        raise SkillError("Could not exit the Rocket Hideout")


def clear_rocket_hideout() -> Generator:
    """Celadon Game Corner → Rocket Hideout → Giovanni → the SILPH SCOPE.
    Unlocks Pokémon Tower catches and, downstream, the Poké Flute/Snorlax.

    Layout facts (empirical probe — scripts/probe_maze.py — plus pret map
    scripts): grunt obj 11 guards the poster at (11,1); the hidden stairs open
    at (15,2) (metatile swap — cached collision is stale, so the approach is
    blind). B4F's Lift Key section is stair-reachable. The elevator is boarded
    on B2F: its doors (28-29,16) sit in B2F's south, reached from the (21,2)
    landing through the spin maze — the west corridor is body-blocked by the
    Moon Stone item ball at (2,5) (picking it up opens the way). Car panel is
    a bg event at (0,2), faced Up from (0,3); the floor menu defaults to the
    CURRENT floor, so B4F = Down x1 from B2F. The exit (South Arrow Warp at
    (2,5), dynamic destination) lands B4F (20,23), Giovanni's side. There,
    the scripted barrier (17-18,12-13) opens after defeating BOTH door guards
    (objects 6 and 5 — sight range 0, must talk to fight); walk-up is blind
    because the barrier removal is a metatile swap. Two other gated routes
    exist and are NOT used: B1F's barrier (20-21,19-21) / lift doors, and
    B2F's stairs pocket (23,12). Scope ball appears at (20,5) after the fight."""
    from modules.context import context
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar

    from dexbot.catching import ensure_healthy
    from dexbot.runner import _log_event

    scope = get_item_by_name("Silph Scope")
    hideout_maps = {(1, 42), (1, 43), (1, 44), (1, 45), (1, 46)}
    if get_item_bag().quantity_of(scope) > 0:
        # Done — but a resume may still be stranded inside (the Giovanni
        # pocket is not graph-plannable); walk out before returning.
        if get_player_avatar().map_group_and_number in hideout_maps:
            _log_event(skill="clear_rocket_hideout", status="phase", phase="exit")
            yield from _exit_rocket_hideout()
        return

    def drain(button: str = "B") -> Generator:
        yield from wait_for_no_script_to_run(button)
        yield from wait_for_player_avatar_to_be_controllable(button)

    already_inside = get_player_avatar().map_group_and_number in hideout_maps

    if not already_inside:
        yield from ensure_healthy(minimum_fraction=0.9, center=PokemonCenter.CeladonCity)

    if not already_inside and not get_event_flag("OPENED_ROCKET_HIDEOUT"):
        _log_event(skill="clear_rocket_hideout", status="phase", phase="poster")
        yield from navigate_to(MapFRLG.CELADON_CITY_GAME_CORNER, (11, 3))  # below the grunt (obj 11 @ 11,2)
        if get_event_flag("HIDE_GAME_CORNER_ROCKET") is False:
            yield from talk_to_npc(11)  # fight; he flees and unhides the poster
            yield from drain()
        yield from navigate_same_level(MapFRLG.CELADON_CITY_GAME_CORNER, (11, 2))
        yield from ensure_facing_direction("Up")
        context.emulator.press_button("A")  # the poster switch
        yield
        yield from drain()

    if not already_inside:
        _log_event(skill="clear_rocket_hideout", status="phase", phase="descend")
        # Stairs at (15,2) are a metatile swap — cached collision blocks
        # pathing, so approach blind along row 2 (bounded, position-checked).
        yield from _descend_hidden_stairs()

    def descend_stairs_chain() -> Generator:
        # Cross-map planning inside the hideout is unreliable (spin mazes +
        # script-swapped metatiles blow the route budget), but the stairs
        # chain is fixed: B1F (17,2) → B2F (28,2) → walk row 2 → B2F (21,2) →
        # B3F (18,2) → walk the maze → B3F (15,18) → B4F (11,15). Same-level
        # legs only; stepping on a stair tile warps by itself.
        chain = {
            MapFRLG.ROCKET_HIDEOUT_B1F.value: (MapFRLG.ROCKET_HIDEOUT_B1F, (17, 2)),
            MapFRLG.ROCKET_HIDEOUT_B2F.value: (MapFRLG.ROCKET_HIDEOUT_B2F, (21, 2)),
            MapFRLG.ROCKET_HIDEOUT_B3F.value: (MapFRLG.ROCKET_HIDEOUT_B3F, (15, 18)),
        }
        for _ in range(3):
            here = get_player_avatar().map_group_and_number
            if here == MapFRLG.ROCKET_HIDEOUT_B4F.value:
                return
            if here not in chain:
                raise SkillError(f"Not in the hideout stairs chain (at {here})")
            level, stairs = chain[here]
            yield from navigate_same_level(level, stairs)
            for _ in range(120):
                if get_player_avatar().map_group_and_number != here:
                    break
                yield
        if get_player_avatar().map_group_and_number != MapFRLG.ROCKET_HIDEOUT_B4F.value:
            raise SkillError("Hideout stairs chain did not reach B4F")

    if get_item_bag().quantity_of(get_item_by_name("Lift Key")) == 0:
        _log_event(skill="clear_rocket_hideout", status="phase", phase="lift_key")
        yield from descend_stairs_chain()
        yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B4F, (3, 3))  # Grunt1/Lift Key corner
        yield from talk_to_npc(3)  # Grunt1 — fight; drops the Lift Key story
        yield from drain()
        # The key is an item ball right there (obj 4 @ 3,2) in some states —
        # grab it if present.
        yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B4F, (3, 3))
        yield from ensure_facing_direction("Up")
        context.emulator.press_button("A")
        yield
        yield from drain()
        if get_item_bag().quantity_of(get_item_by_name("Lift Key")) == 0:
            raise SkillError("Lift Key not obtained on B4F")

    _log_event(skill="clear_rocket_hideout", status="phase", phase="ride_lift")

    tap_and_settle, walk_route = _tap_and_settle, _walk_route  # shared with _exit_rocket_hideout

    # Reach B2F's north landing (21,2). Normal flow arrives from the Lift Key
    # corner on B4F; resumes may be on any hideout floor — same-level stair
    # legs only (cross-map planning in here blows the route budget).
    if get_player_avatar().map_group_and_number == MapFRLG.ROCKET_HIDEOUT_B4F.value:
        yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B4F, (11, 15))  # stairs → B3F (15,18)
        for _ in range(90):
            yield
    if get_player_avatar().map_group_and_number == MapFRLG.ROCKET_HIDEOUT_B3F.value:
        yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B3F, (18, 2))  # stairs → B2F (21,2)
        for _ in range(90):
            yield
    if get_player_avatar().map_group_and_number == MapFRLG.ROCKET_HIDEOUT_B1F.value:
        yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B1F, (17, 2))  # stairs → B2F (28,2)
        for _ in range(90):
            yield
    if get_player_avatar().map_group_and_number != MapFRLG.ROCKET_HIDEOUT_B2F.value:
        yield from navigate_to(MapFRLG.ROCKET_HIDEOUT_B2F, (21, 2))
    if tuple(get_player_avatar().local_coordinates) != (21, 2):
        yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B2F, (21, 2))

    # B2F (21,2) → elevator door front (28,17), through the spin maze.
    # Discovered by scripts/probe_maze.py (savestate BFS, ground truth);
    # single presses with settle — slides land exactly on these waypoints.
    yield from walk_route(
        [("Down", (21, 3)), ("Down", (21, 4)), ("Down", (21, 5)), ("Left", (20, 5)),
         ("Left", (19, 5)), ("Down", (19, 6)), ("Left", (18, 6)), ("Left", (17, 6)),
         ("Left", (1, 4)), ("Right", (2, 4)),
         ("A+Down", (2, 5)),  # Moon Stone item ball — pick up, then step in
         ("Down", (2, 6)), ("Down", (2, 7)), ("Down", (2, 8)), ("Right", (3, 8)),
         ("Down", (3, 9)), ("Right", (8, 11)), ("Right", (9, 11)), ("Right", (14, 13)),
         ("Left", (13, 13)), ("Left", (10, 15)), ("Right", (11, 15)), ("Right", (12, 15)),
         ("Right", (13, 15)), ("Down", (13, 16)), ("Down", (13, 17)), ("Left", (8, 19)),
         ("Right", (9, 19)), ("Down", (13, 20)), ("Right", (14, 20)), ("Right", (15, 20)),
         ("Up", (15, 19)), ("Up", (15, 18)), ("Up", (15, 17)), ("Right", (16, 17)),
         ("Right", (17, 17)), ("Right", (18, 17)), ("Right", (19, 17)), ("Right", (20, 17)),
         ("Right", (21, 17)), ("Right", (22, 17)), ("Right", (23, 17)), ("Right", (24, 17)),
         ("Right", (25, 17)), ("Right", (26, 17)), ("Right", (27, 17)), ("Right", (28, 17))]
    )

    # Unlock the door with the Lift Key (A while facing it), walk in.
    yield from ensure_facing_direction("Up")
    context.emulator.press_button("A")
    yield
    yield from drain()
    for _ in range(6):
        if get_player_avatar().map_group_and_number == MapFRLG.ROCKET_HIDEOUT_ELEVATOR.value:
            break
        yield from tap_and_settle("Up")
    if get_player_avatar().map_group_and_number != MapFRLG.ROCKET_HIDEOUT_ELEVATOR.value:
        raise SkillError("Could not enter the lift (door still locked?)")

    # Ride to B4F: the floor menu defaults to the boarding floor (B2F), so one
    # Down selects B4F (retries inside on a wrong landing).
    yield from _ride_hideout_elevator(("Down",), MapFRLG.ROCKET_HIDEOUT_B4F)

    _log_event(skill="clear_rocket_hideout", status="phase", phase="giovanni")
    # The barrier at (17-18,12-13) opens after BOTH door guards fall (they
    # never ambush — sight 0 — so talk to each). Objects: 6 @ (16,14), 5 @ (19,14).
    for guard in (6, 5):
        yield from talk_to_npc(guard)
        yield from drain()
    # Barrier removal is a metatile swap (cached collision is stale) — walk up
    # blind through it to Giovanni's room.
    yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B4F, (17, 14))
    yield from walk_route([("Up", (17, y)) for y in range(13, 4, -1)] + [("Right", (18, 5)), ("Right", (19, 5))])
    yield from talk_to_npc(1)  # Giovanni (obj 1 @ 19,4)
    yield from drain()
    # The Silph Scope item ball appears beside his desk (obj 2 @ 20,5),
    # directly east of the talk spot (19,5) — row 6 below is wall.
    yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B4F, (19, 5))
    yield from ensure_facing_direction("Right")
    context.emulator.press_button("A")
    yield
    yield from drain()
    if get_item_bag().quantity_of(scope) == 0:
        raise SkillError("Silph Scope not obtained after Giovanni")

    _log_event(skill="clear_rocket_hideout", status="phase", phase="exit")
    yield from _exit_rocket_hideout()


def catch_snorlax() -> Generator:
    """Wake the Route 12 Snorlax with the Poké Flute and CATCH it (one per
    spot; Route 16 holds the only backup — run this with a catch-capable
    battle handler, never plain fight_all_battles). Snorlax obj 5 @ (14,70)
    blocks the road south of Lavender; facing it and pressing A offers the
    flute prompt, YES starts the battle. Catching (or beating) it clears the
    road — the southbound Koga corridor and Routes 12/13 open either way."""
    from modules.context import context
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        ensure_facing_direction,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.pokedex import get_pokedex

    from dexbot.catching import ensure_healthy
    from dexbot.runner import _log_event

    if "Snorlax" in {s.name for s in get_pokedex().owned_species}:
        return
    if get_item_bag().quantity_of(get_item_by_name("Poké Flute")) == 0:
        raise SkillError("No Poké Flute — run rescue_mr_fuji first")

    _log_event(skill="catch_snorlax", status="phase", phase="approach")
    yield from ensure_healthy(minimum_fraction=0.9, center=PokemonCenter.LavenderTown)
    yield from navigate_to(MapFRLG.ROUTE12, (14, 69))  # directly north of Snorlax

    _log_event(skill="catch_snorlax", status="phase", phase="wake")
    yield from ensure_facing_direction("Down")
    context.emulator.press_button("A")
    yield
    # "...would you like to play the POKE FLUTE?" → YES, then the battle
    # starts; the run's battle handler (a catch decider) takes it from there.
    for _ in range(120):
        yield
    context.emulator.press_button("A")
    yield
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("B")
    if "Snorlax" not in {s.name for s in get_pokedex().owned_species}:
        raise SkillError("Snorlax not caught (fled or fainted?) — Route 16 holds the backup")


def rescue_mr_fuji() -> Generator:
    """Pokémon Tower (Scope in hand) → ghost Marowak → 7F grunts → Mr. Fuji →
    the POKE FLUTE at the Volunteer Pokémon House. Unblocks Snorlax (Routes
    12/16) and the southbound Koga corridor.

    Layout facts (ROM warps + pret scripts): up-stairs per floor — 1F (18,9),
    2F (4,10), 3F (18,10), 4F (4,10), 5F (18,10), 6F (11,16). The 2F rival
    (coord events (17,5)/(16,6)) and the 6F ghost Marowak ((11,15)/(12,16),
    must be DEFEATED, cannot be caught) fire mid-walk — the battle listener
    fights them; if a script interrupt aborts the walk, the skill is
    flag-idempotent and the story runner's retry re-enters past them. 7F's
    three grunts (sight 4) ambush on the approach to Fuji (obj 1 @ (11,4));
    his dialogue warps us to the Volunteer House (4,7) — pret: sets
    RESCUED_MR_FUJI, unhides house-Fuji (obj 1 @ (3,3)), who gives the flute."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar

    from dexbot.catching import ensure_healthy
    from dexbot.runner import _log_event

    flute = get_item_by_name("Poké Flute")
    if get_item_bag().quantity_of(flute) > 0:
        return

    def drain(button: str = "B") -> Generator:
        yield from wait_for_no_script_to_run(button)
        yield from wait_for_player_avatar_to_be_controllable(button)

    house = MapFRLG.LAVENDER_TOWN_VOLUNTEER_POKEMON_HOUSE

    if not get_event_flag("RESCUED_MR_FUJI"):
        _log_event(skill="rescue_mr_fuji", status="phase", phase="climb")
        floors = [
            (MapFRLG.POKEMON_TOWER_1F, (18, 9)),
            (MapFRLG.POKEMON_TOWER_2F, (4, 10)),
            (MapFRLG.POKEMON_TOWER_3F, (18, 10)),
            (MapFRLG.POKEMON_TOWER_4F, (4, 10)),
            (MapFRLG.POKEMON_TOWER_5F, (18, 10)),
            (MapFRLG.POKEMON_TOWER_6F, (11, 16)),
        ]
        tower_maps = {f.value for f, _ in floors} | {MapFRLG.POKEMON_TOWER_7F.value}
        if get_player_avatar().map_group_and_number not in tower_maps:
            yield from ensure_healthy(minimum_fraction=0.9, center=PokemonCenter.LavenderTown)
            yield from navigate_to(MapFRLG.POKEMON_TOWER_1F, (11, 17))  # just inside the entrance
        from modules.modes import BotModeError

        for floor, stairs in floors:
            if get_player_avatar().map_group_and_number != floor.value:
                continue  # resumes start above the lower floors
            yield from drain()
            for _ in range(4):
                try:
                    yield from navigate_same_level(floor, stairs)
                    break
                except BotModeError:
                    # A coord-event trigger (2F rival, 6F Marowak) aborted the
                    # walk. Advance its dialogue into the battle — the battle
                    # listener fights it — then re-walk; defeated triggers
                    # don't re-fire.
                    yield from drain("A")
            for _ in range(180):  # stair warp under our feet
                if get_player_avatar().map_group_and_number != floor.value:
                    break
                yield
            yield from drain()
        if get_player_avatar().map_group_and_number != MapFRLG.POKEMON_TOWER_7F.value:
            raise SkillError("Did not reach Pokémon Tower 7F")

        _log_event(skill="rescue_mr_fuji", status="phase", phase="fuji")
        yield from navigate_same_level(MapFRLG.POKEMON_TOWER_7F, (11, 5))  # grunts ambush en route
        yield from drain()
        yield from talk_to_npc(1)  # Mr. Fuji — his script warps us to the house
        yield from drain()
        for _ in range(300):
            if get_player_avatar().map_group_and_number == house.value:
                break
            yield
        yield from drain()

    _log_event(skill="rescue_mr_fuji", status="phase", phase="flute")
    if get_player_avatar().map_group_and_number != house.value:
        yield from navigate_to(house, (4, 6))
    yield from talk_to_npc(1)  # Fuji @ (3,3) hands over the POKE FLUTE
    yield from drain()
    if get_item_bag().quantity_of(flute) == 0:
        raise SkillError("Poké Flute not obtained from Mr. Fuji")


STORY_SKILLS = {
    "clear_mt_moon": clear_mt_moon,
    "cross_nugget_bridge": cross_nugget_bridge,
    "visit_bill": visit_bill,
    "get_hm_cut": get_hm_cut,
    "get_tea": get_tea,
    "get_vs_seeker": get_vs_seeker,
    "get_bicycle": get_bicycle,
    "get_amulet_coin": get_amulet_coin,
    "clear_rocket_hideout": clear_rocket_hideout,
    "rescue_mr_fuji": rescue_mr_fuji,
    "catch_snorlax": catch_snorlax,
}


def main() -> None:
    from dexbot.catching import fight_all_battles
    from dexbot.emulator import setup_headless_emulator

    which = sys.argv[1]
    fixture = sys.argv[2] if len(sys.argv) > 2 else "m7_badge_brock.ss1"
    out = sys.argv[3] if len(sys.argv) > 3 else f"m7_{which}.ss1"

    if fixture == "--live":
        # Run against the persistent living-dex profile (same resume behavior
        # as run.py): story progress lands in current_state.ss1 for real.
        from dexbot.emulator import get_or_create_profile

        context = setup_headless_emulator(profile=get_or_create_profile("livingdex"), is_test_run=False)
        out = None
    else:
        context = setup_headless_emulator(is_test_run=True)
        context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / fixture).read_bytes())
    context.emulator.run_single_frame()

    from dexbot.runner import attach_video_window

    attach_video_window(context, "dexbot story")

    from dexbot.catching import make_catch_decider

    # catch_* story skills (Snorlax, later legendaries) must CATCH their
    # battle, not KO it.
    handler = (
        make_catch_decider(which.removeprefix("catch_").capitalize())
        if which.startswith("catch_")
        else fight_all_battles
    )

    attempts = 0
    while True:
        attempts += 1
        try:
            run_skill(STORY_SKILLS[which](), which, timeout_frames=900_000, on_battle_started=handler)
            break
        except Exception as e:  # noqa: BLE001 — bounded retries; last error re-raised
            if attempts >= 8:
                raise
            print(f"attempt {attempts} failed ({type(e).__name__}: {e}); healing, then retrying")
            from dexbot.catching import ensure_healthy

            try:
                # fight_all_battles: the default battle handler tries to CATCH
                # wilds met on the heal trek and flips to Manual with no balls.
                run_skill(
                    ensure_healthy(minimum_fraction=2.0),
                    "retry_heal",
                    timeout_frames=120_000,
                    on_battle_started=fight_all_battles,
                )
            except Exception as heal_error:  # noqa: BLE001
                print(f"retry heal failed ({heal_error}); retrying anyway")
    print(f"{which} done")
    if out is None:
        context.emulator.create_save_state(suffix=which)  # persists to the profile
    else:
        (PROJECT_ROOT / "fixtures" / out).write_bytes(context.emulator.get_save_state())


if __name__ == "__main__":
    main()
