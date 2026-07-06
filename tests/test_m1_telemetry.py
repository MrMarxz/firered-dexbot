"""M1 acceptance: JSONL telemetry log contents match a known savestate."""

import json

from dexbot import PROJECT_ROOT


def test_telemetry_log_matches_known_state(tmp_path):
    from dexbot.emulator import setup_headless_emulator
    from dexbot.telemetry import TelemetryLogger

    context = setup_headless_emulator(is_test_run=True)
    context.emulator.load_save_state((PROJECT_ROOT / "fixtures" / "m1_game_start.ss1").read_bytes())

    log_path = tmp_path / "telemetry.jsonl"
    logger = TelemetryLogger(log_path, interval_frames=30)
    for _ in range(100):
        context.emulator.run_single_frame()
        logger.tick()

    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(lines) >= 3  # interval is respected: ~1 entry per 30 frames

    for entry in lines:
        assert entry["game_started"] is True
        assert entry["game_state"] == "OVERWORLD"
        assert entry["player_name"] == "AA"
        assert entry["money"] == 3000
        assert (entry["map_group"], entry["map_number"]) == (4, 1)  # player's house 2F
        assert entry["coords"] == [6, 6]
        assert entry["party"] == []
        assert entry["dex_owned"] == 0
        assert not any(entry["badges"].values())
        assert entry["in_battle"] is False

    frames = [entry["frame"] for entry in lines]
    assert frames == sorted(frames) and len(set(frames)) == len(frames)
