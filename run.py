"""Living-dex runner: python run.py --goal living-dex

Boots the persistent 'livingdex' profile (resumes from its last state, or plays
the opening from a fresh save), then loops the deterministic planner. Writes
JSONL telemetry and an auto-savestate checkpoint every 5 minutes of game time.

LLM for reasoning, determinism for execution: the L2 layer (dexbot/llm_planner.py)
is consulted at objective and failure boundaries when enabled; every consultation
falls back to the deterministic default, so this loop also runs LLM-free.
"""

import argparse
import time

import dexbot  # noqa: F401 — sys.path + libmgba bootstrap
from dexbot import verify_rom


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", default="living-dex", choices=["living-dex"])
    parser.add_argument("--profile", default="livingdex")
    parser.add_argument("--video", action="store_true", help="show a live game window (needs a display)")
    args = parser.parse_args()

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
            context.emulator.create_save_state(suffix="auto")
            last_checkpoint = frame

    runner.frame_hooks.extend([telemetry.tick, checkpoint_hook])

    if args.video:
        # Live view: a plain Tk window fed from the emulator's frame buffer
        # every 30 frames (~0.5-2 fps of wall time at unthrottled speed — a
        # fast-forward view, not gameplay speed). Closing the window is safe;
        # the run continues headless.
        import tkinter as tk

        from PIL import ImageTk

        window = tk.Tk()
        window.title(f"dexbot — {args.profile}")
        video_label = tk.Label(window)
        video_label.pack()
        video_state = {"frame": 0, "alive": True}

        def video_hook() -> None:
            if not video_state["alive"]:
                return
            video_state["frame"] += 1
            if video_state["frame"] % 30:
                return
            try:
                image = ImageTk.PhotoImage(context.emulator.get_screenshot().resize((480, 320)))
                video_label.configure(image=image)
                video_label.image = image
                window.update()
            except tk.TclError:  # window closed by the user
                video_state["alive"] = False

        runner.frame_hooks.append(video_hook)

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
    context.emulator.create_save_state(suffix="final")


if __name__ == "__main__":
    main()
