from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "openrouter_agent_config.template.json"
LOCAL_CONFIG_PATH = ROOT / "config" / "openrouter_agent_config.local.json"


class AgentOptions(BaseModel):
    provider: str = "openai-compatible"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    default_timeout_sec: float = 8
    default_max_retries: int = 2
    models_checked_at: str = "2026-04-18"
    model_options: list[str] = Field(default_factory=list)


def load_agent_options() -> AgentOptions:
    env_path = os.getenv("AGENT_OPTIONS_FILE", "").strip()
    if env_path:
        cfg_path = Path(env_path).expanduser()
    else:
        cfg_path = LOCAL_CONFIG_PATH if LOCAL_CONFIG_PATH.exists() else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return AgentOptions()

    try:
        payload: dict[str, Any] = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return AgentOptions()

    try:
        return AgentOptions.model_validate(payload)
    except Exception:
        return AgentOptions()
