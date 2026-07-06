"""M7: gym battles. Each badge is a sub-milestone with its own savestate test.

The battle itself is upstream's DefaultBattleStrategy (damage-calc move choice,
switching). Our job per gym: precondition checks (level, type coverage), the
walk, the talk, and verifying the badge flag afterwards.

Run:  .venv/bin/python -m dexbot.gyms brock
"""

import sys
from typing import Generator

from dexbot import PROJECT_ROOT
from dexbot.catching import ensure_healthy
from dexbot.navigation import navigate_to
from dexbot.planner import grind_levels
from dexbot.runner import SkillError, run_skill


def beat_brock(min_level: int = 13) -> Generator:
    """Beat Brock (requires a healthy, sufficiently-leveled water lead)."""
    from modules.map_data import MapFRLG
    from modules.memory import get_event_flag
    from modules.modes.util.higher_level_actions import talk_to_npc
    from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
    from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable
    from modules.pokemon_party import get_party

    if get_event_flag("BADGE01_GET"):
        return

    # Water is 4x effective against Geodude/Onix, Fighting 2x; the level floor is
    # the "projected to lose" guard for v1 (proper damage projection in later gyms).
    if max(p.level for p in get_party() if not p.is_egg) < min_level:
        yield from grind_levels(min_level)  # caller must run with a Fight policy
    good_moves = ("Bubble", "Water Gun", "Karate Chop", "Low Kick")
    if not any(get_party().has_pokemon_with_move(move) for move in good_moves):
        moves = [(p.species.name, p.level, [m.move.name for m in p.moves if m]) for p in get_party()]
        raise SkillError(f"No move that beats Rock-types in the party: {moves}")

    from modules.map_data import PokemonCenter

    yield from ensure_healthy(minimum_fraction=0.99, center=PokemonCenter.PewterCity)

    yield from navigate_to(MapFRLG.PEWTER_CITY_GYM, (4, 3))  # in front of Brock
    yield from talk_to_npc(1)  # Brock
    yield from wait_for_no_script_to_run("A")
    yield from wait_for_player_avatar_to_be_controllable("A")

    if not get_event_flag("BADGE01_GET"):
        raise SkillError("Brock was not defeated (badge flag unset)")


GYMS = {"brock": beat_brock}


def main() -> None:
    from dexbot.emulator import setup_headless_emulator

    which = sys.argv[1] if len(sys.argv) > 1 else "brock"
    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m6_pre_brock_dex.ss1").read_bytes())
    context.emulator.run_single_frame()

    from dexbot.catching import fight_all_battles

    run_skill(GYMS[which](), f"beat_{which}", timeout_frames=900_000, on_battle_started=fight_all_battles)
    print(f"{which} defeated")
    (PROJECT_ROOT / "fixtures" / f"m7_badge_{which}.ss1").write_bytes(context.emulator.get_save_state())


if __name__ == "__main__":
    main()
