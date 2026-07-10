"""Living-dex runner: python run.py --goal living-dex

Boots the persistent 'livingdex' profile (resumes from its last state, or plays
the opening from a fresh save), then loops the deterministic planner. Writes
JSONL telemetry and an auto-savestate checkpoint every 5 minutes of game time.

LLM for reasoning, determinism for execution: the L2 layer (dexbot/llm_planner.py)
is consulted at objective and failure boundaries when enabled; every consultation
falls back to the deterministic default, so this loop also runs LLM-free.
"""

import argparse
import faulthandler
import os
import time

import dexbot  # noqa: F401 — sys.path + libmgba bootstrap
from dexbot import verify_rom

if os.environ.get("DEXBOT_DUMP"):
    # Ops instrumentation: dump all stacks to stderr every 30s — cheap, and
    # the only way to see WHERE a long-running process spends its wedge time
    # (yama blocks py-spy; single USR1 samples land on innocent frames).
    faulthandler.dump_traceback_later(30, repeat=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", default="living-dex", choices=["living-dex"])
    parser.add_argument("--profile", default="livingdex")
    parser.add_argument("--video", action="store_true", help="(deprecated: the live window is on by default)")
    parser.add_argument("--no-video", action="store_true", help="run without the live game window")
    args = parser.parse_args()

    if args.no_video:
        import os

        os.environ["DEXBOT_VIDEO"] = "0"

    verify_rom()

    from dexbot.emulator import get_or_create_profile, setup_headless_emulator

    # is_test_run=False: loads/saves the profile's current_state.ss1, so a
    # restart resumes where the last run stopped.
    context = setup_headless_emulator(profile=get_or_create_profile(args.profile), is_test_run=False)

    from dexbot import runner
    from dexbot.telemetry import TelemetryLogger

    telemetry = TelemetryLogger(interval_frames=600)
    checkpoint_interval_frames = 5 * 60 * 60  # 5 minutes of game time
    last_checkpoint = 0

    def checkpoint_hook() -> None:
        nonlocal last_checkpoint
        frame = context.emulator.get_frame_count()
        if frame - last_checkpoint >= checkpoint_interval_frames:
            # NEVER checkpoint outside a calm overworld: a wedged battle saved
            # as current_state.ss1 poisons every future resume (the run boots
            # straight back into the unresolvable fight — Diglett Cave incident).
            from modules.memory import GameState, get_game_state

            if get_game_state() != GameState.OVERWORLD:
                return  # retry next frame tick
            context.emulator.create_save_state(suffix="auto")
            last_checkpoint = frame

    runner.frame_hooks.extend([telemetry.tick, checkpoint_hook])

    # Live window: attached by default inside setup_headless_emulator
    # (runner.attach_video_window); --no-video / DEXBOT_VIDEO=0 disables.

    from modules.memory import game_has_started
    from dexbot.runner import run_skill

    context.emulator.run_single_frame()
    if not game_has_started():
        from dexbot.new_game import run_new_game_intro

        print("[run] fresh save — playing the intro")
        run_new_game_intro(context.emulator)

    from modules.memory import get_event_flag

    if not get_event_flag("SYS_POKEDEX_GET"):
        from dexbot.openings import scripted_opening

        print("[run] running scripted opening (starter/rival/parcel/Pokédex)")
        run_skill(scripted_opening(), "scripted_opening", timeout_frames=600_000)

    from dexbot.planner import plan_and_catch_all

    print("[run] entering planner loop")
    start = time.time()
    caught = plan_and_catch_all()
    print(f"[run] planner idle — caught {caught} species in {time.time() - start:.0f}s")
    print("[run] no further objectives available (story progression beyond current milestone)")
    from modules.memory import GameState, get_game_state

    if get_game_state() == GameState.OVERWORLD:
        context.emulator.create_save_state(suffix="final")
    else:
        # Exiting mid-battle/menu (e.g. every objective deferred out of a
        # wedged fight): saving now would poison current_state.ss1 — leave
        # the last healthy auto-checkpoint as the resume point.
        print("[run] not in overworld at exit — skipping final savestate")


if __name__ == "__main__":
    main()
