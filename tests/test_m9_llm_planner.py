"""M9 acceptance: garbage LLM responses always fall back to the deterministic queue."""

import pytest

from dexbot import llm_planner

OBJECTIVES = ["catch_Mankey", "catch_Spearow", "catch_Metapod"]
ENABLED = {**llm_planner.DEFAULT_CONFIG, "enabled": True}


def _with_response(monkeypatch, raw):
    monkeypatch.setattr(llm_planner, "_call_ollama", lambda state, objectives, config: raw)


def test_disabled_uses_queue_head():
    choice, rationale = llm_planner.choose_objective({}, OBJECTIVES, dict(llm_planner.DEFAULT_CONFIG))
    assert choice == "catch_Mankey"
    assert "disabled" in rationale


def test_valid_response_is_used(monkeypatch):
    _with_response(monkeypatch, '{"objective": "catch_Spearow", "rationale": "rarest first"}')
    choice, rationale = llm_planner.choose_objective({}, OBJECTIVES, ENABLED)
    assert choice == "catch_Spearow"
    assert rationale == "rarest first"


@pytest.mark.parametrize(
    "garbage",
    [
        "I think you should catch Mewtwo!",
        '{"objective": "catch_Mewtwo", "rationale": "hallucinated"}',
        '{"wrong_key": true}',
        "",
        "{broken json",
    ],
)
def test_garbage_falls_back_to_queue_head(monkeypatch, garbage):
    _with_response(monkeypatch, garbage)
    choice, rationale = llm_planner.choose_objective({}, OBJECTIVES, ENABLED)
    assert choice == "catch_Mankey"
    assert "fallback" in rationale


def test_llm_exception_falls_back(monkeypatch):
    def boom(state, objectives, config):
        raise ConnectionError("ollama is down")

    monkeypatch.setattr(llm_planner, "_call_ollama", boom)
    choice, rationale = llm_planner.choose_objective({}, OBJECTIVES, ENABLED)
    assert choice == "catch_Mankey"
    assert "fallback" in rationale


RECOVERY = ["defer", "heal_then_retry", "retry"]


def test_failure_boundary_valid_choice_is_used(monkeypatch):
    _with_response(monkeypatch, '{"objective": "heal_then_retry", "rationale": "party is at 12% HP"}')
    action, rationale = llm_planner.consult_on_failure("catch_Abra", "No path", {}, RECOVERY, ENABLED)
    assert action == "heal_then_retry"


def test_failure_boundary_garbage_defers(monkeypatch):
    _with_response(monkeypatch, '{"objective": "fly_to_indigo_plateau"}')
    action, rationale = llm_planner.consult_on_failure("catch_Abra", "No path", {}, RECOVERY, ENABLED)
    assert action == "defer"
    assert "fallback" in rationale


def test_failure_boundary_disabled_defers():
    action, rationale = llm_planner.consult_on_failure(
        "catch_Abra", "No path", {}, RECOVERY, dict(llm_planner.DEFAULT_CONFIG)
    )
    assert action == "defer"


def test_failure_context_reaches_the_model(monkeypatch):
    seen = {}

    def spy(state, objectives, config):
        seen.update(state)
        return '{"objective": "retry", "rationale": ""}'

    monkeypatch.setattr(llm_planner, "_call_ollama", spy)
    llm_planner.consult_on_failure("catch_Abra", "No path to (3,42)", {"money": 981}, RECOVERY, ENABLED)
    assert seen["failed_skill"] == "catch_Abra"
    assert seen["error"] == "No path to (3,42)"
    assert seen["money"] == 981
