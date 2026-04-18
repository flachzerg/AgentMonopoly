from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "openrouter_agent_config.template.json"
LOCAL_CONFIG_PATH = ROOT / "config" / "openrouter_agent_config.local.json"
DEFAULT_AGENT_MODEL = "deepseek/deepseek-chat-v3.1"


class AgentOptions(BaseModel):
    provider: str = "openai-compatible"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    default_timeout_sec: float = 8
    default_max_retries: int = 2
    models_checked_at: str = "2026-04-18"
    default_model: str = DEFAULT_AGENT_MODEL
    model_options: list[str] = Field(default_factory=list)


def _normalize_model_options(default_model: str, model_options: list[str]) -> list[str]:
    default_name = default_model.strip() or DEFAULT_AGENT_MODEL
    normalized = [item.strip() for item in model_options if item and item.strip()]
    if not normalized:
        return [default_name]
    if default_name not in normalized:
        return [default_name, *normalized]
    if normalized[0] == default_name:
        return normalized
    reordered = [default_name]
    reordered.extend(item for item in normalized if item != default_name)
    return reordered


def default_model_name(options: AgentOptions) -> str:
    name = options.default_model.strip() if options.default_model else ""
    if name:
        return name
    return options.model_options[0] if options.model_options else DEFAULT_AGENT_MODEL


def _fallback_options() -> AgentOptions:
    return AgentOptions(default_model=DEFAULT_AGENT_MODEL, model_options=[DEFAULT_AGENT_MODEL])


def load_agent_options() -> AgentOptions:
    env_path = os.getenv("AGENT_OPTIONS_FILE", "").strip()
    if env_path:
        cfg_path = Path(env_path).expanduser()
    else:
        cfg_path = LOCAL_CONFIG_PATH if LOCAL_CONFIG_PATH.exists() else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return _fallback_options()

    try:
        payload: dict[str, Any] = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _fallback_options()

    try:
        options = AgentOptions.model_validate(payload)
        options.default_model = default_model_name(options)
        options.model_options = _normalize_model_options(options.default_model, options.model_options)
        options.default_model = options.model_options[0]
        return options
    except Exception:
        return _fallback_options()
