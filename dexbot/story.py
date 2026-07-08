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


def clear_rocket_hideout() -> Generator:
    """Celadon Game Corner → Rocket Hideout → Giovanni → the SILPH SCOPE.
    Unlocks Pokémon Tower catches and, downstream, the Poké Flute/Snorlax.

    Layout facts (empirical): grunt obj 11 guards the poster at (11,1); the
    hidden stairs open at (15,2) (metatile swap — cached collision is stale, so
    the approach is blind). B4F's Lift Key section is stair-reachable; the
    Giovanni section is ELEVATOR-ONLY (doors: B1F (24,25), car panel bg (0,2),
    exit lands B4F (20-21,23)). Scope item ball appears at (20,5) after the fight."""
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
    if get_item_bag().quantity_of(scope) > 0:
        return

    def drain(button: str = "B") -> Generator:
        yield from wait_for_no_script_to_run(button)
        yield from wait_for_player_avatar_to_be_controllable(button)

    hideout_maps = {(1, 42), (1, 43), (1, 44), (1, 45), (1, 46)}
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

    if get_item_bag().quantity_of(get_item_by_name("Lift Key")) == 0:
        _log_event(skill="clear_rocket_hideout", status="phase", phase="lift_key")
        yield from navigate_to(MapFRLG.ROCKET_HIDEOUT_B4F, (3, 3))  # Grunt1/Lift Key corner
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
    yield from navigate_to(MapFRLG.ROCKET_HIDEOUT_B1F, (24, 25))  # lift doors, B1F side
    yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_ELEVATOR, (1, 2))
    yield from ensure_facing_direction("Left")  # panel bg @ (0,2)
    context.emulator.press_button("A")
    yield
    # Floor menu: B1F / B2F / B4F — pick the last entry.
    for _ in range(40):
        yield
    context.emulator.press_button("Down")
    yield
    context.emulator.press_button("Down")
    yield
    context.emulator.press_button("A")
    for _ in range(120):  # ride animation
        yield
    yield from drain()
    # Walk out of the car (south) onto B4F's Giovanni side.
    for _ in range(6):
        if get_player_avatar().map_group_and_number == MapFRLG.ROCKET_HIDEOUT_B4F.value:
            break
        context.emulator.reset_held_buttons()
        context.emulator.hold_button("Down")
        for _ in range(24):
            yield
        context.emulator.reset_held_buttons()
    if get_player_avatar().map_group_and_number != MapFRLG.ROCKET_HIDEOUT_B4F.value:
        raise SkillError("Elevator did not deliver us to B4F")

    _log_event(skill="clear_rocket_hideout", status="phase", phase="giovanni")
    yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B4F, (19, 5))  # in front of Giovanni (obj 1 @ 19,4)
    yield from talk_to_npc(1)
    yield from drain()
    # The Silph Scope item ball appears beside his desk (obj 2 @ 20,5).
    yield from navigate_same_level(MapFRLG.ROCKET_HIDEOUT_B4F, (20, 6))
    yield from ensure_facing_direction("Up")
    context.emulator.press_button("A")
    yield
    yield from drain()
    if get_item_bag().quantity_of(scope) == 0:
        raise SkillError("Silph Scope not obtained after Giovanni")


STORY_SKILLS = {
    "clear_mt_moon": clear_mt_moon,
    "cross_nugget_bridge": cross_nugget_bridge,
    "visit_bill": visit_bill,
    "get_hm_cut": get_hm_cut,
    "get_tea": get_tea,
    "get_vs_seeker": get_vs_seeker,
    "clear_rocket_hideout": clear_rocket_hideout,
}


def main() -> None:
    from dexbot.catching import fight_all_battles
    from dexbot.emulator import setup_headless_emulator

    which = sys.argv[1]
    fixture = sys.argv[2] if len(sys.argv) > 2 else "m7_badge_brock.ss1"
    out = sys.argv[3] if len(sys.argv) > 3 else f"m7_{which}.ss1"

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / fixture).read_bytes())
    context.emulator.run_single_frame()

    attempts = 0
    while True:
        attempts += 1
        try:
            run_skill(STORY_SKILLS[which](), which, timeout_frames=900_000, on_battle_started=fight_all_battles)
            break
        except Exception as e:  # noqa: BLE001 — bounded retries; last error re-raised
            if attempts >= 8:
                raise
            print(f"attempt {attempts} failed ({type(e).__name__}: {e}); healing, then retrying")
            from dexbot.catching import ensure_healthy

            try:
                run_skill(ensure_healthy(minimum_fraction=2.0), "retry_heal", timeout_frames=120_000)
            except Exception as heal_error:  # noqa: BLE001
                print(f"retry heal failed ({heal_error}); retrying anyway")
    print(f"{which} done")
    (PROJECT_ROOT / "fixtures" / out).write_bytes(context.emulator.get_save_state())


if __name__ == "__main__":
    main()
