"""dexbot — living-dex bot built on top of the pokebot-gen3 executor.

Importing this package makes the pokebot-gen3 checkout importable and
preloads the vendored libmgba shared library (no root install needed).
"""

import ctypes
import faulthandler
import hashlib
import signal
import sys
from pathlib import Path

# `kill -USR1 <pid>` dumps all Python stacks to stderr — the only way to see
# where a wedged headless run is spinning (yama ptrace_scope blocks py-spy).
if hasattr(signal, "SIGUSR1"):
    try:
        faulthandler.register(signal.SIGUSR1)
    except (ValueError, RuntimeError):
        pass  # non-main thread or unsupported platform

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POKEBOT_ROOT = PROJECT_ROOT / "pokebot-gen3"
ROM_PATH = PROJECT_ROOT / "roms" / "firered.gba"
ROM_MD5 = "e26ee0d44e809351c8ce2d73c7400cdd"  # FireRed USA 1.0

_VENDOR_LIB = PROJECT_ROOT / "vendor" / "lib" / "libmgba.so.0.10"

if str(POKEBOT_ROOT) not in sys.path:
    sys.path.insert(0, str(POKEBOT_ROOT))

if _VENDOR_LIB.exists():
    # _pylib.abi3.so links against libmgba.so.0.10 without an rpath; preloading
    # it with RTLD_GLOBAL avoids needing LD_LIBRARY_PATH or a root install.
    ctypes.CDLL(str(_VENDOR_LIB), mode=ctypes.RTLD_GLOBAL)


def verify_rom() -> None:
    """Abort with a clear message unless roms/firered.gba is FireRed USA 1.0."""
    if not ROM_PATH.is_file():
        sys.exit(f"ROM not found at {ROM_PATH} — place a FireRed (USA) 1.0 .gba file there.")
    md5 = hashlib.md5(ROM_PATH.read_bytes()).hexdigest()
    if md5 != ROM_MD5:
        sys.exit(
            f"ROM MD5 mismatch: got {md5}, expected {ROM_MD5} (FireRed USA 1.0). "
            "Refusing to run with an unverified ROM."
        )
