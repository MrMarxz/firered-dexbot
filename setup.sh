#!/usr/bin/env bash
# Reproduce the dev environment from scratch. Idempotent.
# Requires: python3.12, git, curl, unzip, dpkg. ROM must be placed at roms/firered.gba manually.
set -euo pipefail
cd "$(dirname "$0")"

POKEBOT_COMMIT=5dd898f830775d448b06db6f5cd65b930540f146
LIBMGBA_URL=https://github.com/hanzi/libmgba-py/releases/download/0.2.0-2/libmgba-py_0.2.0_ubuntu-lunar.zip

# 1. pokebot-gen3 fork (pinned)
if [ ! -d pokebot-gen3 ]; then
    git clone https://github.com/40Cakes/pokebot-gen3
fi
git -C pokebot-gen3 checkout -q "$POKEBOT_COMMIT"

# 2. venv + python deps
if [ ! -d .venv ]; then
    python3.12 -m venv .venv
fi
.venv/bin/pip -q install --upgrade pip
.venv/bin/pip -q install "confz==2.0.1" "numpy~=2.1.0" setuptools "ruamel.yaml~=0.18.2" \
    "pypresence~=4.3.0" "obsws-python~=1.6.0" "discord-webhook~=1.2.1" "rich~=13.5.2" \
    "cffi~=1.17.1" "Pillow~=10.4.0" "sounddevice~=0.4.6" "pyperclip3~=0.4.1" "plyer~=2.1.0" \
    "notify-py~=0.3.42" "apispec~=6.3.0" "ttkthemes~=3.2.2" "darkdetect~=0.8.0" \
    "show-in-file-manager~=1.1.4" "aiohttp~=3.10.9" "aiortc~=1.10.0" requests pytest

# 3. libmgba python bindings (into pokebot-gen3/mgba)
if [ ! -d pokebot-gen3/mgba ]; then
    curl -sL -o /tmp/libmgba-py.zip "$LIBMGBA_URL"
    unzip -q -o /tmp/libmgba-py.zip -d pokebot-gen3/
fi

# 4. libmgba.so.0.10 vendored locally (no root needed); dexbot preloads it via ctypes
if [ ! -f vendor/lib/libmgba.so.0.10 ]; then
    mkdir -p vendor/lib /tmp/libmgba-deb
    (cd /tmp/libmgba-deb && apt-get download libmgba0.10t64 && dpkg -x libmgba0.10t64*.deb x)
    cp /tmp/libmgba-deb/x/usr/lib/x86_64-linux-gnu/libmgba.so.0.10* vendor/lib/
fi

# 5. ROM check + symlink into pokebot's roms dir
if [ ! -f roms/firered.gba ]; then
    echo "ERROR: place FireRed (USA) 1.0 at roms/firered.gba" >&2
    exit 1
fi
echo "e26ee0d44e809351c8ce2d73c7400cdd  roms/firered.gba" | md5sum -c -
ln -sf "$(pwd)/roms/firered.gba" pokebot-gen3/roms/firered.gba

echo "Setup OK. Verify with: .venv/bin/python -m pytest tests/ -q"
