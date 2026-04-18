# AgentMonopoly MVP 开发配置与代码脉络

## 1. 目标与范围
- 本文档用于说明当前已初始化的前后端分离工程结构。
- 技术栈与主文档一致：`React + FastAPI + PydanticAI + SQLite`。
- 目标是快速跑通黑客松 MVP：房间/回合状态展示、动作提交、Agent 基础决策接口。

## 2. 当前目录结构

```text
Hackathon/
├─ AgentMonopoly_开发文档.md
├─ backend/
│  ├─ .env.example
│  ├─ requirements.txt
│  └─ app/
│     ├─ __init__.py
│     ├─ main.py
│     ├─ schemas.py
│     ├─ game_engine.py
│     ├─ agent_runtime.py
│     ├─ api/
│     │  ├─ __init__.py
│     │  ├─ health.py
│     │  └─ games.py
│     └─ core/
│        ├─ __init__.py
│        └─ config.py
├─ frontend/
│  ├─ .env.example
│  ├─ package.json
│  ├─ tsconfig.json
│  ├─ vite.config.ts
│  ├─ index.html
│  └─ src/
│     ├─ main.tsx
│     ├─ App.tsx
│     └─ index.css
└─ docs/
   └─ MVP_开发配置与代码脉络.md
```

## 3. 后端说明（backend）

### 3.1 核心文件职责
- `backend/app/main.py`
  - FastAPI 应用入口。
  - CORS 配置。
  - 挂载健康检查和游戏接口路由。
- `backend/app/api/health.py`
  - 健康检查接口：`GET /health`。
- `backend/app/api/games.py`
  - 动作提交接口：`POST /games/{game_id}/actions`。
  - Agent 决策接口：`POST /games/{game_id}/agent/{player_id}/act`。
  - AI 自动推进接口：`POST /games/{game_id}/auto-play`。
- `backend/app/schemas.py`
  - 请求/响应模型定义（Pydantic）。
- `backend/app/game_engine.py`
  - 动作白名单与动作合法性校验。
- `backend/app/agent_runtime.py`
  - Agent 决策最小实现（当前为 fallback，后续接 PydanticAI 实调用）。
- `backend/app/core/config.py`
  - 环境配置读取。

### 3.2 已预留的实现边界
- 规则引擎：先用 `game_engine.py` 累积规则函数。
- Agent 链路：在 `agent_runtime.py` 增加 Prompt 组装、模型调用、结构化输出解析。
- 持久化：后续新增 `models.py` 和 `db.py` 接 SQLite。

## 4. 前端说明（frontend）

### 4.1 核心文件职责
- `frontend/src/main.tsx`
  - React 入口。
- `frontend/src/App.tsx`
  - MVP 首页，含对局信息区和日志区。
  - 使用 Zustand 管理最小状态。
- `frontend/src/index.css`
  - 基础样式（深色主题）。
- `frontend/vite.config.ts`
  - Vite 开发配置。
- `frontend/.env.example`
  - API/WS 地址配置模板。

### 4.2 当前页面能力
- 展示房间号、回合号。
- 本地日志流展示。
- 预留“模拟操作”按钮，后续接后端接口。

## 5. 开发配置

### 5.1 后端环境变量
- 文件：`backend/.env.example`
- 字段：
  - `APP_ENV`
  - `BACKEND_HOST`
  - `BACKEND_PORT`
  - `ALLOWED_ORIGINS`
  - `MODEL_BASE_URL`
  - `MODEL_API_KEY`
  - `MODEL_NAME`

### 5.2 前端环境变量
- 文件：`frontend/.env.example`
- 字段：
  - `VITE_API_BASE_URL`
  - `VITE_WS_BASE_URL`

## 6. 启动步骤

### 6.1 启动后端
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6.2 启动前端
```bash
cd frontend
npm install
npm run dev
```

### 6.3 快速验证
- 访问 `http://localhost:8000/health`，应返回 `{"status":"ok"}`。
- 打开前端页面（默认 `http://localhost:5173`），应看到 MVP 面板和日志区。

## 7. 下一步开发顺序（建议）
- 第一步：前端接通 `POST /games/{game_id}/actions`，完成真实动作提交。
- 第二步：后端加入 WebSocket 房间广播（回合事件推送）。
- 第三步：补 `SQLite` 持久化（玩家、地块、游戏快照、事件日志）。
- 第四步：将 `agent_runtime.py` 从 fallback 升级为 `PydanticAI` 实际调用。
- 第五步：加入最小回放接口，支持按回合拉取日志。

## 8. 注意事项
- 黑客松阶段优先“跑通闭环”，不要提前引入 Redis、队列、复杂部署。
- 所有 Agent 动作必须经过白名单校验，避免非法输出破坏游戏流程。
- 回合状态结构尽早固定（字段命名稳定），避免前后端反复改协议。
