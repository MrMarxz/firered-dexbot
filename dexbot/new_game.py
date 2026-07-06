"""Start a new game from a fresh boot and save a fixture once the overworld begins.

State-machine A-masher driven purely by memory state (gMain.callback2). The
naming screen gets special handling: type a few letters, START to jump to OK,
A to confirm. Player and rival both end up named "AAA…" — fine for a bot.

Run:  .venv/bin/python -m dexbot.new_game [output.ss1]
"""

import sys

from dexbot import PROJECT_ROOT
from dexbot.emulator import setup_headless_emulator

MAX_FRAMES = 60_000


def run_new_game_intro(emulator) -> int:
    """Drive from boot to the first controllable overworld frame. Returns frame count."""
    from modules.memory import GameState, game_has_started, get_game_state

    naming_script = []  # queued (frame_offset, button) actions for naming screen
    frame = 0
    overworld_since = None
    for frame in range(MAX_FRAMES):
        state = get_game_state()

        if state == GameState.NAMING_SCREEN:
            if not naming_script:
                # type 3 letters, jump to OK, confirm — spaced out generously
                naming_script = [(20, "A"), (40, "A"), (60, "A"), (90, "Start"), (120, "A"), (150, "A")]
                naming_start = frame
            for offset, button in naming_script:
                if frame - naming_start == offset:
                    emulator.press_button(button)
        else:
            if naming_script and state != GameState.NAMING_SCREEN:
                naming_script = []  # left the naming screen, reset for rival naming
            if frame % 6 == 0:
                emulator.press_button("A")
            elif frame % 6 == 3 and state == GameState.TITLE_SCREEN:
                emulator.press_button("Start")

        if game_has_started() and state == GameState.OVERWORLD:
            if overworld_since is None:
                overworld_since = frame
            elif frame - overworld_since > 120:  # settled in the overworld
                return frame
        else:
            overworld_since = None

        emulator.run_single_frame()

    raise SystemExit(f"Did not reach the overworld within {MAX_FRAMES} frames (last state: {get_game_state().name})")


def main() -> None:
    out_path = PROJECT_ROOT / "fixtures" / (sys.argv[1] if len(sys.argv) > 1 else "m1_game_start.ss1")
    context = setup_headless_emulator(is_test_run=True)
    frame = run_new_game_intro(context.emulator)

    out_path.write_bytes(context.emulator.get_save_state())

    from dexbot.telemetry import capture_state

    import json

    print(f"Overworld reached at frame {frame}; fixture saved to {out_path}")
    print(json.dumps(capture_state(), indent=1))


if __name__ == "__main__":
    main()
