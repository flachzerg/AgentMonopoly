from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "agent_options.placeholder.json"
LOCAL_CONFIG_PATH = ROOT / "config" / "agent_options.local.json"
LEGACY_LOCAL_CONFIG_PATHS: tuple[Path, ...] = (
    ROOT / "config" / "deepseek_agent_config.json",
)
# “显示模型”用于前端下拉与头像；“真实模型”用于后端实际请求。
# 默认使用 DeepSeek，方便在国内网络环境直接跑通。
DEFAULT_AGENT_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_ACTUAL_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 产品 demo：前端可选九个“最新型号”，但真实调用固定 DeepSeek。
DEMO_MODEL_OPTIONS: list[str] = [
    "anthropic/claude-opus-4.7",
    "openai/gpt-5.4",
    "google/gemini-3.1-pro",
    "qwen/qwen-3.6-plus",
    "z-ai/glm-5.1",
    "minimax/minimax-2.7",
    "moonshot/kimi-k-2.6",
    "bytedance/seed-2.0-pro",
    "deepseek/deepseek-v3.2",
]


class AgentOptions(BaseModel):
    provider: str = "openai-compatible"
    # DeepSeek OpenAI-compatible base url（可被 agent_options.local.json 覆盖）
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    api_key: str = ""
    default_timeout_sec: float = 8
    default_max_retries: int = 2
    models_checked_at: str = "2026-04-18"
    default_model: str = DEFAULT_AGENT_MODEL
    # 后端真正发送给模型服务的 model id（忽略前端选择）
    actual_model: str = DEFAULT_ACTUAL_MODEL
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
    return AgentOptions(
        default_model=DEFAULT_AGENT_MODEL,
        actual_model=DEFAULT_ACTUAL_MODEL,
        model_options=[DEFAULT_AGENT_MODEL],
    )


def load_agent_options() -> AgentOptions:
    env_path = os.getenv("AGENT_OPTIONS_FILE", "").strip()
    if env_path:
        raw = Path(env_path).expanduser()
        cfg_path = raw if raw.is_absolute() else (ROOT.parent / raw).resolve()
    else:
        if LOCAL_CONFIG_PATH.exists():
            cfg_path = LOCAL_CONFIG_PATH
        else:
            cfg_path = next((item for item in LEGACY_LOCAL_CONFIG_PATHS if item.exists()), DEFAULT_CONFIG_PATH)
    if not cfg_path.exists():
        return _fallback_options()

    try:
        payload: dict[str, Any] = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _fallback_options()

    try:
        options = AgentOptions.model_validate(payload)
        allow_external = os.getenv("ALLOW_NON_DEEPSEEK_MODELS", "").strip().lower() in {"1", "true", "yes"}

        if allow_external:
            options.default_model = default_model_name(options)
            options.model_options = _normalize_model_options(options.default_model, options.model_options)
            options.default_model = options.model_options[0]
            if not options.actual_model:
                options.actual_model = DEFAULT_ACTUAL_MODEL
            return options

        # 默认策略：永远只走 DeepSeek 的 base_url + api_key；前端只展示 DEMO_MODEL_OPTIONS
        options.provider = "openai-compatible"
        options.base_url = os.getenv("DEEPSEEK_BASE_URL", "").strip() or DEFAULT_DEEPSEEK_BASE_URL
        env_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        # 优先使用环境变量注入；否则使用配置文件里的 api_key（占位符方案）
        if env_key:
            options.api_key = env_key

        options.actual_model = DEFAULT_ACTUAL_MODEL
        options.default_model = DEFAULT_AGENT_MODEL
        options.model_options = _normalize_model_options(options.default_model, DEMO_MODEL_OPTIONS)
        options.default_model = options.model_options[0]
        return options
    except Exception:
        return _fallback_options()
