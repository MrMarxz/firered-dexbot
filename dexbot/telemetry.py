"""M1: decoded game-state snapshots and JSONL telemetry logging.

Everything is decoded from emulator memory via pokebot-gen3's modules —
never from pixels.
"""

import json
import time
from pathlib import Path

from dexbot import PROJECT_ROOT

BADGE_FLAGS = [f"BADGE{n:02d}_GET" for n in range(1, 9)]

# Story flags worth tracking for the dex dependency graph (extend as needed).
# Names must exist in modules/data/event_flags/frlg.txt — get_event_flag()
# silently returns False for unknown names.
FLAGS_OF_INTEREST = [
    "SYS_POKEDEX_GET",
    "BEAT_RIVAL_IN_OAKS_LAB",
    "GOT_SS_TICKET",
    "GOT_HM01",  # Cut
    "GOT_HM02",  # Fly
    "GOT_HM03",  # Surf
    "GOT_HM04",  # Strength
    "GOT_HM05",  # Flash
    "GOT_HM06",  # Rock Smash
    *BADGE_FLAGS,
]


def capture_state() -> dict:
    """Decode the current game state from memory into a JSON-serializable dict."""
    from modules.context import context
    from modules.memory import game_has_started, get_event_flag, get_game_state

    state = {
        "time": round(time.time(), 3),
        "frame": context.emulator.get_frame_count(),
        "game_state": get_game_state().name,
        "game_started": game_has_started(),
    }
    if not state["game_started"]:
        return state

    from modules.battle_state import battle_is_active
    from modules.player import get_player, get_player_avatar
    from modules.pokedex import get_pokedex
    from modules.pokemon_party import get_party

    avatar = get_player_avatar()
    player = get_player()
    pokedex = get_pokedex()
    state.update(
        {
            "player_name": player.name,
            "money": player.money,
            "map_group": avatar.map_group_and_number[0],
            "map_number": avatar.map_group_and_number[1],
            "coords": list(avatar.local_coordinates),
            "facing": avatar.facing_direction,
            "party": [
                {
                    "species": p.species.name,
                    "level": p.level,
                    "hp": p.current_hp,
                    "max_hp": p.total_hp,
                    "status": p.status_condition.name,
                }
                for p in get_party()
            ],
            "badges": {flag: get_event_flag(flag) for flag in BADGE_FLAGS},
            "flags": {flag: get_event_flag(flag) for flag in FLAGS_OF_INTEREST},
            "dex_seen": len(pokedex.seen_species),
            "dex_owned": len(pokedex.owned_species),
            "in_battle": battle_is_active(),
        }
    )
    return state


class TelemetryLogger:
    """Appends a state snapshot to a JSONL file every `interval_frames` frames.

    Call `tick()` once per emulated frame.
    """

    def __init__(self, path: Path | None = None, interval_frames: int = 120):
        self.path = path or PROJECT_ROOT / "logs" / f"telemetry_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.interval_frames = interval_frames
        self._next_frame = 0

    def tick(self) -> None:
        from modules.context import context

        frame = context.emulator.get_frame_count()
        if frame >= self._next_frame:
            self.log_now()
            self._next_frame = frame + self.interval_frames

    def log_now(self) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps(capture_state()) + "\n")
