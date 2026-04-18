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
- 已支持 Agent `thought` 伪流式输出（方式 A）：模型先返回完整 JSON，再通过 WebSocket 分片广播 `agent.thought.delta / agent.thought.done`
- Agent 输出合同已强制要求 `thought` 非空，思维群聊默认可稳定展示思考文本（不再以 `raw=...` 作为主展示）
- 对局页已接入 Agent 思维群聊视图：不同 Agent 固定头像 + 聊天气泡流式展示
- 地图生成引擎与数据结构已完成“分支地图”改造：
  - 数据模型：支持通过 `next_tile_ids` 定义任意有向图，兼容原有单环运行逻辑，新增前方分支路径预测。
  - 视觉升级：自适应等分点贝塞尔（Cubic Bezier）平滑连线，正方形 100x100 地块完美居中文字，拥有者状态颜色区分，棋子四角分布。
  - 多样化内置地图：包含大单环、多分支、复杂交叉网络以及专为展示对称曲线之美设计的 `bezier_showcase` 地图。
- 地图链路已全打通：`Setup` 下拉读取后端地图清单，建局请求传入 `map_asset`，后端按地图构建棋盘并在 `state.map_asset` 回传给前端渲染层。

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

如果你已经有项目根目录下的 `.venv-Hackathon`，可直接复用（推荐黑客松阶段）：

```bash
# 项目根目录执行
./.venv-Hackathon/Scripts/python -m pip install -r backend/requirements-dev.txt
```

如果没有现成环境，再新建：

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

Windows + `.venv-Hackathon`（从 `backend` 目录启动）：

```powershell
..\.venv-Hackathon\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端健康检查：

- [http://localhost:8000/health](http://localhost:8000/health)

地图选项接口（供前端配置页读取）：

- [http://localhost:8000/games/map-options](http://localhost:8000/games/map-options)

### 5) 启动前端（新终端）

```bash
cd frontend
npm install
npx vite --host 0.0.0.0 --port 5173
```

打开：

- [http://localhost:5173](http://localhost:5173)

### 6) 启动后 30 秒自检（强烈建议）

```bash
# 后端健康检查
curl http://localhost:8000/health

# 前端主页可访问
curl -I http://localhost:5173/
```

期望结果：
- 后端返回 `{"status":"ok"}`
- 前端返回 `200`

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
- Windows 下从 `backend` 目录启动时，注意 Python 路径应是 `..\.venv-Hackathon\Scripts\python.exe`（不是 `.\.venv-Hackathon\...`）
- 若 `npm run dev -- --host ... --port ...` 未按预期监听端口，直接改用 `npx vite --host 0.0.0.0 --port 5173`

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
- 分支地图改造设计方案：[docs/分支地图改造设计方案.md](docs/分支地图改造设计方案.md)
- 地图生成与视觉设计经验：[docs/地图生成与视觉设计经验沉淀.md](docs/地图生成与视觉设计经验沉淀.md)
- Agent 输入输出协议：[docs/Agent输入输出协议.md](docs/Agent输入输出协议.md)
- Thought 伪流式方案：[docs/Thought伪流式实现方案.md](docs/Thought伪流式实现方案.md)

## License

[MIT](LICENSE)
