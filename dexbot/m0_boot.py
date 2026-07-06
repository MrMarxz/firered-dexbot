"""M0 proof: boot FireRed headless to the title screen, dump screenshot + memory snapshot.

Run from project root:  .venv/bin/python -m dexbot.m0_boot
"""

import json

from dexbot import PROJECT_ROOT, ROM_MD5
from dexbot.emulator import setup_headless_emulator

MAX_FRAMES = 30_000
PROOF_DIR = PROJECT_ROOT / "proof"


def main() -> None:
    context = setup_headless_emulator(is_test_run=True)

    from modules.game import get_symbol
    from modules.memory import get_game_state_symbol

    emulator = context.emulator
    symbol = ""
    for frame in range(MAX_FRAMES):
        # Tap A every 30 frames to skip through copyright/intro sequence.
        if frame % 30 == 0:
            emulator.press_button("A")
        emulator.run_single_frame()
        symbol = get_game_state_symbol()
        if symbol == "CB2_TITLESCREENRUN":
            break
    else:
        raise SystemExit(f"Never reached title screen in {MAX_FRAMES} frames (last callback2: {symbol})")

    # Let the fade-in finish so the screenshot actually shows the title screen.
    for _ in range(600):
        emulator.run_single_frame()

    PROOF_DIR.mkdir(exist_ok=True)
    emulator.get_screenshot().save(PROOF_DIR / "m0_title.png")

    snapshot = {
        "rom_md5": ROM_MD5,
        "game": str(context.profile.rom.game_name),
        "frame_count": emulator.get_frame_count(),
        "callback2_symbol": symbol,
        "gMain_address": hex(get_symbol("gMain")[0]),
        "gMain_first_16_bytes": emulator.read_bytes(get_symbol("gMain")[0], 16).hex(),
    }
    (PROOF_DIR / "m0_memory.json").write_text(json.dumps(snapshot, indent=2) + "\n")

    fixtures = PROJECT_ROOT / "fixtures"
    fixtures.mkdir(exist_ok=True)
    (fixtures / "m0_title.ss1").write_bytes(emulator.get_save_state())

    print(f"Title screen reached at frame {snapshot['frame_count']} ({symbol})")
    print(f"Proof written to {PROOF_DIR}/m0_title.png and m0_memory.json; fixture: fixtures/m0_title.ss1")


if __name__ == "__main__":
    main()
