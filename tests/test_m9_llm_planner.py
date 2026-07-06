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
