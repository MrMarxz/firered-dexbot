import os
import sys
from pathlib import Path

os.environ["DEXBOT_VIDEO"] = "0"  # tests stay truly headless (video is default-on)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dexbot  # noqa: F401  — puts pokebot-gen3 on sys.path, preloads libmgba
