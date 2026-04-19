export const DEFAULT_AGENT_MODEL = "deepseek/deepseek-v3.2";

// 前端“可选模型”仅用于展示与头像；后端真实请求会固定走 DeepSeek。
// 这里的字符串刻意包含厂商关键字，方便用现有头像规则匹配。
export const FALLBACK_MODELS = [
  "anthropic/claude-opus-4.7",
  "openai/gpt-5.4",
  "google/gemini-3.1-pro",
  "qwen/qwen-3.6-plus",
  "z-ai/glm-5.1",
  "minimax/minimax-2.7",
  "moonshot/kimi-k-2.6",
  "bytedance/seed-2.0-pro",
  DEFAULT_AGENT_MODEL,
];
