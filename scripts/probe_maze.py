"""Empirical reachability probe: savestate-per-position BFS over a single map.

Ground truth for "can the player physically get from A to B" when the tile
model lies (spin mazes, phantom columns, trainer templates). For each frontier
position: load its savestate, try each direction (hold until the first coord
change, max 40 frames — releasing immediately keeps spin-tile slides on
rails), settle (coords stable 24 frames), record the landing.

Usage:
    .venv/bin/python scripts/probe_maze.py <checkpoint.ss1> <goal_x> <goal_y>

Probes the map the checkpoint is standing on. Prints every reachable tile,
exits/warps hit, script tiles, and — if the goal is reached — the direction
sequence to get there.
"""

import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dexbot.emulator import setup_headless_emulator

DIRECTIONS = ("Up", "Down", "Left", "Right")
HOLD_CAP = 40  # frames: enough for turn+step; released on first coord change
SETTLE_STABLE = 24  # coords unchanged this long = settled
SETTLE_CAP = 900  # bound long conveyor/spin slides


def main() -> None:
    ckpt, goal = Path(sys.argv[1]), (int(sys.argv[2]), int(sys.argv[3]))
    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state(ckpt.read_bytes())
    context.emulator.run_single_frame()

    from modules.memory import GameState, get_game_state
    from modules.player import get_player_avatar
    from modules.tasks import get_global_script_context

    emu = context.emulator
    home_map = get_player_avatar().map_group_and_number
    start = tuple(get_player_avatar().local_coordinates)
    print(f"probing map {home_map} from {start} toward {goal}", flush=True)

    def busy() -> bool:
        if get_game_state() != GameState.OVERWORLD:
            return True
        ctx = get_global_script_context()
        return ctx is not None and ctx.is_active

    def resolve_battle() -> bool:
        """Fight through whatever script/battle just fired. True if we survived
        on the same map (post-fight overworld state), False = treat as wall."""
        from dexbot.catching import fight_all_battles
        from dexbot.runner import SkillError, SkillTimeout, run_skill
        from modules.modes.util.tasks_scripts import wait_for_no_script_to_run
        from modules.modes.util.walking import wait_for_player_avatar_to_be_controllable

        def drain():
            yield from wait_for_no_script_to_run("B")
            yield from wait_for_player_avatar_to_be_controllable("B")

        try:
            run_skill(drain(), "probe_drain", timeout_frames=30_000, on_battle_started=fight_all_battles)
        except (SkillError, SkillTimeout):
            return False
        return get_player_avatar().map_group_and_number == home_map and not busy()

    def try_move(direction: str):
        """Returns (kind, pos): kind in walk/exit/fought/script/blocked."""
        emu.reset_held_buttons()
        before = tuple(get_player_avatar().local_coordinates)
        emu.hold_button(direction)
        for _ in range(HOLD_CAP):
            emu.run_single_frame()
            if tuple(get_player_avatar().local_coordinates) != before:
                break
        emu.reset_held_buttons()
        stable, last = 0, tuple(get_player_avatar().local_coordinates)
        for _ in range(SETTLE_CAP):
            emu.run_single_frame()
            if busy():
                # A grunt saw us (or a sign/door script). Fight through it —
                # trainer templates are fightable, not walls — then land where
                # the dust settles.
                if not resolve_battle():
                    return "script", last
                return "fought", tuple(get_player_avatar().local_coordinates)
            cur = tuple(get_player_avatar().local_coordinates)
            if get_player_avatar().map_group_and_number != home_map:
                return "exit", cur
            stable = stable + 1 if cur == last else 0
            last = cur
            if stable >= SETTLE_STABLE:
                break
        return ("blocked", last) if last == before else ("walk", last)

    def try_clear_and_move(direction: str):
        """A blocked tile may be an obstruction, not a wall: an item ball
        (A picks it up) or a stationary trainer facing away (A starts the
        fight). Press A at it, drain whatever script/battle fires, retry."""
        emu.press_button("A")
        emu.run_single_frame()
        for _ in range(30):
            emu.run_single_frame()
        if busy() and not resolve_battle():
            return "blocked", None
        if get_player_avatar().map_group_and_number != home_map:
            return "exit", tuple(get_player_avatar().local_coordinates)
        return try_move(direction)

    states = {start: emu.get_save_state()}
    parent: dict = {start: None}
    queue = deque([start])
    exits, scripts = [], []
    while queue:
        pos = queue.popleft()
        for direction in DIRECTIONS:
            emu.load_save_state(states[pos])
            emu.run_single_frame()
            kind, landed = try_move(direction)
            if kind == "blocked":
                kind, landed = try_clear_and_move(direction)
                if kind == "walk":
                    kind = "fought"  # path exists only after the A-press; replay needs it
            if kind in ("walk", "fought") and landed not in states:
                states[landed] = emu.get_save_state()
                parent[landed] = (pos, direction if kind == "walk" else f"A+{direction}")
                queue.append(landed)
                if landed == goal:
                    queue.clear()
                    break
            elif kind == "exit":
                exits.append((pos, direction, landed))
            elif kind == "script":
                scripts.append((pos, direction))
        print(f"  frontier={len(queue)} seen={len(states)}", flush=True)

    print(f"\nreachable ({len(states)}): {sorted(states)}")
    print(f"exits: {exits}")
    print(f"script tiles: {sorted(set(scripts))}")
    if goal in parent:
        path, node = [], goal
        while parent[node]:
            prev, d = parent[node]
            path.append((d, node))
            node = prev
        print(f"GOAL {goal} REACHED: {list(reversed(path))}")
    else:
        print(f"GOAL {goal} NOT reachable")


if __name__ == "__main__":
    main()
