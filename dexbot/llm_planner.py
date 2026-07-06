"""M9: optional LLM planner — local Ollama via its OpenAI-compatible API.

Strictly additive on top of the deterministic planner: it receives structured
JSON state plus the enumerated list of currently-valid objectives and returns
one of them with a rationale. Any response that is not exactly one of the
offered objectives is rejected and the deterministic queue head is used.

The LLM is never a source of game facts and is only consulted at objective
boundaries. Disabled by default (config.json: llm_planner.enabled).
"""

import json
import urllib.request

from dexbot import PROJECT_ROOT

DEFAULT_CONFIG = {
    "enabled": False,
    "base_url": "http://localhost:11434/v1",
    "model": "qwen2.5:7b",
    "timeout_seconds": 20,
}


def load_config() -> dict:
    path = PROJECT_ROOT / "config.json"
    if path.exists():
        return {**DEFAULT_CONFIG, **json.loads(path.read_text()).get("llm_planner", {})}
    return dict(DEFAULT_CONFIG)


def _call_ollama(state: dict, objectives: list[str], config: dict) -> str:
    """Returns the raw text content of the model response. Split out for test injection."""
    prompt = (
        "You are picking the next objective for a Pokémon FireRed living-dex bot.\n"
        f"Current state:\n{json.dumps(state, indent=1)}\n\n"
        "Valid objectives (you MUST answer with exactly one of these strings, "
        'as JSON: {"objective": "...", "rationale": "..."}):\n'
        + "\n".join(f"- {objective}" for objective in objectives)
    )
    request = urllib.request.Request(
        config["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(
            {
                "model": config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=config["timeout_seconds"]) as response:
        body = json.load(response)
    return body["choices"][0]["message"]["content"]


def choose_objective(state: dict, objectives: list[str], config: dict | None = None) -> tuple[str, str]:
    """Pick the next objective. Always returns a member of `objectives`."""
    if not objectives:
        raise ValueError("No objectives to choose from")
    if config is None:
        config = load_config()
    fallback = objectives[0]

    if not config.get("enabled"):
        return fallback, "deterministic queue (LLM planner disabled)"

    try:
        raw = _call_ollama(state, objectives, config)
        parsed = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        choice = parsed.get("objective")
        if choice in objectives:
            return choice, str(parsed.get("rationale", ""))[:500]
    except Exception as e:  # noqa: BLE001 — any LLM failure must never stop the bot
        return fallback, f"deterministic fallback (LLM error: {type(e).__name__})"
    return fallback, "deterministic fallback (LLM response not in objective list)"
