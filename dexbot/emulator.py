"""Headless emulator setup shared by dexbot scripts and tests.

Mirrors pokebot-gen3's own tests/utility.py:_set_up_test_emulator, but for
our persistent "livingdex" profile instead of throwaway test profiles.
"""

from pathlib import Path

from dexbot import POKEBOT_ROOT, ROM_PATH, verify_rom


def get_or_create_profile(name: str = "livingdex"):
    from modules.profiles import create_profile, load_profile_by_name, profile_directory_exists
    from modules.roms import load_rom_data

    if profile_directory_exists(name):
        return load_profile_by_name(name)
    return create_profile(name, load_rom_data(POKEBOT_ROOT / "roms" / "firered.gba"))


def setup_headless_emulator(profile=None, is_test_run: bool = False):
    """Boot a headless, unthrottled emulator and wire up the pokebot context.

    Returns the pokebot `context` singleton with `context.emulator` ready.
    """
    verify_rom()

    from modules.config import Config
    from modules.context import context
    from modules.game import set_rom
    from modules.libmgba import LibmgbaEmulator

    if profile is None:
        profile = get_or_create_profile()

    context.testing = is_test_run
    context.config = Config(POKEBOT_ROOT / "modules" / "config" / "templates")

    from modules.config.schemas_v1 import Battle

    # Unattended operation: never drop to manual mode for move learning, learn
    # the best move automatically; allow evolutions (we want evolved dex entries).
    context.config.battle = Battle(
        new_move="learn_best",
        stop_evolution=False,
        lead_cannot_battle_action="rotate",
        faint_action="rotate",
        hp_threshold=10,
    )
    context.profile = profile
    set_rom(profile.rom)
    context.emulator = LibmgbaEmulator(profile, lambda: None, is_test_run=is_test_run)
    context.emulator.set_audio_enabled(False)
    context.emulator.set_throttle(False)

    from modules.stats import StatsDatabase

    context.stats = StatsDatabase(profile)
    return context
