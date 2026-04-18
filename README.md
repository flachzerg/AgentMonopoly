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
- Agent 上下文管理系统已重构：每回合统一构建 `agent_context`（`static_map` / `dynamic_state` / `recent_actions_3turns` / `memory_context`）并通过 `state.sync` 下发前端，支持在决策面板折叠查看。

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
      agent_options.template.json          # 统一模板（可提交）
      agent_options.local.json             # 本地私有配置（git ignore）
  frontend/                    # React 前端
  docs/                        # PRD / Roadmap / 开发文档
```

## 依赖与环境配置

### 1) 前置依赖

- Git
- Node.js 20+
- npm 10+
- Python 3.13+（建议）

### 2) Clone 项目

```bash
git clone https://github.com/flachzerg/AgentMonopoly.git
cd AgentMonopoly
```

### 3) 统一虚拟环境（推荐）

推荐统一使用项目根目录的 `.venv-Hackathon`，避免 README 和命令示例出现多套环境名。

Windows（PowerShell）：

```powershell
python -m venv .venv-Hackathon
.\.venv-Hackathon\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
```

macOS/Linux（bash/zsh）：

```bash
python3 -m venv .venv-Hackathon
./.venv-Hackathon/bin/python -m pip install -r backend/requirements-dev.txt
```

如果你已在 `backend/.venv` 有历史环境，可继续使用，但后续文档命令默认以 `.venv-Hackathon` 为准。

### 4) 前端依赖安装

```bash
cd frontend
npm install
cd ..
```

### 5) Agent 配置模板与本地配置

> 前端页面不录入 API Key；密钥与 base_url 由后端配置文件读取。

```bash
cd backend
cp config/agent_options.template.json config/agent_options.local.json
# 可选：准备多份本地私有配置用于切换
cp config/agent_options.template.json config/agent_options.openrouter.local.json
cp config/agent_options.template.json config/agent_options.deepseek.local.json
cd ..
```

默认模板文件：`backend/config/agent_options.template.json`（可提交到 GitHub）  
本地文件：`backend/config/*.local.json`（已 `.gitignore`）

### 6) Provider 切换（相对路径，跨电脑可用）

项目通过 `AGENT_OPTIONS_FILE` 指定后端读取的配置文件。  
未显式指定时，默认优先级：

1. `backend/config/agent_options.local.json`
2. `backend/config/deepseek_agent_config.json`（兼容历史命名）
3. `backend/config/openrouter_agent_config.local.json`（兼容历史命名）
4. `backend/config/agent_options.template.json`

Windows（PowerShell）：

```powershell
# OpenRouter
$env:AGENT_OPTIONS_FILE = "backend/config/agent_options.openrouter.local.json"

# DeepSeek
$env:AGENT_OPTIONS_FILE = "backend/config/agent_options.deepseek.local.json"
```

bash/zsh：

```bash
export AGENT_OPTIONS_FILE=backend/config/agent_options.openrouter.local.json
```

## 启动与自检

### 1) 一键重启（推荐）

脚本会先清理旧进程（端口占用 + 残留 `uvicorn/vite` 进程），再启动新服务，避免“看起来配置没生效”。

```bash
# macOS / Linux / Git Bash
bash scripts/dev_restart.sh restart

# 手动指定配置文件
AGENT_OPTIONS_FILE=backend/config/agent_options.openrouter.local.json bash scripts/dev_restart.sh restart
```

```powershell
# Windows PowerShell
.\scripts\dev_restart.ps1 restart

# 手动指定配置文件（相对路径）
$env:AGENT_OPTIONS_FILE = "backend/config/agent_options.deepseek.local.json"
.\scripts\dev_restart.ps1 restart
```

### 2) 手动启动后端

Windows（PowerShell）：

```powershell
cd backend
..\.venv-Hackathon\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

macOS/Linux（bash/zsh）：

```bash
cd backend
../.venv-Hackathon/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3) 手动启动前端（新终端）

```bash
cd frontend
npx vite --host 0.0.0.0 --port 5173
```

### 4) 自检

- 后端健康检查：[http://localhost:8000/health](http://localhost:8000/health)
- 地图选项接口：[http://localhost:8000/games/map-options](http://localhost:8000/games/map-options)
- 当前 Agent 配置：[http://localhost:8000/games/agent-options](http://localhost:8000/games/agent-options)
- 前端页面：[http://localhost:5173](http://localhost:5173)

## 快速体验路径

1. 进入 `/` 配置页
2. 填写房间名、人数、回合上限
3. 为每个席位选择 `真人` 或 `AI`，AI 席位选择模型
4. 点击“开始对局”进入 `/game/:gameId`
5. 对局完成后进入 `/replay/:gameId` 查看全局复盘

## Agent 上下文管理系统（重构后）

### 决策链路

1. `games.py` 在回合开始调用 `context_builder.py` 统一构建上下文
2. `agent_runtime.py` 渲染 prompt 并调用模型（保留 `## Turn Input JSON` 机器可读块）
3. `game_engine.py` 校验动作合法性并推进状态
4. WebSocket `state.sync` 广播 `agent_context` + `audit` 到前端

### 上下文结构

- `static_map`：棋盘拓扑与边（跨回合稳定）
- `dynamic_state`：当前回合快照（含前方分支路径和风险提示）
- `recent_actions_3turns`：最近三回合结构化动作 + thought
- `memory_context`：短期/长期记忆摘要
- `options`：动作白名单与参数约束（最终执行裁决基线）

### 前端可视化

- 对局页 `DecisionCenter` 的折叠区可查看完整 `agent_context` 包，用于调试与回放分析。

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
../.venv-Hackathon/bin/python -m pytest
../.venv-Hackathon/bin/python -m ruff check .
../.venv-Hackathon/bin/python -m mypy app
```

Windows（PowerShell）：

```powershell
cd backend
..\.venv-Hackathon\Scripts\python.exe -m pytest
..\.venv-Hackathon\Scripts\python.exe -m ruff check .
..\.venv-Hackathon\Scripts\python.exe -m mypy app
```

历史环境 `.venv` 兼容写法：

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

- 确认 `backend/config/agent_options.local.json`（或你指定的本地配置）内 `api_key` 有效
- 确认 `base_url` 为 `https://openrouter.ai/api/v1`
- 若你在切换 Provider，确认 `AGENT_OPTIONS_FILE` 指向了期望的配置文件
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
