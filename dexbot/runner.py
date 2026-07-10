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


class StepTimeout(BaseException):
    """A single controller step (one generator advance) exceeded its wall-time
    budget — a planning or menu loop wedged. Raised via SIGALRM. Deliberately
    a BaseException: the wedged code paths sit inside broad `except Exception`
    blocks (e.g. _walkable treats any failure as 'not walkable'), which would
    swallow a normal exception and keep spinning. run_skill converts it back
    to a SkillTimeout at the step boundary."""


_STEP_BUDGET_SECONDS = 120

# Behavioral stall detector: a skill that changes NOTHING observable for this
# many frames (~8 game-minutes) is looping, not progressing. The SIGALRM
# watchdog only catches CPU wedges; this catches walk/menu/battle loops that
# happily burn frames. On trip: state dump + savestate for offline debugging.
_PROGRESS_BUDGET_FRAMES = 30_000


def _progress_sample():
    """A cheap tuple that changes whenever the run is actually getting
    somewhere: position, money, ball count, game state, party HP."""
    try:
        from modules.items import get_item_bag, get_item_by_name
        from modules.memory import get_game_state
        from modules.player import get_player, get_player_avatar
        from modules.pokemon_party import get_party

        avatar = get_player_avatar()
        return (
            avatar.map_group_and_number,
            avatar.local_coordinates,
            get_player().money,
            get_item_bag().quantity_of(get_item_by_name("Poké Ball")),
            get_item_bag().quantity_of(get_item_by_name("Great Ball")),
            int(get_game_state()),
            tuple(p.current_hp for p in get_party()),
        )
    except Exception:
        return None


def _dump_stall(name: str, sample) -> str:
    """Persist a stall diagnosis bundle: journal entry + savestate + screenshot."""
    from modules.context import context
    from modules.tasks import get_global_script_context

    stalls = PROJECT_ROOT / "fixtures" / "_stalls"
    stalls.mkdir(exist_ok=True)
    stamp = time.strftime("%H%M%S")
    state_path = stalls / f"{name}_{stamp}.ss1"
    try:
        state_path.write_bytes(context.emulator.get_save_state())
        context.emulator.get_screenshot().save(str(stalls / f"{name}_{stamp}.png"))
    except Exception:
        pass
    script = get_global_script_context()
    _log_event(
        skill=name,
        status="stall",
        sample=repr(sample),
        script=script.stack if script and script.is_active else [],
        state=str(state_path),
    )
    return str(state_path)


_events_path = PROJECT_ROOT / "logs" / "skills.jsonl"

# Called once per emulated frame from run_skill — used by run.py for telemetry
# logging and periodic auto-savestates.
frame_hooks: list = []



def attach_video_window(context, title: str = "dexbot") -> None:
    """Live game window, ON BY DEFAULT for every run (owner directive: they
    watch the window). Set DEXBOT_VIDEO=0 for true headless (the test suite
    does); no display/tkinter degrades to headless silently. Fed from the
    frame buffer every 30 frames; closing the window is safe."""
    import os

    if os.environ.get("DEXBOT_VIDEO", "1") == "0":
        return
    try:
        import tkinter as tk

        from PIL import ImageTk

        window = tk.Tk()
    except Exception:
        return  # no tkinter or no DISPLAY — run headless
    window.title(title)
    label = tk.Label(window)
    label.pack()
    state = {"n": 0, "alive": True}

    def hook() -> None:
        if not state["alive"]:
            return
        state["n"] += 1
        if state["n"] % 30:
            return
        try:
            image = ImageTk.PhotoImage(context.emulator.get_screenshot().resize((480, 320)))
            label.configure(image=image)
            label.image = image
            window.update()
        except Exception:
            state["alive"] = False

    frame_hooks.append(hook)


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
    last_sample = None
    frames_at_last_progress = 0
    from collections import deque

    recent_positions: deque = deque(maxlen=10)  # sampled every 2000 frames
    recent_rest: deque = deque(maxlen=10)
    faint_menu_frames = 0
    faint_menu_gap = 0
    faint_injected = False
    battle_rescued = False
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

            # Faint→send-next safety net: script-started trainer/gym battles
            # desync the BattleListener, so nothing drives the "choose your
            # next Pokémon" menu after a faint — it hangs until the progress
            # watchdog (the Koga stall). When that menu persists with living
            # backups, inject upstream's faint handler to send the healthiest
            # mon. Hardens every multi-mon battle.
            _faint_tasks = ("task_returntochoosemonaftertext", "task_handlechoosemoninput")
            if any(t in frame_info.active_tasks for t in _faint_tasks):
                faint_menu_frames += 1
                faint_menu_gap = 0
            else:
                # Tolerate short gaps: a wedged battle handler mashing buttons
                # re-prints the menu text, cycling the task away for a few
                # frames every ~90 (measured on the Route 17 biker fight) —
                # a hard reset there kept the counter below the 240 threshold
                # forever. Only a sustained absence means the menu really closed.
                faint_menu_gap += 1
                if faint_menu_gap > 120:
                    faint_menu_frames = 0
                    faint_injected = False
            if faint_menu_frames > 240 and not faint_injected:
                from modules.pokemon_party import get_party

                if len(get_party().non_fainted_pokemon) > 0:
                    from modules.battle_handler import handle_fainted_pokemon

                    from dexbot.catching import make_healing_battle_strategy

                    context.controller_stack.append(handle_fainted_pokemon(make_healing_battle_strategy()))
                    faint_injected = True
                    _log_event(skill=name, status="faint_menu_injected")

            try:
                if len(context.controller_stack) > 0:
                    _with_step_watchdog(context.controller_stack[-1])
            except StepTimeout as wedge:
                # Convert to the normal skill-failure path here, where nothing
                # can swallow it — the deferral/retry machinery takes over.
                raise SkillTimeout(str(wedge)) from None
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
            if frames % 2000 == 0:
                sample = _progress_sample()
                if sample is not None:
                    recent_positions.append(sample[:2])
                    recent_rest.append(sample[2:])
                if sample != last_sample:
                    last_sample = sample
                    frames_at_last_progress = frames
                elif frames - frames_at_last_progress >= _PROGRESS_BUDGET_FRAMES:
                    # Battle rescue (once per skill): a stalled BATTLE usually
                    # means nothing is driving it — a skill that STARTED
                    # mid-battle (mid-battle checkpoint resume) or a stale
                    # BattleListener generator waiting for an intro that
                    # already passed. One unresolvable Diglett fight poisoned
                    # a whole catch queue this way. Drop everything above the
                    # skill and inject the universal battle handler, mashing B
                    # first (a pending message inside turn selection is a state
                    # upstream's selection handler yields on forever).
                    from modules.battle_state import battle_is_active

                    if not battle_rescued and battle_is_active():
                        from modules.battle_handler import handle_battle

                        from dexbot.catching import make_healing_battle_strategy

                        def _battle_rescue():
                            for i in range(180):
                                if i % 8 == 0:
                                    context.emulator.press_button("B")
                                yield
                            yield from handle_battle(make_healing_battle_strategy())

                        while len(context.controller_stack) > 1:
                            context.controller_stack.pop()
                        context.bot_listeners = get_bot_listeners(context.rom)
                        context.controller_stack.append(_battle_rescue())
                        battle_rescued = True
                        frames_at_last_progress = frames
                        _log_event(skill=name, status="battle_rescued")
                        continue
                    state_path = _dump_stall(name, sample)
                    raise SkillError(
                        f"Skill {name!r} made no observable progress for "
                        f"{frames - frames_at_last_progress} frames at {sample[:2] if sample else '?'} "
                        f"(stall state: {state_path})"
                    )
                # Pacing detector: oscillating between a few tiles resets the
                # standstill check above (position "changes"), so a walk loop
                # bouncing off an obstacle looked alive for hours. A full
                # window confined to a tiny bounding box on one map with
                # money/balls/HP/game-state frozen is a stall — report it
                # within ~20k frames, not never. (A ≤4-unique-tiles test
                # missed the Route 2 ledge-hop loop, which paces a 3x3 box of
                # 5-6 tiles.)
                if (
                    len(recent_positions) == recent_positions.maxlen
                    and len(set(recent_positions)) > 1
                    and len({p[0] for p in recent_positions}) == 1
                    and (
                        max(p[1][0] for p in recent_positions) - min(p[1][0] for p in recent_positions)
                        + max(p[1][1] for p in recent_positions) - min(p[1][1] for p in recent_positions)
                        <= 6
                    )
                    and len(set(recent_rest)) == 1
                ):
                    pacing_tiles = sorted(set(recent_positions))
                    state_path = _dump_stall(name, sample)
                    raise SkillError(
                        f"Skill {name!r} is pacing between {pacing_tiles} "
                        f"with no other progress (stall state: {state_path})"
                    )
            if frames > timeout_frames:
                raise SkillTimeout(f"Skill {name!r} exceeded {timeout_frames} frames")
    except BaseException as e:
        _log_event(skill=name, status="timeout" if isinstance(e, SkillTimeout) else "error", error=str(e))
        raise
    finally:
        context.controller_stack.clear()
    _log_event(skill=name, status="success", frames_taken=frames)
