# AgentMonopoly

一个无需注册、无需登录、点开就能玩的 AI Monopoly Web 应用。  
目标体验：用户进入网站后，先完成对局配置，再进入实时对局页，结局后直接进入复盘页查看全局分析。

## 产品能力概览

- 三段式体验流程：
  - 配置页：房间名、人数、玩家操控方式（Human / AI）、AI 模型选择
  - 对局页：上方全局状态、左侧地图、右侧日志与 Agent 流式输出、底部动作区
  - 复盘页：对局日志回放、摘要生成、导出复盘
- 后端单轨 `v2` 架构（legacy 路径已移除）
- AI Provider 已默认接到 OpenRouter（后端读取本地配置文件）
- 前端无需展示 API Key / base URL，用户仅需选择模型
- 支持 AI 单步决策与自动推进

## 技术栈

- Frontend: React + TypeScript + Vite + Zustand + React Router
- Backend: FastAPI + Pydantic + WebSocket
- AI Runtime: openai-compatible 接口（默认 OpenRouter）

## 目录结构

```text
AgentMonopoly/
  backend/                     # FastAPI 服务
    app/
    config/
      openrouter_agent_config.template.json
      openrouter_agent_config.local.json   # 本地私有配置（git ignore）
  frontend/                    # React 前端
  docs/                        # PRD / Roadmap / 开发文档
```

## 前置依赖

- Git
- Node.js 20+
- npm 10+
- Python 3.13+（建议）

## 1 分钟本地启动

### 1) clone 项目

```bash
git clone https://github.com/flachzerg/AgentMonopoly.git
cd AgentMonopoly
```

### 2) 后端依赖安装

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

### 3) 配置 OpenRouter（本地文件）

> 前端页面不录入 API Key；密钥与 base_url 在后端本地配置文件里。

```bash
mkdir -p config
cp config/openrouter_agent_config.template.json config/openrouter_agent_config.local.json
```

编辑 `backend/config/openrouter_agent_config.local.json`：

```json
{
  "provider": "openai-compatible",
  "base_url": "https://openrouter.ai/api/v1",
  "api_key": "YOUR_OPENROUTER_KEY",
  "default_timeout_sec": 8,
  "default_max_retries": 2,
  "models_checked_at": "2026-04-18",
  "model_options": [
    "qwen/qwen-plus-2025-07-28",
    "qwen/qwen3-max",
    "qwen/qwen3-235b-a22b-2507",
    "qwen/qwen3-coder-plus",
    "deepseek/deepseek-chat-v3.1",
    "deepseek/deepseek-v3.2",
    "moonshotai/kimi-k2-0905",
    "z-ai/glm-5.1",
    "minimax/minimax-m2.7",
    "deepseek/deepseek-r1"
  ]
}
```

### 4) 启动后端

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端健康检查：

- [http://localhost:8000/health](http://localhost:8000/health)

### 5) 启动前端（新终端）

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

打开：

- [http://localhost:5173](http://localhost:5173)

## 快速体验路径

1. 进入 `/` 配置页
2. 填写房间名、人数、回合上限
3. 为每个席位选择 `真人` 或 `AI`，AI 席位选择模型
4. 点击“开始对局”进入 `/game/:gameId`
5. 对局完成后进入 `/replay/:gameId` 查看全局复盘

## 常用命令

### 前端

```bash
cd frontend
npm run test
npm run build
```

### 后端

```bash
cd backend
source .venv/bin/activate
pytest
ruff check .
mypy app
```

## 常见问题

### Q1: 页面提示 `ERR_CONNECTION_REFUSED`

A:

- 确认后端在 `8000` 端口运行
- 确认前端在 `5173` 端口运行
- 确认前端环境变量 `VITE_API_BASE_URL` 没有指向错误地址

### Q2: 配置页可以看到模型，但 AI 不行动

A:

- 确认 `backend/config/openrouter_agent_config.local.json` 内 `api_key` 有效
- 确认 `base_url` 为 `https://openrouter.ai/api/v1`
- 查看后端日志是否出现模型调用超时或鉴权失败

### Q3: 我只想体验本地规则，不走远端模型

A:

- 在 `.env` 中把 `MODEL_PROVIDER` 设为 `heuristic`
- 重启后端

## 文档入口

- 产品需求：[docs/PRD_OpenPlay_v2.md](docs/PRD_OpenPlay_v2.md)
- 开发路线：[docs/Roadmap_OpenPlay_v2.md](docs/Roadmap_OpenPlay_v2.md)
- 代码脉络：[docs/MVP_开发配置与代码脉络.md](docs/MVP_开发配置与代码脉络.md)

## License

[MIT](LICENSE)
