"""Minimal frame loop for running L1 skills (generator-based, like upstream bot modes).

Every skill run gets a frame timeout and a structured telemetry record — a skill
can fail, but it can never hang silently.
"""

import json
import time

from dexbot import PROJECT_ROOT


class SkillError(RuntimeError):
    pass


class SkillTimeout(SkillError):
    pass


_events_path = PROJECT_ROOT / "logs" / "skills.jsonl"


def _log_event(**fields) -> None:
    _events_path.parent.mkdir(exist_ok=True)
    with open(_events_path, "a") as f:
        f.write(json.dumps({"time": round(time.time(), 3), **fields}) + "\n")


def run_skill(skill, name: str, timeout_frames: int = 30_000) -> None:
    """Drive a skill generator one frame at a time until it finishes.

    Raises SkillTimeout after `timeout_frames`, SkillError on failure. Either way
    the outcome lands in logs/skills.jsonl.
    """
    from modules.context import context

    _log_event(skill=name, status="start", frame=context.emulator.get_frame_count())
    frames = 0
    try:
        for _ in skill:
            context.emulator.run_single_frame()
            frames += 1
            if frames > timeout_frames:
                raise SkillTimeout(f"Skill {name!r} exceeded {timeout_frames} frames")
    except BaseException as e:
        _log_event(skill=name, status="timeout" if isinstance(e, SkillTimeout) else "error", error=str(e))
        raise
    _log_event(skill=name, status="success", frames_taken=frames)
