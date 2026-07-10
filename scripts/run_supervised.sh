#!/usr/bin/env bash
# Supervisor for the living-dex run: the emulator occasionally dies silently
# (segfault-class, roughly hourly); run.py resumes from current_state.ss1
# losing at most 5 game-minutes. Restart on crash; stop on clean exit
# (planner idle) or after too many rapid failures.
cd "$(dirname "$0")/.."

# ONE emulator rule: a second run.py silently corrupts current_state.ss1
# (two processes checkpoint interleaved — a stale world overwrote a fresh
# catch). Refuse to start while another instance is alive.
if pgrep -f "run.py --goal" >/dev/null 2>&1; then
    echo "[supervisor] another run.py is already alive — refusing to double-launch." >&2
    exit 2
fi

FAILS=0
while true; do
    START=$(date +%s)
    .venv/bin/python -u run.py --goal living-dex "$@"
    CODE=$?
    if [ $CODE -eq 0 ]; then
        echo "[supervisor] clean exit (planner idle) — done."
        break
    fi
    ELAPSED=$(( $(date +%s) - START ))
    if [ $ELAPSED -lt 120 ]; then
        FAILS=$((FAILS + 1))
    else
        FAILS=0
    fi
    if [ $FAILS -ge 5 ]; then
        echo "[supervisor] 5 rapid failures — giving up (real bug, not emulator flake)."
        exit 1
    fi
    echo "[supervisor] run died (exit $CODE) after ${ELAPSED}s — resuming from checkpoint."
    sleep 2
done
