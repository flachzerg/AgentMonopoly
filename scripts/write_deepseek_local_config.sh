#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_FILE="$ROOT_DIR/backend/config/agent_options.local.json"

DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com}"
DEEPSEEK_ACTUAL_MODEL="${DEEPSEEK_ACTUAL_MODEL:-deepseek/deepseek-v3.2}"

if [[ -z "${DEEPSEEK_API_KEY// }" ]]; then
  echo "缺少环境变量 DEEPSEEK_API_KEY。"
  echo "用法：DEEPSEEK_API_KEY='sk-xxxx' bash scripts/write_deepseek_local_config.sh"
  exit 1
fi

mkdir -p "$(dirname "$OUT_FILE")"

cat >"$OUT_FILE" <<JSON
{
  "provider": "openai-compatible",
  "base_url": "${DEEPSEEK_BASE_URL}",
  "api_key": "${DEEPSEEK_API_KEY}",
  "default_timeout_sec": 20,
  "default_max_retries": 1,
  "models_checked_at": "2026-04-19",
  "default_model": "deepseek/deepseek-v3.2",
  "actual_model": "${DEEPSEEK_ACTUAL_MODEL}",
  "model_options": [
    "anthropic/claude-opus-4.7",
    "openai/gpt-5.4",
    "google/gemini-3.1-pro",
    "qwen/qwen-3.6-plus",
    "z-ai/glm-5.1",
    "minimax/minimax-2.7",
    "moonshot/kimi-k-2.6",
    "bytedance/seed-2.0-pro",
    "deepseek/deepseek-v3.2"
  ]
}
JSON

echo "已写入：$OUT_FILE"
echo "说明：该文件已在 .gitignore 中，不会被提交。"

