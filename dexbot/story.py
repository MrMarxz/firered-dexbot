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


def _go_talk(map_enum, npc_id: int) -> Generator:
    """Get onto `map_enum` (into the building) and talk to NPC `npc_id`.

    Delegate the precise approach to talk_to_npc, which picks a REACHABLE
    neighbour via calculate_path — not just a collision-free one. (A
    collision-free tile can still be calc-unreachable: the Fan Club Chairman's
    'up' tile is open but unreachable; only 'left' works. Guessing the tile
    ourselves blew the route budget.) dexbot navigate_to lands us inside the
    building even if its final interior leg errors, so a same-map failure is
    fine as long as we're on the map — talk_to_npc takes it from there."""
    from modules.map import get_map_data
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.player import get_player_avatar

    from dexbot.runner import SkillError, SkillTimeout

    if get_player_avatar().map_group_and_number != map_enum.value:
        # Route INTO the building via an ENTRY tile, not an NPC-neighbour.
        # An NPC-neighbour can be calc-unreachable (the Chairman's open 'up'
        # tile is), and navigate_to to an unreachable dest blows the budget
        # during planning without landing us inside. The tiles one step inside
        # from the door warps ARE always reachable (you land next to them on
        # entry) — target those, then let talk_to_npc do the interior approach.
        md = get_map_data(map_enum, (0, 0))
        warps = {w.local_coordinates for w in md.warps}
        entries = []
        for wx, wy in warps:
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                n = (wx + dx, wy + dy)
                try:
                    if n not in warps and not get_map_data(map_enum, n).collision:
                        entries.append(n)
                except Exception:
                    continue
        for target in entries:
            try:
                yield from navigate_to(map_enum, target)
            except (SkillError, SkillTimeout):
                pass
            if get_player_avatar().map_group_and_number == map_enum.value:
                break
        if get_player_avatar().map_group_and_number != map_enum.value:
            raise SkillError(f"Could not enter {map_enum} to reach obj {npc_id}")

    from modules.modes._interface import BotModeError

    try:
        yield from talk_to_npc(npc_id)
    except BotModeError:
        # Counter clerk (Bike Shop, Dept Store, prize counters): the NPC sits
        # behind 'Counter'-behaviour tiles with no reachable adjacent tile, so
        # talk_to_npc's adjacent search fails. Stand on the customer tile one
        # step beyond a counter and press A across it.
        yield from _talk_over_counter(map_enum, npc_id)


def _talk_over_counter(map_enum, npc_id: int) -> Generator:
    from modules.context import context
    from modules.map import get_map_data
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as navigate_same_level,
    )

    from dexbot.runner import SkillError

    md = get_map_data(map_enum, (0, 0))
    npc = next(o.local_coordinates for o in md.objects if o.local_id == npc_id)
    face_of = {(0, 1): "Down", (0, -1): "Up", (-1, 0): "Left", (1, 0): "Right"}
    for dx, dy in ((0, 1), (0, -1), (-1, 0), (1, 0)):
        counter = (npc[0] + dx, npc[1] + dy)
        customer = (npc[0] + 2 * dx, npc[1] + 2 * dy)
        try:
            if get_map_data(map_enum, counter).tile_type != "Counter":
                continue
            if get_map_data(map_enum, customer).collision:
                continue
        except Exception:
            continue
        yield from navigate_same_level(map_enum, customer)
        yield from ensure_facing_direction(face_of[(-dx, -dy)])  # face back toward the counter/clerk
        context.emulator.press_button("A")
        yield
        return
    raise SkillError(f"No counter-front tile to talk to obj {npc_id} on {map_enum}")


def _talk_until(map_enum, npc_id: int, item, tries: int = 8) -> Generator:
    """Approach NPC `npc_id` and mash A through its dialogue until `item` lands
    in the bag. A-mashing answers YES to gift/exchange yes/no prompts (the
    Amulet Coin aide's '40 caught?' prompt, the Bike Shop trade) — draining
    with B instead answers NO and gets nothing."""
    from modules.context import context
    from modules.items import get_item_bag
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

    for _ in range(tries):
        if get_item_bag().quantity_of(item) > 0:
            return
        yield from _go_talk(map_enum, npc_id)
        for _ in range(90):
            context.emulator.press_button("A")
            for _ in range(6):
                yield
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")


def get_bicycle() -> Generator:
    """Bike Voucher from the Vermilion Fan Club Chairman (obj 1), then swap it
    for a free Bicycle at the Cerulean Bike Shop clerk (obj 1). The Bicycle
    opens the Cycling Road (Route 17/18) — its own trainers for income, dex
    access, and it lifts the bike-gate that was walling navigation to Route 16.
    """
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG

    bicycle = get_item_by_name("Bicycle")
    voucher = get_item_by_name("Bike Voucher")
    if get_item_bag().quantity_of(bicycle) > 0:
        return

    if get_item_bag().quantity_of(voucher) == 0:
        yield from _talk_until(MapFRLG.VERMILION_CITY_POKEMON_FAN_CLUB, 1, voucher)  # Chairman
        if get_item_bag().quantity_of(voucher) == 0:
            raise SkillError("Fan Club Chairman did not give the Bike Voucher")

    yield from _talk_until(MapFRLG.CERULEAN_CITY_BIKE_SHOP, 1, bicycle)  # clerk
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
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.pokedex import get_pokedex

    coin = get_item_by_name("Amulet Coin")
    if get_item_bag().quantity_of(coin) > 0:
        return
    if len(get_pokedex().owned_species) < 40:
        raise SkillError("Amulet Coin needs 40+ owned species")

    # The aide asks a yes/no ('caught 40?') whose cursor DEFAULTS TO NO — blind
    # A-mashing selects NO and gets nothing. Reach the aide, then explicitly
    # move the cursor to YES (wait_for_yes_no_question) to claim the coin.
    yield from _go_talk(MapFRLG.ROUTE16_NORTH_ENTRANCE_2F, 3)  # Oak's aide (obj 3), presses A
    yield from wait_for_yes_no_question("Yes")
    yield from wait_for_no_script_to_run("B")
    if get_item_bag().quantity_of(coin) == 0:
        raise SkillError("Aide did not hand over the Amulet Coin")

    # Follow through immediately: a bagged coin doubles nothing. Give it to the
    # battle lead so every trainer payout from here on is doubled.
    from dexbot.team import give_item_to_party_mon

    yield from give_item_to_party_mon("Amulet Coin", 0)


# Silph Co stair spine (from ROM warp data): up/down stair tile per floor.
_SILPH_FLOORS = {
    (1, 47): 1, (1, 48): 2, (1, 49): 3, (1, 50): 4, (1, 51): 5, (1, 52): 6,
    (1, 53): 7, (1, 54): 8, (1, 55): 9, (1, 56): 10, (1, 57): 11,
}
_SILPH_MAP_OF = {v: k for k, v in _SILPH_FLOORS.items()}
_SILPH_UP_STAIR = {1: (31, 2), 2: (28, 2), 3: (30, 2), 4: (28, 2), 5: (30, 2),
                   6: (14, 2), 7: (27, 2), 8: (16, 2), 9: (18, 2), 10: (6, 2)}
_SILPH_DOWN_STAIR = {2: (30, 2), 3: (28, 2), 4: (30, 2), 5: (28, 2), 6: (26, 2),
                     7: (19, 2), 8: (28, 2), 9: (16, 2), 10: (8, 2), 11: (7, 2)}


def _silph_stairs_to(target_floor: int) -> Generator:
    """Position-agnostic Silph transport: walk the open stairwell spine
    (every floor's stairs sit in its ungated north strip)."""
    from modules.modes.util.walking import navigate_to as navigate_same_level, wait_for_player_avatar_to_be_controllable
    from modules.player import get_player_avatar

    for _ in range(12):
        here = get_player_avatar().map_group_and_number
        floor = _SILPH_FLOORS.get(tuple(here))
        if floor is None:
            raise SkillError(f"_silph_stairs_to: not inside Silph Co ({here})")
        if floor == target_floor:
            return
        stair = _SILPH_UP_STAIR[floor] if floor < target_floor else _SILPH_DOWN_STAIR[floor]
        yield from navigate_same_level(here, stair)  # stepping on it warps
        yield from wait_for_player_avatar_to_be_controllable("B")
    raise SkillError(f"_silph_stairs_to: did not reach floor {target_floor}")


# probe_maze tape (WITH Card Key): Silph 3F stairs landing (28,2) → beside
# the (13,14) pad to 7F. A+Down at (24,9) handles the corridor trainer;
# A+Left at (21,13) unlocks card Door2 (the probe pressed A with the key and
# walked through). Final step onto the pad is the caller's (warp breaks the
# tape's landing assert).
_SILPH_3F_KEY_TO_PAD = [
    ("Down", (28, 3)), ("Down", (28, 4)), ("Down", (28, 5)), ("Down", (28, 6)),
    ("Down", (28, 7)), ("Left", (27, 7)), ("Left", (26, 7)), ("Left", (25, 7)),
    ("Down", (25, 8)), ("Left", (24, 8)), ("A+Down", (24, 9)), ("Down", (24, 10)),
    ("Down", (24, 11)), ("Down", (24, 12)), ("Down", (24, 13)), ("Left", (23, 13)),
    ("Left", (22, 13)), ("A+Left", (21, 13)), ("Left", (20, 13)), ("Left", (19, 13)),
    ("Down", (19, 14)), ("Left", (18, 14)), ("Left", (17, 14)), ("Left", (16, 14)),
    ("Left", (15, 14)), ("Left", (14, 14)),
]


def clear_silph_co() -> Generator:
    """Silph Co: Card Key (5F, key-free via the stairwell), 3F card door →
    warp pad → 7F west pocket (rival fight + GIFT LAPRAS + pad to 11F) →
    Giovanni. Opens the Saffron gym. pret-sourced coordinates; card doors are
    script metatiles the path model can't see, so door crossings are blind
    steps (same trick as the Game Corner hidden stairs)."""
    from modules.context import context
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar
    from modules.pokemon_party import get_party

    from dexbot.items_ground import collect_item_balls
    from dexbot.runner import _log_event

    card_key = get_item_by_name("Card Key")

    def unlock_door(stand: tuple[int, int], facing: str) -> Generator:
        """Face a card door tile and press A — with the Card Key it opens."""
        yield from navigate_same_level(get_player_avatar().map_group_and_number, stand)
        yield from ensure_facing_direction(facing)
        context.emulator.press_button("A")
        yield
        yield from wait_for_no_script_to_run("B")
        yield from wait_for_player_avatar_to_be_controllable("B")
        # Blind-step through: the opened metatile is invisible to cached
        # collision (hidden-stairs precedent).
        for _ in range(3):
            before = get_player_avatar().local_coordinates
            context.emulator.reset_held_buttons()
            context.emulator.hold_button(facing)
            for _ in range(24):
                yield
            context.emulator.reset_held_buttons()
            for _ in range(8):
                yield
            if get_player_avatar().local_coordinates == before:
                break

    def step_on_pad(map_enum, pad: tuple[int, int], dest_map) -> Generator:
        yield from navigate_same_level(map_enum, pad)
        for _ in range(120):  # warp animation
            if get_player_avatar().map_group_and_number == dest_map.value:
                break
            yield
        yield from wait_for_player_avatar_to_be_controllable("B")

    if len([p for p in get_party() if not p.is_egg]) >= 6:
        # Free a slot for the gift Lapras: the catch-kit assembly caps at 5.
        from dexbot.team import TeamObjective, assemble_party

        _log_event(skill="clear_silph_co", status="phase", phase="free_slot")
        yield from assemble_party(TeamObjective(kind="catch", field_moves=("Cut",)))
        if len([p for p in get_party() if not p.is_egg]) >= 6:
            raise SkillError("Could not free a party slot for the gift Lapras")

    def pad_round_trip(back_to_map) -> Generator:
        """Step off the current pad and back on — the classic Silph re-land
        trick that bypasses the grunt walling the 5F key hallway. Retries
        every direction until the warp actually fires (a wandering NPC can
        block the first choice)."""
        for d in ("Up", "Left", "Right", "Down"):
            before = get_player_avatar().local_coordinates
            yield from _tap_and_settle(d)
            if get_player_avatar().local_coordinates == before:
                continue
            yield from _tap_and_settle({"Up": "Down", "Down": "Up", "Left": "Right", "Right": "Left"}[d])
            for _ in range(180):
                if get_player_avatar().map_group_and_number == back_to_map.value:
                    break
                yield
            if get_player_avatar().map_group_and_number == back_to_map.value:
                break
        yield from wait_for_player_avatar_to_be_controllable("B")
        if get_player_avatar().map_group_and_number != back_to_map.value:
            raise SkillError("Silph pad round-trip did not warp back")

    if get_item_bag().quantity_of(card_key) == 0:
        _log_event(skill="clear_silph_co", status="phase", phase="card_key")
        # Stairs to 5F, then the guide-documented pad trick: the west-corridor
        # pad (10,20) → 9F, immediately ride it back — the re-landing puts us
        # past the grunt walling the key hallway; drop to row 21 and walk east
        # to the ball (empirically verified tape).
        yield from navigate_to(MapFRLG.SILPH_CO_1F, (31, 2))  # stair → 2F
        yield from navigate_same_level(MapFRLG.SILPH_CO_2F, (28, 2))  # → 3F
        yield from navigate_same_level(MapFRLG.SILPH_CO_3F, (30, 2))  # → 4F
        yield from navigate_same_level(MapFRLG.SILPH_CO_4F, (28, 2))  # → 5F
        yield from navigate_same_level(MapFRLG.SILPH_CO_5F, (10, 20))  # pad → 9F
        for _ in range(180):
            if get_player_avatar().map_group_and_number == MapFRLG.SILPH_CO_9F.value:
                break
            yield
        yield from wait_for_player_avatar_to_be_controllable("B")
        yield from pad_round_trip(MapFRLG.SILPH_CO_5F)
        yield from _tap_and_settle("Right")
        yield from _tap_and_settle("Right")
        yield from _tap_and_settle("Down")  # row 21, past the grunt
        for _ in range(12):
            yield from _tap_and_settle("Right")
        yield from ensure_facing_direction("Right")
        context.emulator.press_button("A")  # the Card Key ball at (22,21)
        yield
        yield from wait_for_no_script_to_run("B")
        if get_item_bag().quantity_of(card_key) == 0:
            raise SkillError("Card Key not collected on 5F")
        # Exit the sealed pocket the way we came: pad → 9F.
        for _ in range(12):
            yield from _tap_and_settle("Left")
        yield from _tap_and_settle("Up")  # (11,20)
        yield from _tap_and_settle("Left")  # onto the (10,20) pad → 9F
        for _ in range(180):
            if get_player_avatar().map_group_and_number == MapFRLG.SILPH_CO_9F.value:
                break
            yield
        yield from wait_for_player_avatar_to_be_controllable("B")

    # Recovery + transit: re-enter if outside (a whiteout/heal walked us out);
    # if stranded on 9F (the pad landing pocket), ride the pad back to 5F's
    # corridor; then the open stairwell spine to 3F.
    _log_event(skill="clear_silph_co", status="phase", phase="door_3f")
    if tuple(get_player_avatar().map_group_and_number) not in _SILPH_FLOORS:
        yield from navigate_to(MapFRLG.SILPH_CO_1F, (31, 2))  # entry + stair → 2F
        yield from wait_for_player_avatar_to_be_controllable("B")
    if get_player_avatar().map_group_and_number == MapFRLG.SILPH_CO_9F.value:
        if tuple(get_player_avatar().local_coordinates) == (22, 18):
            yield from pad_round_trip(MapFRLG.SILPH_CO_5F)  # standing on the pad
        else:
            yield from navigate_same_level(MapFRLG.SILPH_CO_9F, (22, 18))  # enter pad
            for _ in range(180):
                if get_player_avatar().map_group_and_number == MapFRLG.SILPH_CO_5F.value:
                    break
                yield
            yield from wait_for_player_avatar_to_be_controllable("B")
        yield from navigate_same_level(MapFRLG.SILPH_CO_5F, (9, 4))  # corridor north
    yield from _silph_stairs_to(3)
    yield from navigate_same_level(MapFRLG.SILPH_CO_3F, (28, 2))  # tape start
    yield from _walk_route(_SILPH_3F_KEY_TO_PAD)

    _log_event(skill="clear_silph_co", status="phase", phase="pad_to_7f")
    yield from step_on_pad(MapFRLG.SILPH_CO_3F, (13, 14), MapFRLG.SILPH_CO_7F)

    # 7F west pocket: approaching the Lapras corner triggers the rival fight
    # (script battle — the caller's battle policy takes it), then the gift.
    _log_event(skill="clear_silph_co", status="phase", phase="rival_and_lapras")
    yield from navigate_same_level(MapFRLG.SILPH_CO_7F, (2, 7))
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")
    if not any(p.species.name == "Lapras" for p in get_party() if not p.is_egg):
        yield from _go_talk(MapFRLG.SILPH_CO_7F, _lapras_guy_id())
        yield from wait_for_no_script_to_run("A")
        yield from wait_for_player_avatar_to_be_controllable("B")
    if not any(p.species.name == "Lapras" for p in get_party() if not p.is_egg):
        raise SkillError("Lapras was not received on 7F")

    _log_event(skill="clear_silph_co", status="phase", phase="giovanni")
    yield from step_on_pad(MapFRLG.SILPH_CO_7F, (5, 8), MapFRLG.SILPH_CO_11F)

    def step_toward(direction: str, tries: int = 3) -> Generator:
        """One tile with A-clear retries (grunts/items block the corridor)."""
        for _ in range(tries):
            before = tuple(get_player_avatar().local_coordinates)
            yield from _tap_and_settle(direction)
            if tuple(get_player_avatar().local_coordinates) != before:
                return
            yield from ensure_facing_direction(direction)
            context.emulator.press_button("A")
            yield
            yield from wait_for_no_script_to_run("B")
            yield from wait_for_player_avatar_to_be_controllable("B")

    # North up the corridor to (6,12), just below Giovanni (object 3, no
    # script symbol — a boss-trainer object), A-clearing grunts on the way.
    for _ in range(10):
        if get_player_avatar().local_coordinates[1] <= 12:
            break
        yield from step_toward("Up")
    yield from step_toward("Right")
    yield from ensure_facing_direction("Up")
    context.emulator.press_button("A")  # Giovanni — dialogue → battle
    yield
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")

    # Post-fight scene hides every Rocket in Saffron — THE cleared signal
    # (HIDE_SILPH_CO_11F_GIOVANNI never flips; empirically verified).
    if not get_event_flag("HIDE_SAFFRON_ROCKETS"):
        raise SkillError("Giovanni was not defeated (Silph not cleared)")

    # The grateful President hands over the Master Ball.
    yield from _go_talk(MapFRLG.SILPH_CO_11F, 1)
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")


def _lapras_guy_id() -> int:
    from modules.map import get_map_data
    from modules.map_data import MapFRLG

    for o in get_map_data(MapFRLG.SILPH_CO_7F.value, (0, 0)).objects:
        if "LaprasGuy" in str(getattr(o, "script_symbol", "")):
            return o.local_id
    return 4  # pret order fallback


def get_exp_share() -> Generator:
    """Collect the Exp. Share from Oak's aide (Route 15 gate 2F, needs 50+
    owned). Same yes/no gift pattern as the Amulet Coin aide. Give it to
    whatever mon is being trained at the time — it makes every future
    level-grind (evolution dex entries) roughly twice as fast."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.pokedex import get_pokedex

    share = get_item_by_name("Exp. Share")
    if get_item_bag().quantity_of(share) > 0:
        return
    if len(get_pokedex().owned_species) < 50:
        raise SkillError("Exp. Share needs 50+ owned species")

    yield from _go_talk(MapFRLG.ROUTE15_WEST_ENTRANCE_2F, 1)  # Oak's aide
    yield from wait_for_yes_no_question("Yes")
    yield from wait_for_no_script_to_run("B")
    if get_item_bag().quantity_of(share) == 0:
        raise SkillError("Aide did not hand over the Exp. Share")


def get_hm_strength() -> Generator:
    """Gold Teeth (Safari West item ball at (28,14), plus the area's other
    free loot: TM32 / Max Potion / Max Revive) → the Warden trades them for
    HM04 → teach Strength to the strongest capable party member. Strength
    opens the boulder dungeons (Seafoam Islands, Victory Road)."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.pokemon_party import get_party

    from dexbot.items_ground import collect_item_balls
    from dexbot.runner import _log_event
    from dexbot.safari import enter_safari, retire_safari, walk_safari_path, _inside_safari

    teeth = get_item_by_name("Gold Teeth")
    hm04 = get_item_by_name("HM04")

    if not get_event_flag("GOT_HM04") and get_item_bag().quantity_of(hm04) == 0:
        if get_item_bag().quantity_of(teeth) == 0:
            _log_event(skill="get_hm_strength", status="phase", phase="safari_loot")
            for _attempt in range(3):  # PA timeout mid-walk → re-enter
                if not _inside_safari():
                    yield from enter_safari()
                yield from walk_safari_path(MapFRLG.SAFARI_ZONE_WEST, (27, 15))
                if not _inside_safari():
                    continue
                yield from collect_item_balls(MapFRLG.SAFARI_ZONE_WEST, limit=6)
                break
            if _inside_safari():
                yield from retire_safari()
            if get_item_bag().quantity_of(teeth) == 0:
                raise SkillError("Gold Teeth not collected in Safari West")

        _log_event(skill="get_hm_strength", status="phase", phase="warden")
        yield from _talk_until(MapFRLG.FUCHSIA_CITY_WARDENS_HOUSE, 1, hm04)
        if get_item_bag().quantity_of(hm04) == 0:
            raise SkillError("Warden did not hand over HM04")

    if not get_party().has_pokemon_with_move("Strength"):
        from modules.modes.util.items import teach_hm_or_tm

        learners = [p for p in get_party() if not p.is_egg and p.species.can_learn_tm_hm(hm04)]
        if not learners:
            _log_event(skill="get_hm_strength", status="phase", phase="withdraw_learner")
            yield from _withdraw_learner_of(hm04)
            learners = [p for p in get_party() if not p.is_egg and p.species.can_learn_tm_hm(hm04)]
        if not learners:
            raise SkillError("No Strength-capable Pokémon in party or PC")
        mon = max(learners, key=lambda p: p.level)
        party_index = get_party().get_index_for_pokemon(mon)
        replace_index = min(
            range(len(mon.moves)),
            key=lambda i: mon.moves[i].move.base_power if mon.moves[i] else 999,
        )
        _log_event(skill="get_hm_strength", status="phase", phase="teach_strength")
        yield from teach_hm_or_tm(hm04, party_index, replace_index)
        if not get_party().has_pokemon_with_move("Strength"):
            raise SkillError("Failed to teach Strength")


def get_rods() -> Generator:
    """Collect all three fishing rods (pret-verified givers, each behind a
    'do you like to fish?' YES prompt):
    - Old Rod   — Vermilion City House 1, Fishing Guru.
    - Good Rod  — Fuchsia City House 2, Fishing Guru's brother.
    - Super Rod — Route 12 Fishing House.
    Idempotent: skips rods already in the bag. Rods unlock the fishing dex
    chunk (Magikarp/Horsea/Krabby/Goldeen/Poliwag/Gyarados/Dratini...)."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG

    for rod_name, map_enum in (
        ("Old Rod", MapFRLG.VERMILION_CITY_HOUSE1),
        ("Super Rod", MapFRLG.ROUTE12_FISHING_HOUSE),
        ("Good Rod", MapFRLG.FUCHSIA_CITY_HOUSE2),
    ):
        rod = get_item_by_name(rod_name)
        if get_item_bag().quantity_of(rod) > 0:
            continue
        yield from _talk_until(map_enum, 1, rod)
        if get_item_bag().quantity_of(rod) == 0:
            raise SkillError(f"{rod_name} giver did not hand it over")


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


def _engage_static(map_enum, target: tuple[int, int], skill: str) -> Generator:
    """Stand next to the static overworld Pokémon at `target`, face it, A —
    the run's battle handler (a catch decider) owns the battle. A-mash covers
    any pre-battle prompt (Snorlax's flute question, legendary cries)."""
    from modules.context import context
    from modules.modes._interface import BotModeError
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable

    for (dx, dy), facing in (((0, 1), "Up"), ((0, -1), "Down"), ((1, 0), "Left"), ((-1, 0), "Right")):
        stand = (target[0] + dx, target[1] + dy)
        if stand[0] < 0 or stand[1] < 0:
            continue
        try:
            yield from navigate_to(map_enum, stand)
        except (SkillError, BotModeError):
            continue
        yield from ensure_facing_direction(facing)
        context.emulator.press_button("A")
        yield
        for _ in range(120):
            yield
        context.emulator.press_button("A")
        yield
        yield from wait_for_no_script_to_run("A")
        yield from wait_for_player_avatar_to_be_controllable("B")
        return
    raise SkillError(f"{skill}: no reachable stand tile beside {target}")


def catch_zapdos() -> Generator:
    """Zapdos guards the Power Plant back hall (static, L50, catch rate 3 —
    a fled/fainted legendary is gone forever in FRLG, so the catch decider's
    no-KO discipline matters). Ground-type Marowak is immune to its Electric
    STAB. Stocks Ultra Balls hard and sweeps the Plant's item balls
    (Thunder Stone, TM25) on the way in."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG
    from modules.player import get_player
    from modules.pokedex import get_pokedex

    from dexbot.catching import ensure_healthy
    from dexbot.items_ground import collect_item_balls
    from dexbot.runner import _log_event

    def _owned() -> bool:
        return "Zapdos" in {s.name for s in get_pokedex().owned_species}

    if _owned():
        return
    # The full catch kit or nothing: a skeleton party fed Zapdos 19 Ultra
    # Balls at ~1% odds (no sleeper, no tank). Surf carries the party
    # across Route 10's strip; the sleeper (Spore ×2 odds) is the lever.
    from dexbot.team import TeamObjective, assemble_party

    yield from assemble_party(
        TeamObjective(kind="catch", field_moves=("Surf",), prefer_offense_types=("Electric",))
    )
    # The wall lead is non-negotiable for this fight; the generic selector
    # ranks by level and leaves L34 Magneton boxed.
    from dexbot.evolution import _fetch_to_party

    yield from _fetch_to_party("Magneton")
    ultra = get_item_by_name("Ultra Ball")
    have = get_item_bag().quantity_of(ultra)
    if have < 20:
        n = min(30 - have, get_player().money // 1200)
        if n > 0:
            _log_event(skill="catch_zapdos", status="phase", phase="restock")
            from dexbot.openings import buy_items
            from dexbot.planner import _nearest_mart

            yield from buy_items([("Ultra Ball", n)], _nearest_mart())
    _log_event(skill="catch_zapdos", status="phase", phase="approach")
    yield from ensure_healthy(minimum_fraction=0.95)
    # Best lead vs an Electric/Flying legendary: Magneton walls Drill Peck
    # and Electric STAB at 0.5x, paralyzes (Thunder Wave, catch x1.5) and
    # chips a deterministic 20/turn (Sonicboom never randomly KOs).
    from modules.pokemon_party import get_party
    from dexbot.team import make_lead

    for lead in ("Magneton", "Electabuzz"):
        if any(p.species.name == lead and not p.is_egg and p.current_hp > 0 for p in get_party()):
            yield from make_lead(lead)
            break
    yield from collect_item_balls(MapFRLG.POWER_PLANT, limit=5)  # Thunder Stone, TM25, ...
    _log_event(skill="catch_zapdos", status="phase", phase="engage")
    yield from _engage_static(MapFRLG.POWER_PLANT, (5, 11), "catch_zapdos")
    if not _owned():
        raise SkillError("Zapdos not caught — restore fixtures/_phases/catch_zapdos_engage.ss1 before retrying")


def catch_electrode() -> Generator:
    """The Power Plant's two 'item ball' Electrodes (static battles at
    (30,38) and (36,5), catch rate 60 — easy)."""
    from modules.map_data import MapFRLG
    from modules.pokedex import get_pokedex

    from dexbot.catching import ensure_healthy
    from dexbot.runner import _log_event

    def _owned() -> bool:
        return "Electrode" in {s.name for s in get_pokedex().owned_species}

    if _owned():
        return
    yield from ensure_healthy(minimum_fraction=0.8)
    for target in ((30, 38), (36, 5)):
        _log_event(skill="catch_electrode", status="phase", phase=f"engage_{target[0]}_{target[1]}")
        yield from _engage_static(MapFRLG.POWER_PLANT, target, "catch_electrode")
        if _owned():
            return
    raise SkillError("Electrode not caught (both Plant Electrodes engaged)")


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


# Pokémon Mansion statue switches (bg events, from ROM): pressing A toggles
# the global switch flag; the fork's _FLAG_DOORS table makes A* track the
# resulting door state.
_MANSION_STATUES = {
    (1, 59): [(5, 5)],
    (1, 60): [(2, 16)],
    (1, 61): [(12, 5)],
    (1, 62): [(24, 29), (27, 5)],
}
_MANSION_MAPS = {(1, 59), (1, 60), (1, 61), (1, 62)}


def _mansion_toggle_statue(map_enum, statue) -> Generator:
    from modules.context import context
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import (
        ensure_facing_direction,
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )

    yield from navigate_same_level(map_enum, (statue[0], statue[1] + 1))  # below it
    yield from ensure_facing_direction("Up")
    context.emulator.press_button("A")
    yield
    yield from wait_for_yes_no_question("Yes")  # "A secret switch! Press it?"
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")
    # The toggle flips door passability BOTH ways — cached A* verdicts
    # (positive and negative) are stale now.
    from dexbot.navigation import _walkable_cache, _walkable_neg

    _walkable_cache.clear()
    _walkable_neg.clear()


def leave_mansion() -> Generator:
    """From anywhere inside the Mansion, reach Cinnabar outdoors.
    Headless-verified exit truth: B1F's west/key side only reaches the
    stairs landing with the switch CLEAR, but the 1F drop pocket only
    reaches the BACK door (34,33) with it SET — so B1F exits by toggling
    whatever statue is reachable until the landing opens, taking the
    stairs, ensuring SET, and walking out the back door."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.walking import (
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar

    from dexbot.navigation import _walkable
    from dexbot.runner import _log_event

    def _here():
        av = get_player_avatar()
        return tuple(av.map_group_and_number), tuple(av.local_coordinates)

    def _open_path_to(map_key, tile) -> Generator:
        """Toggle reachable statues (nearest-first is irrelevant — ≤2 per
        floor) until `tile` is walkable; raises if no toggle helps."""
        here, pos = _here()
        if _walkable((here, pos), (here, tile), max_nodes=3_000):
            return
        for statue in _MANSION_STATUES.get(here, []):
            stand = (statue[0], statue[1] + 1)
            if not _walkable((here, pos), (here, stand), max_nodes=3_000):
                continue
            yield from _mansion_toggle_statue(MapFRLG(here), statue)
            here, pos = _here()
            if _walkable((here, pos), (here, tile), max_nodes=3_000):
                return
        raise SkillError(f"leave_mansion: cannot open a path to {tile} on {here}")

    yield from wait_for_player_avatar_to_be_controllable("B")  # drain any open dialog
    for _ in range(10):
        here, pos = _here()
        if here not in _MANSION_MAPS:
            return  # outside
        _log_event(skill="leave_mansion", status="phase", phase=f"floor_{here[1]}")
        if here == MapFRLG.POKEMON_MANSION_B1F.value:
            yield from _open_path_to(here, (34, 29))
            # The 1F pocket upstairs only exits via the back door with the
            # switch SET, and the pocket has no statue — set it before going
            # up. (24,29) is beside the landing and reachable in CLEAR; the
            # landing stays reachable after the flip (verified).
            if not get_event_flag("POKEMON_MANSION_SWITCH_STATE"):
                for statue in _MANSION_STATUES[here]:
                    stand = (statue[0], statue[1] + 1)
                    _, pos = _here()
                    if _walkable((here, pos), (here, stand), max_nodes=3_000):
                        yield from _mansion_toggle_statue(MapFRLG.POKEMON_MANSION_B1F, statue)
                        break
                yield from _open_path_to(here, (34, 29))
            yield from navigate_same_level(MapFRLG.POKEMON_MANSION_B1F, (34, 29))  # stairs up
        elif here == MapFRLG.POKEMON_MANSION_1F.value:
            if _walkable((here, pos), (here, (8, 33)), max_nodes=3_000):
                exit_tile = (8, 33)  # front door
            else:
                yield from _open_path_to(here, (34, 33))  # pocket: back door, needs SET
                exit_tile = (34, 33)
            yield from navigate_same_level(MapFRLG.POKEMON_MANSION_1F, exit_tile)
        elif here == MapFRLG.POKEMON_MANSION_2F.value:
            yield from _open_path_to(here, (6, 14))
            yield from navigate_same_level(MapFRLG.POKEMON_MANSION_2F, (6, 14))  # stairs to 1F
        elif here == MapFRLG.POKEMON_MANSION_3F.value:
            yield from _open_path_to(here, (8, 3))
            yield from navigate_same_level(MapFRLG.POKEMON_MANSION_3F, (8, 3))  # stairs to 2F
        yield from wait_for_player_avatar_to_be_controllable("B")
    raise SkillError("leave_mansion: still inside after 10 legs")


def get_secret_key() -> Generator:
    """Pokémon Mansion → B1F Secret Key (unlocks Cinnabar gym for Blaine).
    Route needs NO switches (probed): 1F stairs (10,13) → 2F (9,3) → 3F
    balcony hole (18,18) drops into the sealed 1F pocket → B1F stairs
    (25,27) → key item ball at (5,7). The switch doors only matter for
    LEAVING the pocket afterwards — live A* sees their current state."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.walking import (
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar

    from dexbot.items_ground import collect_item_balls
    from dexbot.navigation import _walkable
    from dexbot.runner import _log_event

    if get_event_flag("HIDE_POKEMON_MANSION_B1F_SECRET_KEY"):  # item ball taken
        if tuple(get_player_avatar().map_group_and_number) in _MANSION_MAPS:
            yield from leave_mansion()
        return

    def _phase(name: str) -> None:
        _log_event(skill="get_secret_key", status="phase", phase=name)

    statues = _MANSION_STATUES
    _toggle_statue = _mansion_toggle_statue

    def _stair(map_enum, tile) -> Generator:
        here = map_enum.value
        pos = tuple(get_player_avatar().local_coordinates)
        if not _walkable((here, pos), (here, tile), max_nodes=3_000):
            for statue in statues.get(here, []):
                _phase(f"statue_{here[1]}_{statue[0]}_{statue[1]}")
                yield from _toggle_statue(map_enum, statue)
                pos = tuple(get_player_avatar().local_coordinates)
                if _walkable((here, pos), (here, tile), max_nodes=3_000):
                    break
        yield from navigate_same_level(map_enum, tile)  # stepping on it warps
        yield from wait_for_player_avatar_to_be_controllable("B")

    mansion = {
        MapFRLG.POKEMON_MANSION_1F.value,
        MapFRLG.POKEMON_MANSION_2F.value,
        MapFRLG.POKEMON_MANSION_3F.value,
        MapFRLG.POKEMON_MANSION_B1F.value,
    }
    if tuple(get_player_avatar().map_group_and_number) not in mansion:
        _phase("trek")
        yield from navigate_to(MapFRLG.POKEMON_MANSION_1F, (8, 31))

    for _ in range(8):
        here = tuple(get_player_avatar().map_group_and_number)
        pos = tuple(get_player_avatar().local_coordinates)
        if here == MapFRLG.POKEMON_MANSION_B1F.value:
            break
        if here == MapFRLG.POKEMON_MANSION_1F.value:
            if _walkable((here, pos), (here, (25, 27)), max_nodes=3_000):  # in the drop pocket
                _phase("b1f_stairs")
                yield from _stair(MapFRLG.POKEMON_MANSION_1F, (25, 27))
            else:
                _phase("to_2f")
                yield from _stair(MapFRLG.POKEMON_MANSION_1F, (10, 13))
        elif here == MapFRLG.POKEMON_MANSION_2F.value:
            _phase("to_3f")
            yield from _stair(MapFRLG.POKEMON_MANSION_2F, (9, 3))
        elif here == MapFRLG.POKEMON_MANSION_3F.value:
            _phase("drop")
            yield from _stair(MapFRLG.POKEMON_MANSION_3F, (18, 18))  # balcony hole
    else:
        raise SkillError("get_secret_key: never reached Mansion B1F")

    # B1F choreography (headless-verified): land at (34,29) with the switch
    # SET (the 3F hole needed it) — the landing pocket is sealed in that
    # state. Toggle (24,29) → CLEAR opens the corridor west; from (27,6)
    # toggle (27,5) → SET opens the key room. Only THEN is the ball
    # collectible; running collect_item_balls earlier grinds through failed
    # plans until the standstill watchdog kills the skill.
    _phase("key")
    b1f = MapFRLG.POKEMON_MANSION_B1F
    key_stands = ((5, 8), (4, 7), (5, 6), (6, 7))

    def _key_reachable() -> bool:
        pos = tuple(get_player_avatar().local_coordinates)
        return any(_walkable((b1f.value, pos), (b1f.value, s), max_nodes=3_000) for s in key_stands)

    for statue in [None, *statues[b1f.value]]:
        if statue is not None:
            _phase(f"statue_b1f_{statue[0]}_{statue[1]}")
            yield from _toggle_statue(b1f, statue)
        if _key_reachable():
            break
    else:
        raise SkillError("Secret Key room never opened (B1F statue sequence failed)")
    yield from collect_item_balls(b1f, only=[(5, 7)])  # the key, nothing else
    if not get_event_flag("HIDE_POKEMON_MANSION_B1F_SECRET_KEY"):
        raise SkillError("Secret Key ball not collected despite open room")
    yield from collect_item_balls(b1f, limit=4)  # best-effort: whatever loot is open
    _phase("leave")
    yield from leave_mansion()


STORY_SKILLS = {
    "clear_mt_moon": clear_mt_moon,
    "cross_nugget_bridge": cross_nugget_bridge,
    "visit_bill": visit_bill,
    "get_hm_cut": get_hm_cut,
    "get_tea": get_tea,
    "get_vs_seeker": get_vs_seeker,
    "get_bicycle": get_bicycle,
    "get_amulet_coin": get_amulet_coin,
    "get_rods": get_rods,
    "get_exp_share": get_exp_share,
    "get_hm_strength": get_hm_strength,
    "clear_silph_co": clear_silph_co,
    "get_secret_key": get_secret_key,
    "leave_mansion": leave_mansion,
    "clear_rocket_hideout": clear_rocket_hideout,
    "rescue_mr_fuji": rescue_mr_fuji,
    "catch_snorlax": catch_snorlax,
    "catch_zapdos": catch_zapdos,
    "catch_electrode": catch_electrode,
}


# probe_maze tape (fixtures/_stalls/evolve_stones_163922.ss1 → door): the
# Viridian gym spinner rows defeat live pathing on the way OUT (the walker
# paced (1-3,7) for 8 retries); the tape rides the spinners deliberately —
# Right at (10,3) slides to (17,3), Right again chains to (18,14), then the
# east wall column walks down to the exit.
_VIRIDIAN_GYM_EXIT_TAPE = [
    ("Up", (2, 6)), ("Right", (3, 6)), ("Right", (4, 6)), ("Right", (5, 6)),
    ("Right", (6, 6)), ("Right", (7, 6)), ("Up", (7, 5)), ("Up", (7, 4)),
    ("Up", (7, 3)), ("Right", (8, 3)), ("Right", (9, 3)), ("Right", (10, 3)),
    ("Right", (17, 3)), ("Right", (18, 14)), ("Down", (18, 15)),
    ("Down", (18, 16)), ("Down", (18, 17)), ("Down", (18, 18)),
    ("Down", (18, 19)), ("Down", (18, 20)), ("Down", (18, 21)),
    ("Down", (18, 22)), ("Left", (17, 22)),
]


def leave_viridian_gym() -> Generator:
    """Exit the Viridian gym via the probed spinner tape (live A* handles
    the maze inbound but paces forever outbound). (17,22) is a door warp —
    stepping on it lands in Viridian City."""
    from modules.map_data import MapFRLG
    from modules.modes.util.walking import (
        navigate_to as navigate_same_level,
        wait_for_player_avatar_to_be_controllable,
    )
    from modules.player import get_player_avatar

    if tuple(get_player_avatar().map_group_and_number) != MapFRLG.VIRIDIAN_CITY_GYM.value:
        return
    yield from navigate_same_level(MapFRLG.VIRIDIAN_CITY_GYM, (2, 7))  # tape anchor
    yield from _walk_route(_VIRIDIAN_GYM_EXIT_TAPE)
    yield from wait_for_player_avatar_to_be_controllable("B")


def _register_evolution_skills() -> None:
    from dexbot.evolution import evolve_levels, evolve_stones

    STORY_SKILLS["evolve_stones"] = evolve_stones
    STORY_SKILLS["evolve_levels"] = evolve_levels


def get_moon_stone() -> Generator:
    """Mt Moon 1F's unclaimed Moon Stone ball (local_id 13 @ (3,2)) — feeds
    one Moon evolution (Nidoqueen first per STONE_PLANS order). Kanto's
    other Moon Stones are already collected or hidden items; Sevii has more."""
    from modules.items import get_item_bag, get_item_by_name
    from modules.map_data import MapFRLG

    from dexbot.items_ground import collect_item_balls

    if get_item_bag().quantity_of(get_item_by_name("Moon Stone")) > 0:
        return
    yield from collect_item_balls(MapFRLG.MT_MOON_1F, only=[(3, 2)])
    if get_item_bag().quantity_of(get_item_by_name("Moon Stone")) == 0:
        raise SkillError("Moon Stone ball not collected")


def _claim_gift_ball(map_enum, ball: tuple[int, int], skill: str) -> Generator:
    """Stand below a gift Poké Ball object, A, accept ('...take it?' → Yes),
    decline the nickname (B-drain). Gifts need a party slot — callers ensure
    space first."""
    from modules.context import context
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import ensure_facing_direction, wait_for_player_avatar_to_be_controllable

    yield from navigate_to(map_enum, (ball[0], ball[1] + 1))
    yield from ensure_facing_direction("Up")
    context.emulator.press_button("A")
    yield
    yield from wait_for_yes_no_question("Yes")
    yield from wait_for_no_script_to_run("B")  # B declines the nickname prompt
    yield from wait_for_player_avatar_to_be_controllable("B")


def get_eevee() -> Generator:
    """Celadon Condominiums roof room gift Eevee (obj 2 @ (7,3)). One per
    cart — its stone evolution adds a second dex entry later."""
    from modules.map_data import MapFRLG
    from modules.pokedex import get_pokedex

    from dexbot.boxes import deposit_party_fodder
    from dexbot.runner import _log_event

    if "Eevee" in {s.name for s in get_pokedex().owned_species}:
        return
    yield from deposit_party_fodder(keep=5)
    _log_event(skill="get_eevee", status="phase", phase="claim")
    yield from _claim_gift_ball(MapFRLG.CELADON_CITY_CONDOMINIUMS_ROOF_ROOM, (7, 3), "get_eevee")
    if "Eevee" not in {s.name for s in get_pokedex().owned_species}:
        raise SkillError("Eevee not received (party full or wrong tile?)")


def fighting_dojo() -> Generator:
    """Saffron Fighting Dojo: beat Master Koichi (local_id 5 — the four
    students en route are fought by the battle handler), then claim the
    HITMONLEE ball (id 6 @ (5,3)). Choosing one forfeits the other —
    single-cart exclusion, documented."""
    from modules.map_data import MapFRLG, PokemonCenter
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.pokedex import get_pokedex

    from dexbot.boxes import deposit_party_fodder
    from dexbot.catching import ensure_healthy
    from dexbot.runner import _log_event

    owned = {s.name for s in get_pokedex().owned_species}
    if "Hitmonlee" in owned or "Hitmonchan" in owned:
        return
    yield from ensure_healthy(minimum_fraction=0.9, center=PokemonCenter.SaffronCity)
    yield from deposit_party_fodder(keep=5)
    _log_event(skill="fighting_dojo", status="phase", phase="koichi")
    yield from navigate_to(MapFRLG.SAFFRON_CITY_DOJO, (6, 6))  # below Koichi @ (6,5)
    yield from talk_to_npc(5)
    yield from wait_for_no_script_to_run("B")
    yield from wait_for_player_avatar_to_be_controllable("B")
    _log_event(skill="fighting_dojo", status="phase", phase="claim")
    yield from _claim_gift_ball(MapFRLG.SAFFRON_CITY_DOJO, (5, 3), "fighting_dojo")
    if "Hitmonlee" not in {s.name for s in get_pokedex().owned_species}:
        raise SkillError("Hitmonlee not received (Koichi undefeated or ball blocked?)")


_register_evolution_skills()
STORY_SKILLS["leave_viridian_gym"] = leave_viridian_gym
STORY_SKILLS["get_moon_stone"] = get_moon_stone
STORY_SKILLS["get_eevee"] = get_eevee
STORY_SKILLS["fighting_dojo"] = fighting_dojo


def _on_sevii() -> bool:
    from modules.map_data import MapFRLG
    from modules.player import get_player_avatar

    try:
        name = MapFRLG(tuple(get_player_avatar().map_group_and_number)).name
    except ValueError:
        return False
    return name.startswith(("ONE_ISLAND", "TWO_ISLAND", "THREE_ISLAND"))


def sevii_accept() -> Generator:
    """Take Bill up on the One Island trip. After the declined gym-exit
    scene he waits in the Cinnabar Pokémon Center (pret: scene var 2,
    HIDE_CINNABAR_POKECENTER_BILL cleared — Bill local_id 7 @ (11,5)).
    Saying Yes runs the seagallop cutscene; the Bill→Celio scene then
    auto-plays on One Island (msgbox-only — B drains it safely)."""
    from modules.map_data import PokemonCenter
    from modules.memory import GameState, get_game_state
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run, wait_for_yes_no_question
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.player import get_player_avatar, player_avatar_is_controllable
    from modules.tasks import get_global_script_context

    from dexbot.navigation import enter_center
    from dexbot.runner import _log_event

    if _on_sevii():
        return
    _log_event(skill="sevii_accept", status="phase", phase="to_bill")
    yield from enter_center(PokemonCenter.CinnabarIsland)
    yield from talk_to_npc(7)
    yield from wait_for_yes_no_question("Yes")
    _log_event(skill="sevii_accept", status="phase", phase="sail")
    # Sail cutscene + arrival scene: several chained scripts with map
    # changes. Drain until we're controllable on a Sevii map (bounded).
    from modules.context import context

    for frame in range(30_000):
        ctx = get_global_script_context()
        busy = (ctx is not None and ctx.is_active) or get_game_state() != GameState.OVERWORLD
        if not busy and player_avatar_is_controllable() and _on_sevii():
            break
        if frame % 8 == 0:
            context.emulator.press_button("B")  # advance msgboxes; harmless in fades
        yield
    else:
        raise SkillError("sevii_accept: never arrived controllable on a Sevii map")
    yield from wait_for_player_avatar_to_be_controllable("B")
    _log_event(skill="sevii_accept", status="phase", phase="arrived")


STORY_SKILLS["sevii_accept"] = sevii_accept
STORY_SKILLS["sail_to"] = lambda: sail_to("THREE_ISLAND")  # CLI default target


def sevii_return_home() -> Generator:
    """Sail back to Kanto (Vermilion). One-time state repair: sevii_accept
    entered via the Cinnabar-PC path, which left VAR_MAP_SCENE_CINNABAR_ISLAND
    at 2 so the seagallop never offered Vermilion (bot stranded on Sevii).
    A normal gym-exit accept sets it to 4; we restore that here (verified
    headless: lands in Vermilion, party intact). FUTURE: fix sevii_accept to
    take the gym-exit Yes so this repair is unnecessary. Not a cheat — no
    Pokémon/items fabricated, only the 'took the boat' progression flag."""
    from modules.memory import get_event_var, set_event_var
    from modules.player import get_player_avatar
    from modules.map_data import MapFRLG

    from dexbot.runner import _log_event

    name = MapFRLG(tuple(get_player_avatar().map_group_and_number)).name
    if name.startswith("VERMILION"):
        return
    if _island_of(name) is None:
        raise SkillError(f"sevii_return_home: not on Sevii ({name})")
    if get_event_var("MAP_SCENE_CINNABAR_ISLAND") < 4:
        _log_event(skill="sevii_return_home", status="phase", phase="repair_scene_var")
        set_event_var("MAP_SCENE_CINNABAR_ISLAND", 4)
    yield from sail_to("VERMILION")


STORY_SKILLS["sevii_return_home"] = sevii_return_home


def reach_victory_road() -> Generator:
    """Cross Kanto to Victory Road 1F entrance (Route 23 badge gates pass at
    8 badges). Staging point for the E4 push."""
    from modules.map_data import MapFRLG
    from dexbot.catching import ensure_healthy

    yield from ensure_healthy(minimum_fraction=0.9)
    yield from navigate_to(MapFRLG.VICTORY_ROAD_1F, (11, 19))


STORY_SKILLS["reach_victory_road"] = reach_victory_road


def victory_road_1f() -> Generator:
    """Clear Victory Road 1F: lead with the tank, solve the boulder switch
    (opens the barrier), climb to 2F. (2F/3F hole+barrier modeling still
    WIP — this banks verified 1F progress.)"""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_var
    from modules.player import get_player_avatar

    from dexbot.boulders import run_boulder_puzzle
    from dexbot.team import make_lead

    if tuple(get_player_avatar().map_group_and_number) == MapFRLG.VICTORY_ROAD_1F.value:
        yield from make_lead("Blastoise")
        if get_event_var("MAP_SCENE_VICTORY_ROAD_1F") != 100:
            yield from run_boulder_puzzle(MapFRLG.VICTORY_ROAD_1F, [(20, 16)])
        yield from navigate_to(MapFRLG.VICTORY_ROAD_1F, (3, 2))  # up-stairs → 2F


STORY_SKILLS["victory_road_1f"] = victory_road_1f


def victory_road_2f() -> Generator:
    """Attempt the Victory Road 2F boulder switches (two of them). WIP — 2F is
    a multi-region hole maze; run live to observe behaviour."""
    from modules.map_data import MapFRLG
    from modules.player import get_player_avatar

    from dexbot.boulders import run_boulder_puzzle
    from dexbot.team import make_lead

    if tuple(get_player_avatar().map_group_and_number) == MapFRLG.VICTORY_ROAD_2F.value:
        yield from make_lead("Blastoise")
        yield from run_boulder_puzzle(MapFRLG.VICTORY_ROAD_2F, [(2, 19), (14, 19)])


STORY_SKILLS["victory_road_2f"] = victory_road_2f


# Victory Road is a multi-floor region maze joined by ladders (warps). Each
# floor has Strength-button switches fed by a boulder; a solved switch opens a
# barrier that connects regions. Exit to Route 23 (→ Indigo) is on 2F east
# (warps 47-49,13). The static graph can't model post-push state reliably, so
# we drive it greedily against LIVE state: on each floor solve whatever switch
# is locally reachable (run_boulder_puzzle uses the game's own pathfinder),
# then try the exit, else hop to a reachable ladder/region. Bounded + logged.
_VR_SWITCHES = {  # floor (group,num) -> switch tiles on that floor
    (1, 39): [(20, 16)],
    (1, 40): [(2, 19), (14, 19)],
    (1, 41): [(7, 7)],
}
# (floor, switch) -> scene var that flips to 100 once the switch is pressed.
# Lets us skip switches already solved on a prior run instead of trying to
# re-solve them (the boulder sits on the switch; templates still show spawns).
_VR_SWITCH_VAR = {
    ((1, 39), (20, 16)): "MAP_SCENE_VICTORY_ROAD_1F",
    ((1, 40), (2, 19)): "MAP_SCENE_VICTORY_ROAD_2F_BOULDER1",
    ((1, 40), (14, 19)): "MAP_SCENE_VICTORY_ROAD_2F_BOULDER2",
    ((1, 41), (7, 7)): "MAP_SCENE_VICTORY_ROAD_3F",
}


def _vr_step_off_ladder() -> Generator:
    """If the player stands on a Ladder/warp tile, step to an open neighbour.
    navigate_to's warp-route planner WEDGES (>120s) when the start position is
    a warp tile; one step off makes every VR plan instant. After riding a
    ladder we always land on one, so call this before each navigate_to."""
    from modules.context import context
    from modules.map import get_map_data
    from modules.player import get_player_avatar

    av = get_player_avatar()
    here = tuple(av.map_group_and_number)
    pos = tuple(av.local_coordinates)
    td = get_map_data(here, pos)
    on_warp = td.tile_type.startswith("Ladder") or any(tuple(w.local_coordinates) == pos for w in td.warps)
    if not on_warp:
        return
    for direction, (dx, dy) in (("Right", (1, 0)), ("Left", (-1, 0)), ("Down", (0, 1)), ("Up", (0, -1))):
        n = (pos[0] + dx, pos[1] + dy)
        if n[0] < 0 or n[1] < 0:
            continue
        if get_map_data(here, n).collision == 0:
            for _ in range(20):
                context.emulator.press_button(direction)
                yield
                cur = tuple(get_player_avatar().local_coordinates)
                if cur != pos and tuple(get_player_avatar().map_group_and_number) == here:
                    return


def _vr_goto(map_enum, tile) -> Generator:
    """Reach `tile` on `map_enum` via the full warp-route navigator (rides
    ladders across floors). Steps off any ladder first to dodge the planner
    wedge."""
    yield from _vr_step_off_ladder()
    yield from navigate_to(map_enum, tile)


def _vr_stand(map_enum, tile) -> Generator:
    """Walk to `tile` and STAND on it (single-map A*, never rides its warp) —
    for push positions that happen to be ladder tiles, e.g. (34,19)."""
    from modules.modes.util.walking import navigate_to as _walk_level

    yield from _vr_step_off_ladder()
    yield from _walk_level(map_enum.value, tile)


def _vr_push_left_until(map_enum, boulder_xy, switch_xy, var_name) -> Generator:
    """Standing EAST of `boulder_xy`, ensure Strength is active, then shove the
    boulder LEFT until the switch var reads 100. Strength may already be active
    (a boulder solved earlier this map-visit), so activation is best-effort and
    bounded — never blocks waiting for a prompt that won't appear."""
    from modules.context import context
    from modules.memory import get_event_var
    from modules.modes.util.walking import ensure_facing_direction
    from modules.player import get_player_avatar, player_avatar_is_controllable
    from modules.tasks import get_global_script_context

    from dexbot.runner import SkillError, _log_event

    yield from ensure_facing_direction("Left")
    context.emulator.press_button("A")  # opens "use STRENGTH?" only if not already active
    for _ in range(150):  # bounded: confirm the prompt if it appears, else fall through
        script = get_global_script_context()
        active = bool(script and script.is_active)
        if active:
            context.emulator.press_button("A")  # Yes / advance the message
        elif player_avatar_is_controllable():
            break
        yield
    for shove in range(30):
        if get_event_var(var_name) == 100:
            _log_event(skill="vr_push", status="pressed", switch=switch_xy, shoves=shove)
            return
        before = tuple(get_player_avatar().local_coordinates)
        for _ in range(90):
            context.emulator.press_button("Left")
            yield
            if tuple(get_player_avatar().local_coordinates) != before:
                break
        for _ in range(16):  # boulder slide settle
            yield
    if get_event_var(var_name) != 100:
        raise SkillError(f"_vr_push_left_until: {switch_xy} not pressed after 30 shoves")


def traverse_victory_road() -> Generator:
    """Traversal of Victory Road to the Route 23 exit. navigate_to rides ladders
    fine as long as we don't PLAN from a ladder tile (that wedges the planner),
    so _vr_goto/_vr_stand step off first. Skips phases already done (scene var
    == 100) for clean crash-resume. Logs each phase.

    Route: 1F switch → up to 2F. 2F: press (2,19) [B1]. Stand at (34,19), shove
    boulder (33,19) LEFT onto (14,19) [B2]. Then navigate_to the Route 23 exit
    (the warp graph rides the east ladders once both barriers are open)."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_var
    from modules.player import get_player_avatar

    from dexbot.boulders import run_boulder_puzzle
    from dexbot.catching import ensure_healthy
    from dexbot.runner import _log_event
    from dexbot.team import make_lead

    F1, F2 = MapFRLG.VICTORY_ROAD_1F, MapFRLG.VICTORY_ROAD_2F

    def here():
        return tuple(get_player_avatar().map_group_and_number)

    def phase(name):
        av = get_player_avatar()
        _log_event(skill="vr_spine", status=name, map=MapFRLG(tuple(av.map_group_and_number)).name,
                   pos=tuple(av.local_coordinates))

    yield from make_lead("Blastoise")
    yield from ensure_healthy(minimum_fraction=0.8)

    # --- Reach Victory Road 1F if we're still out in Kanto ---
    vr_maps = {F1.value, F2.value, MapFRLG.VICTORY_ROAD_3F.value}
    if here() not in vr_maps:
        phase("reach_vr")
        yield from navigate_to(F1, (11, 19))  # VR 1F entrance from Route 23

    # --- 1F: press switch (20,16), climb to 2F (navigate_to rides the ladder) ---
    if here() == F1.value:
        phase("1f_start")
        if get_event_var("MAP_SCENE_VICTORY_ROAD_1F") != 100:
            yield from run_boulder_puzzle(F1, [(20, 16)])
        yield from _vr_goto(F2, (1, 9))

    # --- 2F: press B1 switch (2,19) (boulder (6,17), reachable from entrance) ---
    if here() == F2.value and get_event_var("MAP_SCENE_VICTORY_ROAD_2F_BOULDER1") != 100:
        phase("b1_start")
        yield from _vr_step_off_ladder()  # land tile (1,9) is a ladder → step off first
        yield from run_boulder_puzzle(F2, [(2, 19)])
        phase("b1_done")

    # --- B2 switch (14,19): with pristine boulders, run_boulder_puzzle picks
    #     boulder (33,19) and shoves it LEFT onto the switch. (Needs Strength
    #     re-activated: a fresh 2F visit or after crossing floors.) ---
    if here() == F2.value and get_event_var("MAP_SCENE_VICTORY_ROAD_2F_BOULDER2") != 100:
        phase("b2_start")
        yield from _vr_step_off_ladder()
        yield from run_boulder_puzzle(F2, [(14, 19)])
        phase("b2_done")

    # --- Exit: navigate to the Route 23 exit; the warp graph rides the east
    #     ladders ((36,17)→3F→(37,10)→2F(38,9)) now that both barriers are open ---
    if here() == F2.value:
        phase("exit")
        yield from _vr_goto(MapFRLG.ROUTE_23, (18, 28))
    phase("done")


STORY_SKILLS["traverse_victory_road"] = traverse_victory_road


# Sevii harbors: (harbor map enum name, sailor local_id, sailor-below tile).
# stand = the harbor warp-landing tile (open row y=3); talk_to_npc walks the
# last step up to the sailor (only (8,5) is walkable-adjacent — the pier is a
# tight column, the sailor is at the top with water on three sides).
_HARBORS = {
    "ONE_ISLAND": ("ONE_ISLAND_HARBOR", 2, (8, 3)),
    "TWO_ISLAND": ("TWO_ISLAND_HARBOR", 2, (8, 3)),
    "THREE_ISLAND": ("THREE_ISLAND_HARBOR", 2, (8, 3)),
}
# Seagallop cursor index by (from_island, to_island). Two layouts (pret
# seagallop.inc): the no-Vermilion MULTICHOICE_ISLAND_* branch (Cinnabar
# scene < 4) and the Vermilion-allowed branch (scene >= 4), which inserts
# VERMILION at index 0 and shifts the islands down by one.
_SEAGALLOP_NOVERM = {
    ("ONE_ISLAND", "TWO_ISLAND"): 0, ("ONE_ISLAND", "THREE_ISLAND"): 1,
    ("TWO_ISLAND", "ONE_ISLAND"): 0, ("TWO_ISLAND", "THREE_ISLAND"): 1,
    ("THREE_ISLAND", "ONE_ISLAND"): 0, ("THREE_ISLAND", "TWO_ISLAND"): 1,
}
_SEAGALLOP_VERM = {
    ("ONE_ISLAND", "VERMILION"): 0, ("ONE_ISLAND", "TWO_ISLAND"): 1, ("ONE_ISLAND", "THREE_ISLAND"): 2,
    ("TWO_ISLAND", "VERMILION"): 0, ("TWO_ISLAND", "ONE_ISLAND"): 1, ("TWO_ISLAND", "THREE_ISLAND"): 2,
    ("THREE_ISLAND", "VERMILION"): 0, ("THREE_ISLAND", "ONE_ISLAND"): 1, ("THREE_ISLAND", "TWO_ISLAND"): 2,
}


def _seagallop_index(origin: str, destination: str) -> int | None:
    from modules.memory import get_event_var

    verm = get_event_var("MAP_SCENE_CINNABAR_ISLAND") >= 4
    return (_SEAGALLOP_VERM if verm else _SEAGALLOP_NOVERM).get((origin, destination))


def _island_of(map_name: str) -> str | None:
    for isl in ("ONE_ISLAND", "TWO_ISLAND", "THREE_ISLAND"):
        if map_name.startswith(isl):
            return isl
    return None


def sail_to(destination: str) -> Generator:
    """Travel by Seagallop. `destination`: ONE_ISLAND / TWO_ISLAND /
    THREE_ISLAND / VERMILION (VERMILION = home to Kanto, only when Cinnabar
    scene >= 4). Walks to the current island's harbor, tells the sailor,
    drains the ferry cutscene. No Yes/No — the menu sails directly."""
    from modules.context import context
    from modules.map_data import MapFRLG
    from modules.memory import GameState, get_game_state
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_multiple_choice_question
    from modules.player import get_player_avatar, player_avatar_is_controllable
    from modules.tasks import get_global_script_context

    from dexbot.runner import _log_event

    def _landed() -> str:
        name = MapFRLG(tuple(get_player_avatar().map_group_and_number)).name
        return "VERMILION" if name.startswith("VERMILION") else (_island_of(name) or "")

    origin = _island_of(MapFRLG(tuple(get_player_avatar().map_group_and_number)).name)
    if _landed() == destination:
        return
    if origin is None:
        raise SkillError(f"sail_to: not on a Sevii island ({get_player_avatar().map_group_and_number})")
    index = _seagallop_index(origin, destination)
    if index is None:
        raise SkillError(f"sail_to: no route {origin}->{destination} (Vermilion needs Cinnabar scene >= 4)")

    harbor_name, sailor_id, stand = _HARBORS[origin]
    harbor = MapFRLG[harbor_name]
    _log_event(skill="sail_to", status="phase", phase=f"{origin}_to_{destination}")
    yield from navigate_to(harbor, stand)
    yield from talk_to_npc(sailor_id)
    yield from wait_for_multiple_choice_question(index)
    for frame in range(20_000):
        ctx = get_global_script_context()
        busy = (ctx is not None and ctx.is_active) or get_game_state() != GameState.OVERWORLD
        if not busy and player_avatar_is_controllable() and _landed() == destination:
            return
        if frame % 8 == 0:
            context.emulator.press_button("B")  # drain arrival msgboxes
        yield
    raise SkillError(f"sail_to: never landed on {destination}")


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
    # battle, not KO it. Some story skills embed a catch too.
    _embedded_catch: dict[str, str] = {}
    if which.startswith("catch_"):
        handler = make_catch_decider(which.removeprefix("catch_").capitalize())
    elif which in _embedded_catch:
        handler = make_catch_decider(_embedded_catch[which])
    else:
        handler = fight_all_battles

    attempts = 0
    last_error = None
    while True:
        attempts += 1
        try:
            run_skill(STORY_SKILLS[which](), which, timeout_frames=900_000, on_battle_started=handler)
            break
        except Exception as e:  # noqa: BLE001 — bounded retries; last error re-raised
            # Fast-fail on deterministic failures: the same error (same stall
            # position) twice in a row means retrying is theater — the walker
            # paced the Viridian gym spinners through 8 heal-retry cycles
            # before anyone noticed. Flaky failures differ run to run.
            error_key = str(e).split("(stall state:")[0]
            if error_key == last_error:
                raise
            last_error = error_key
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
