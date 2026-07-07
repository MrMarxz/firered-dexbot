"""Dev harness: resume a skill from a phase checkpoint in seconds.

Every `_log_event(status="phase")` snapshots the emulator to
fixtures/_phases/{skill}_{phase}.ss1. Skills are flag-idempotent (they skip
already-completed steps), so resuming = load the checkpoint, run the skill.

Usage:
    .venv/bin/python -m dexbot.dev_resume <skill> <phase>
    .venv/bin/python -m dexbot.dev_resume beat_surge door
    .venv/bin/python -m dexbot.dev_resume get_hm_cut board_and_ship

Skill names resolve from dexbot.story.STORY_SKILLS and dexbot.gyms.GYMS.
"""

import sys

from dexbot import PROJECT_ROOT


def main() -> None:
    skill_name, phase = sys.argv[1], sys.argv[2]
    checkpoint = PROJECT_ROOT / "fixtures" / "_phases" / f"{skill_name}_{phase}.ss1"
    if not checkpoint.exists():
        available = sorted(p.name for p in (PROJECT_ROOT / "fixtures" / "_phases").glob("*.ss1"))
        raise SystemExit(f"No checkpoint {checkpoint.name}. Available: {available}")

    from dexbot.emulator import setup_headless_emulator

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state(checkpoint.read_bytes())
    context.emulator.run_single_frame()

    from dexbot.catching import fight_all_battles
    from dexbot.gyms import GYMS
    from dexbot.runner import run_skill
    from dexbot.story import STORY_SKILLS

    skill = {**STORY_SKILLS, **{f"beat_{k}": v for k, v in GYMS.items()}}.get(skill_name) or GYMS.get(
        skill_name.removeprefix("beat_")
    )
    if skill is None:
        raise SystemExit(f"Unknown skill {skill_name!r}")
    run_skill(skill(), skill_name, timeout_frames=900_000, on_battle_started=fight_all_battles)
    print(f"{skill_name} done (resumed from {phase})")


if __name__ == "__main__":
    main()
