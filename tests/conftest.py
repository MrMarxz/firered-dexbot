import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dexbot  # noqa: F401  — puts pokebot-gen3 on sys.path, preloads libmgba
