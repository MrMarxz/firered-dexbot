"""Frame loop for running L1 skills, modeled on upstream's bot-mode main loop.

Includes the bot listeners (battle handling, evolution scenes, ...) so skills
get the same runtime services as upstream modes. Every skill run gets a frame
timeout and a structured telemetry record — a skill can fail, but it can never
hang silently.
"""

import json
import time
from typing import Generator

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


def _make_bot_mode(skill: Generator):
    from modules.modes._interface import BotMode

    class DexSkillMode(BotMode):
        @staticmethod
        def name() -> str:
            return "DexSkill"

        def run(self) -> Generator:
            yield from skill

    return DexSkillMode()


def run_skill(skill: Generator, name: str, timeout_frames: int = 100_000) -> None:
    """Drive a skill generator one frame at a time until it finishes.

    Mirrors upstream's main loop: builds FrameInfo, runs bot listeners (which
    push battle/evolution handlers onto the controller stack), then advances
    the topmost controller. Raises SkillTimeout/SkillError; outcome is logged
    to logs/skills.jsonl either way.
    """
    from modules.context import context
    from modules.memory import get_game_state
    from modules.modes import FrameInfo, get_bot_listeners
    from modules.tasks import get_global_script_context, get_tasks

    bot_mode = _make_bot_mode(skill)
    context.bot_mode_instance = bot_mode
    context._current_bot_mode = bot_mode.name()
    context.bot_listeners = get_bot_listeners(context.rom)
    context.controller_stack.clear()
    context.controller_stack.append(bot_mode.run())

    _log_event(skill=name, status="start", frame=context.emulator.get_frame_count())
    frames = 0
    previous_frame_info = None
    try:
        while len(context.controller_stack) > 0:
            if context.bot_mode == "Manual":
                raise SkillError(f"Skill {name!r} was aborted (bot switched to Manual mode)")

            script_context = get_global_script_context()
            script_stack = script_context.stack if script_context is not None and script_context.is_active else []
            task_list = get_tasks()
            frame_info = FrameInfo(
                frame_count=context.emulator.get_frame_count(),
                game_state=get_game_state(),
                active_tasks=[task.symbol.lower() for task in task_list] if task_list is not None else [],
                script_stack=script_stack,
                controller_stack=[controller.__qualname__ for controller in context.controller_stack],
                previous_frame=previous_frame_info,
            )

            for listener in context.bot_listeners.copy():
                listener.handle_frame(bot_mode, frame_info)

            try:
                next(context.controller_stack[-1])
            except (StopIteration, GeneratorExit):
                context.controller_stack.pop()
                continue

            context.emulator.run_single_frame()
            frames += 1
            previous_frame_info = frame_info
            previous_frame_info.previous_frame = None
            if frames > timeout_frames:
                raise SkillTimeout(f"Skill {name!r} exceeded {timeout_frames} frames")
    except BaseException as e:
        _log_event(skill=name, status="timeout" if isinstance(e, SkillTimeout) else "error", error=str(e))
        raise
    finally:
        context.controller_stack.clear()
    _log_event(skill=name, status="success", frames_taken=frames)
