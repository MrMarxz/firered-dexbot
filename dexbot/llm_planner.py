"""L2 LLM reasoning layer — any OpenAI-compatible endpoint (Ollama, Anthropic, ...).

The division of labor is: LLM for reasoning, determinism for execution.
Skills execute frame-perfect without LLM involvement; the LLM is consulted at
BOUNDARIES — objective selection, and failure recovery when determinism has
already failed — receiving structured JSON state plus an enumerated list of
valid choices, returning exactly one with a rationale. A validator rejects
anything not in the list and falls back to the deterministic default, so the
bot remains fully autonomous with the LLM disabled, unreachable, or drunk.

The LLM is never a source of game facts (those come from the ROM/KB); it only
ranks choices the deterministic layer already proved valid.

Config (config.json: llm_planner): `base_url` any OpenAI-compatible /v1;
`api_key_env` names an environment variable holding a bearer token for hosted
endpoints (e.g. ANTHROPIC_API_KEY with base_url https://api.anthropic.com/v1).
Disabled by default.
"""

import json
import os
import urllib.request

from dexbot import PROJECT_ROOT

DEFAULT_CONFIG = {
    "enabled": False,
    "base_url": "http://localhost:11434/v1",
    "model": "qwen2.5:7b",
    "timeout_seconds": 20,
    "api_key_env": "",
}


def load_config() -> dict:
    path = PROJECT_ROOT / "config.json"
    if path.exists():
        return {**DEFAULT_CONFIG, **json.loads(path.read_text()).get("llm_planner", {})}
    return dict(DEFAULT_CONFIG)


def _call_ollama(state: dict, objectives: list[str], config: dict) -> str:
    """Returns the raw text content of the model response. Split out for test injection."""
    task = state.get("task", "picking the next objective for a Pokémon FireRed living-dex bot")
    prompt = (
        f"You are {task}.\n"
        f"Current state:\n{json.dumps(state, indent=1)}\n\n"
        "Valid choices (you MUST answer with exactly one of these strings, "
        'as JSON: {"objective": "...", "rationale": "..."}):\n'
        + "\n".join(f"- {objective}" for objective in objectives)
    )
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get(config.get("api_key_env") or "", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        config["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(
            {
                "model": config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode(),
        headers=headers,
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


def consult_on_failure(
    skill: str, error: str, state: dict, options: list[str], config: dict | None = None
) -> tuple[str, str]:
    """Failure boundary: determinism already failed — let the LLM pick the
    recovery action from `options`. options[0] is the deterministic default
    (what the bot did before this layer existed); the same validator/fallback
    guarantees that disabled/unreachable/garbage always yields it.
    """
    return choose_objective(
        {
            "task": f"choosing a recovery action after the skill {skill!r} failed",
            "failed_skill": skill,
            "error": error,
            **state,
        },
        options,
        config,
    )
