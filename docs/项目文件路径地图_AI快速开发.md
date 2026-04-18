# AgentMonopoly 项目文件路径地图（AI 快速开发版）

本文档目标：让开发者和 AI agent 在**不搜索**的前提下，快速定位“改哪里、看哪里、测哪里”。

## 1. 仓库总览（先记住这 5 层）

```text
AgentMonopoly/
  backend/    # FastAPI + 规则引擎 + 地图引擎 + AI 运行时
  frontend/   # React + Vite + Zustand 前端
  docs/       # 产品/路线图/分工文档/开发指引
  .github/    # CI 流水线
  README.md   # 启动说明与项目入口
```

## 2. 10 分钟上手路径（按顺序打开）

1. `README.md`：启动、依赖、常见问题、文档入口
2. `backend/app/main.py`：后端服务入口与路由挂载
3. `backend/app/api/games.py`：核心 HTTP + WebSocket 接口
4. `backend/app/game_engine.py`：大富翁规则主引擎
5. `frontend/src/App.tsx`：前端路由入口（配置页/对局页/复盘页）
6. `frontend/src/pages/GamePage.tsx`：主对局页编排中心
7. `docs/Agent输入输出协议.md`：Agent 输入输出字段协议
8. `docs/Thought伪流式实现方案.md`：thought 伪流式（方式 A）实现细节

## 3. 后端路径地图（按功能分区）

### 3.1 服务入口与接口层

- `backend/app/main.py`：FastAPI 应用启动点
- `backend/app/api/health.py`：健康检查接口
- `backend/app/api/games.py`：创建对局、推进对局、流式事件等核心接口
- `backend/app/ws_manager.py`：WebSocket 连接管理

### 3.2 规则引擎与数据模型

- `backend/app/game_engine.py`：回合推进、格子结算、胜负流程
- `backend/app/schemas.py`：API 输入输出与结构约束（Pydantic）

### 3.3 地图系统（本项目重点）

- `backend/app/map_engine.py`：地图 JSON 加载、校验、运行时棋盘转换
- `backend/app/map_svg.py`：根据地图 JSON 生成 SVG 底图
- `backend/config/maps/board.01_basic_loop.json`：默认单环地图配置
- `backend/config/maps/board.02_basic_branch.json`：分支地图配置
- `backend/config/maps/board.03_large_loop.json`：大单环地图配置
- `backend/config/maps/board.04_large_branch.json`：大分支地图配置
- `backend/config/maps/board.05_complex_branch.json`：复杂多分支交叉地图配置
- `backend/config/maps/board.06_bezier_showcase.json`：贝塞尔曲线视觉展示专用地图配置
- `backend/scripts/generate_map_svg.py`：批量/单次生成 SVG 的 CLI 脚本
- `scripts/generate_new_maps.py`：用于构建复杂网格分支图配置的坐标规划脚本
- `scripts/generate_bezier.py`：专门构建展现 S 形三次贝塞尔曲线的点对称网络脚本

### 3.4 AI 相关能力

- `backend/app/agent_runtime.py`：AI agent 运行调度
- `backend/app/api/games.py`：Agent 行动触发 + `agent.thought.delta/done` WebSocket 广播
- `backend/app/agent_memory.py`：agent 记忆管理
- `backend/app/agent_eval.py`：评估逻辑
- `backend/app/prompts/router.py`：Prompt 路由
- `backend/app/prompts/templates.py`：Prompt 模板
- `backend/app/core/config.py`：后端配置读取
- `backend/config/openrouter_agent_config.template.json`：OpenRouter 配置模板

### 3.5 后端质量保障

- `backend/tests/test_api_integration.py`：接口集成测试
- `backend/tests/test_game_engine.py`：规则引擎测试
- `backend/tests/test_map_engine.py`：地图引擎加载/校验/fallback 测试
- `backend/tests/test_map_svg.py`：SVG 生成结构测试
- `backend/pyproject.toml`：`pytest`/`ruff`/`mypy` 等工具配置

## 4. 前端路径地图（按页面与数据流）

### 4.1 入口与全局

- `frontend/src/main.tsx`：前端挂载入口
- `frontend/src/App.tsx`：路由主入口
- `frontend/src/index.css`：全局样式基线

### 4.2 页面层（你改页面优先看这里）

- `frontend/src/pages/SetupPage.tsx`：游戏前配置页
- `frontend/src/pages/GamePage.tsx`：对局主页面
- `frontend/src/pages/ReplayPage.tsx`：复盘页面

### 4.3 组件层（按场景拆分）

- `frontend/src/components/BoardGrid.tsx`：棋盘可视区域（当前地图展示核心）
- `frontend/src/components/ActionPanel.tsx`：动作区
- `frontend/src/components/AgentStreamPanel.tsx`：Agent 思维群聊视图（头像 + 聊天气泡 + 流式 thought）
- `frontend/src/components/EventTimeline.tsx`：事件流/时间轴
- `frontend/src/components/ReplayPanel.tsx`：复盘面板
- `frontend/src/components/AssetPanel.tsx`：资产信息
- `frontend/src/components/AlliancePanel.tsx`：联盟信息
- `frontend/src/components/PhaseBadge.tsx`：阶段标签

### 4.4 数据与通信层

- `frontend/src/services/api.ts`：HTTP 请求封装
- `frontend/src/services/ws.ts`：WebSocket 连接封装
- `frontend/src/store/gameStore.ts`：实时对局状态管理（含 thought 增量聚合）
- `frontend/src/store/replayPlayer.ts`：复盘播放器状态
- `frontend/src/types/game.ts`：前端游戏领域类型定义（含 `agent.thought.delta/done`）

### 4.5 静态资源层

- `frontend/public/maps/default.svg`：默认地图 SVG 产物
- `frontend/public/maps/theme2.svg`：主题 2 地图 SVG 产物
- `frontend/public/maps/branch.svg`：分支地图 SVG 产物

## 5. “我要改某个需求”直达文件索引

### 5.1 改“地图规则/格子数据”

1. `backend/config/maps/board.01_basic_loop.json`（或其它地图配置文件）
2. `backend/app/map_engine.py`（校验字段是否通过）
3. `backend/tests/test_map_engine.py`（补充测试）

### 5.2 改“地图视觉样式/布局”

1. `backend/app/map_svg.py`（颜色、轨道线、格子卡片、落点槽位）
2. `backend/scripts/generate_map_svg.py`（重新生成）
3. `frontend/public/maps/*.svg`（确认产物）
4. `frontend/src/components/BoardGrid.tsx`（渲染接入方式）
5. `backend/tests/test_map_svg.py`（补充结构断言）

### 5.3 改“回合逻辑/结算规则”

1. `backend/app/game_engine.py`
2. `backend/app/schemas.py`（若接口字段变动）
3. `backend/tests/test_game_engine.py` + `backend/tests/test_api_integration.py`

### 5.4 改“对局主页面交互”

1. `frontend/src/pages/GamePage.tsx`
2. `frontend/src/components/*`（对应模块）
3. `frontend/src/store/gameStore.ts`
4. `frontend/src/services/api.ts` / `frontend/src/services/ws.ts`

### 5.6 改“Agent thought 流式观战体验”

1. `backend/app/api/games.py`（伪流式切片与 `agent.thought.*` 事件广播）
2. `frontend/src/services/ws.ts`（接收新事件）
3. `frontend/src/store/gameStore.ts`（按 `player_id + turn_index` 聚合增量）
4. `frontend/src/components/AgentStreamPanel.tsx`（群聊气泡渲染）
5. `frontend/src/types/game.ts`（WS 事件字段类型）
6. `docs/Thought伪流式实现方案.md`（协议与开关说明）
7. `docs/地图生成与视觉设计经验沉淀.md`（关于分支地图的美化技巧）

### 5.5 改“配置页或复盘页”

- 配置页：`frontend/src/pages/SetupPage.tsx`
- 复盘页：`frontend/src/pages/ReplayPage.tsx` + `frontend/src/store/replayPlayer.ts`

## 6. 常用命令路径对照

### 6.1 后端

- 工作目录：`backend/`
- 启动：`uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- 测试：`pytest`
- 质量检查：`ruff check .`、`mypy app`

### 6.2 前端

- 工作目录：`frontend/`
- 启动：`npx vite --host 0.0.0.0 --port 5173`
- 测试：`npm run test`
- 构建：`npm run build`

### 6.3 地图生成

- 工作目录：`backend/`
- 命令示例：

```bash
python scripts/generate_map_svg.py --map config/maps/board.01_basic_loop.json --out ../frontend/public/maps/01_basic_loop.svg
python scripts/generate_map_svg.py --map config/maps/board.02_basic_branch.json --out ../frontend/public/maps/02_basic_branch.svg
python scripts/generate_map_svg.py --map config/maps/board.05_complex_branch.json --out ../frontend/public/maps/05_complex_branch.svg
python scripts/generate_map_svg.py --map config/maps/board.06_bezier_showcase.json --out ../frontend/public/maps/06_bezier_showcase.svg
```

## 7. AI Agent 开发建议（减少走弯路）

- 先读：`README.md` + 本文档，再进代码。
- 改后端规则时，优先保证 `backend/tests/test_game_engine.py` 通过。
- 改地图时，同时检查 `map_engine.py`（数据）与 `map_svg.py`（视觉）两层，不要只改一层。
- 页面问题优先从 `pages/*.tsx` 查“状态来源”，再到 `store/` 和 `services/`。
- 每次提交前至少跑一组与改动直接相关的测试，避免跨模块回归。

---

维护约定：新增核心模块后，请同步更新本文档的“直达文件索引”。
