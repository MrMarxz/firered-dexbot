#!/usr/bin/env bash
# Supervisor for single live skills (dexbot.story / dexbot.gyms): the mGBA
# core segfaults occasionally (native crash — no Python traceback, the video
# window just freezes blank). The live profile checkpoints to
# current_state.ss1, so a crashed skill resumes losing only in-flight
# progress. Restart on crash; stop on clean exit or rapid-failure loop.
#
# Usage:  scripts/run_skill_supervised.sh story catch_zapdos
#         scripts/run_skill_supervised.sh gyms blaine
cd "$(dirname "$0")/.."

MODULE="$1"; shift
if [ -z "$MODULE" ] || [ -z "$1" ]; then
    echo "usage: $0 <story|gyms> <skill> [args...]" >&2
    exit 2
fi

# ONE emulator rule: concurrent processes on the live profile corrupt
# current_state.ss1 (interleaved checkpoints lost three catches once).
if pgrep -f "run.py --goal" >/dev/null 2>&1 || pgrep -f "dexbot.story .* --live" >/dev/null 2>&1 \
   || pgrep -f "dexbot.gyms .* --live" >/dev/null 2>&1; then
    echo "[skill-supervisor] another live emulator process is running — refusing." >&2
    exit 2
fi

export LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/libgcc_s.so.1"

FAILS=0
while true; do
    START=$(date +%s)
    .venv/bin/python -u -m "dexbot.$MODULE" "$@" --live
    CODE=$?
    if [ $CODE -eq 0 ]; then
        echo "[skill-supervisor] clean exit — done."
        break
    fi
    ELAPSED=$(( $(date +%s) - START ))
    if [ $ELAPSED -lt 120 ]; then
        FAILS=$((FAILS + 1))
    else
        FAILS=0
    fi
    if [ $FAILS -ge 4 ]; then
        echo "[skill-supervisor] 4 rapid failures — giving up (real bug, not emulator flake)."
        exit 1
    fi
    echo "[skill-supervisor] run died (exit $CODE) after ${ELAPSED}s — resuming from checkpoint."
    sleep 2
done
