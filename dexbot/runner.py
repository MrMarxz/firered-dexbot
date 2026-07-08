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


class StepTimeout(SkillError):
    """A single controller step (one generator advance) exceeded its wall-time
    budget — a planning or menu loop wedged. Raised via SIGALRM so even a
    CPU-bound spin inside one step gets interrupted and reported instead of
    freezing the run for hours."""


_STEP_BUDGET_SECONDS = 120


_events_path = PROJECT_ROOT / "logs" / "skills.jsonl"

# Called once per emulated frame from run_skill — used by run.py for telemetry
# logging and periodic auto-savestates.
frame_hooks: list = []


def _log_event(**fields) -> None:
    _events_path.parent.mkdir(exist_ok=True)
    with open(_events_path, "a") as f:
        f.write(json.dumps({"time": round(time.time(), 3), **fields}) + "\n")
    if fields.get("status") == "phase":
        _checkpoint_phase(fields.get("skill", "skill"), fields.get("phase", "phase"))


def _checkpoint_phase(skill: str, phase: str) -> None:
    """Savestate at every phase boundary → fixtures/_phases/{skill}_{phase}.ss1.

    This is the dev debug loop: a failure inside phase N is re-reachable in
    seconds via `python -m dexbot.dev_resume <skill> <phase>` instead of
    re-running the whole trek. Phase boundaries are clean overworld states by
    convention (same rule as fixtures). Best-effort: never breaks the run.
    """
    try:
        from modules.context import context

        phases_dir = PROJECT_ROOT / "fixtures" / "_phases"
        phases_dir.mkdir(exist_ok=True)
        safe = f"{skill}_{phase}".replace("/", "_").replace(" ", "_")
        (phases_dir / f"{safe}.ss1").write_bytes(context.emulator.get_save_state())
    except Exception:
        pass


def _with_step_watchdog(controller) -> None:
    """Advance a controller one step under a wall-time budget. Any single step
    normally takes milliseconds; planning pathologies have wedged steps for
    hours at 100% CPU with the avatar frozen. SIGALRM interrupts even a
    CPU-bound step (main thread only — which run_skill is)."""
    import signal

    if not hasattr(signal, "SIGALRM"):
        next(controller)
        return

    def _on_alarm(signum, frame):
        raise StepTimeout(
            f"controller step exceeded {_STEP_BUDGET_SECONDS}s "
            f"(wedged at {frame.f_code.co_filename}:{frame.f_lineno} in {frame.f_code.co_name})"
        )

    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(_STEP_BUDGET_SECONDS)
    try:
        next(controller)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _make_bot_mode(skill: Generator, on_battle_started=None):
    from modules.modes._interface import BotMode

    class DexSkillMode(BotMode):
        @staticmethod
        def name() -> str:
            return "DexSkill"

        def run(self) -> Generator:
            yield from skill

        def on_battle_started(self, encounter):
            if on_battle_started is not None:
                return on_battle_started(encounter)
            return super().on_battle_started(encounter)

        def on_whiteout(self) -> bool:
            # The game already healed us at a Pokémon Center; skills re-plan
            # from wherever they are, so a whiteout is a setback, not a stop.
            _log_event(skill="whiteout", status="recovered")
            return True

    return DexSkillMode()


def run_skill(skill: Generator, name: str, timeout_frames: int = 100_000, on_battle_started=None) -> None:
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

    bot_mode = _make_bot_mode(skill, on_battle_started)
    context.bot_mode_instance = bot_mode
    context._current_bot_mode = bot_mode.name()
    context.bot_listeners = get_bot_listeners(context.rom)
    context.controller_stack.clear()
    context.controller_stack.append(bot_mode.run())

    _log_event(skill=name, status="start", frame=context.emulator.get_frame_count())
    frames = 0
    calm_overworld_frames = 0
    previous_frame_info = None
    try:
        while len(context.controller_stack) > 0:
            context.frame += 1
            if context.bot_mode == "Manual":
                raise SkillError(f"Skill {name!r} was aborted (bot switched to Manual mode: {context.message!r})")

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

            # Stale-controller cleanup: a battle handler can survive its battle
            # when script-started fights desync the BattleListener, leaving a
            # generator that waits forever and swallows the next battle. After
            # a sustained calm overworld stretch, drop leftovers and reset the
            # listeners so the next battle is handled from a clean slate.
            from modules.memory import GameState

            if frame_info.game_state == GameState.OVERWORLD and not frame_info.script_stack:
                calm_overworld_frames += 1
                if calm_overworld_frames == 180 and len(context.controller_stack) > 1:
                    while len(context.controller_stack) > 1:
                        context.controller_stack.pop()
                    context.bot_listeners = get_bot_listeners(context.rom)
                    _log_event(skill=name, status="cleaned_stale_battle_controllers")
            else:
                calm_overworld_frames = 0

            try:
                if len(context.controller_stack) > 0:
                    _with_step_watchdog(context.controller_stack[-1])
            except (StopIteration, GeneratorExit):
                # Upstream semantics: pop and STILL advance the frame below.
                # Re-processing the same frame would double-run the listeners,
                # which re-arms the BattleListener during BATTLE_ENDING and
                # pushes a duplicate battle handler that never terminates.
                context.controller_stack.pop()
                if len(context.controller_stack) == 0:
                    break

            context.emulator.run_single_frame()
            frames += 1
            for hook in frame_hooks:
                hook()
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
