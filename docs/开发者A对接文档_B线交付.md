# 开发者A对接文档（B线交付）

更新时间：2026-04-18
仓库：`AgentMonopoly`
分支建议：`codex/phase-b-full-delivery`

## 1. 目标与边界

本文用于让开发者 A 直接对接 B 线代码。

本次交付已完成：
- Agent Runtime 真链路（输入构建、输出解析、失败降级、审计）
- Prompt 模板体系（8 类模板、版本、变更记录、A/B 路由）
- 前端对局主界面（HTTP + WebSocket、断线重连、状态同步）
- replay 与策略分析面板（单步、跳转、候选 vs 最终、导出）
- 批量评测与模板版本对比脚本

本次未做：
- DB 持久化（当前为内存态）
- QUIZ 完整玩法链路（仅保留模板位与事件占位）

## 2. 协议固定项

- 输入协议：`DY-MONO-TURN-IN/3.1`
- 输出协议：`DY-MONO-TURN-OUT/3.1`
- 回合主链：`ROLL -> TILE_ENTER -> AUTO_SETTLE -> DECISION -> EXECUTE -> LOG`
- AI 输出强制 `json_only`
- 输出模型 `extra=forbid`，拒绝额外字段

核心模型位于：`backend/app/schemas.py`

## 3. HTTP 接口合同

实现文件：`backend/app/api/games.py`

### 3.1 创建与查询

- `POST /games`
  - 请求：`CreateGameRequest`
  - 回包：`{ game_id, state }`
- `GET /games`
  - 回包：`{ games: string[] }`
- `GET /games/{game_id}/state`
  - 回包：`{ state: GameState }`

### 3.2 动作执行

- `POST /games/{game_id}/actions`
  - 请求：`ActionRequest`
  - 回包：`ActionResponse`
  - 规则：动作与参数必须在服务端 `allowed_actions` 白名单内

### 3.3 Agent 决策

- `POST /games/{game_id}/agent/{player_id}/act`
  - 回包：`ActionResponse`
  - `audit` 字段包含：
    - `model_tag`
    - `template_key` / `template_version`
    - `prompt_hash`
    - `attempt_count`
    - `failure_codes`
    - `final_decision`

### 3.4 replay 与摘要

- `GET /games/{game_id}/replay`
  - 回包：`ReplayResponse`
  - 包含：`candidate_actions`、`final_action`、`strategy_tags`、`phase_trace`
- `GET /games/{game_id}/summary`
  - 回包：`ReplayExport`
  - `metrics` 含：`fallback_ratio`、`illegal_action_rate`、`avg_net_worth` 等

## 4. WebSocket 合同

接口：`/games/{game_id}/ws`

客户端上行：
- `{"type":"ping"}`
- `{"type":"sync_request"}`

服务端下行：
- `{"type":"state.sync","state":...,"event":...,"audit":...}`
- `{"type":"game.started","state":...}`
- `{"type":"pong"}`
- `{"type":"error","message":"..."}`

前端已做：
- 自动重连（指数退避）
- 重连后自动发 `sync_request`
- 以服务端 `state` 与 `event` 作为唯一真值

## 5. Agent Runtime 对接点

实现文件：`backend/app/agent_runtime.py`

### 5.1 输入构建

`build_turn_input` 会拼装：
- `turn_meta`
- `tile_context`
- `player_state`
- `players_snapshot`
- `board_snapshot`
- `options`
- `output_contract`
- `template_key` / `template_version`
- `memory_summary`

### 5.2 输出解析

`parse_turn_output` 强制：
- `protocol == DY-MONO-TURN-OUT/3.1`
- `action` 必在 `options` 内
- `required_args` 必填
- `allowed_values` 必匹配
- 额外字段直接判错

### 5.3 失败治理

失败码写入 `failure_codes`：
- `timeout`
- `parse_error`
- `illegal_action`
- `runtime_error:*`

所有失败都可降级到 `fallback_decision`，保证流程稳定。

## 6. Prompt 模板与版本路由

模板目录：`backend/app/prompts/`

已含 8 类模板：
- `PROPERTY_UNOWNED_TEMPLATE`
- `PROPERTY_SELF_TEMPLATE`
- `PROPERTY_ALLY_TEMPLATE`
- `PROPERTY_OTHER_TEMPLATE`
- `BANK_TEMPLATE`
- `EVENT_TEMPLATE`
- `EMPTY_TEMPLATE`
- `QUIZ_TEMPLATE`（占位）

路由文件：`backend/app/prompts/router.py`
- 支持覆盖版本（override）
- 支持稳定 hash 分流 A/B

变更记录：`backend/app/prompts/CHANGELOG.md`

## 7. 评测脚本与结果

### 7.1 批量对局评测

脚本：`backend/scripts/batch_eval.py`

指标：
- `win_rate`
- `avg_total_assets`
- `bankrupt_rate`
- `illegal_action_rate`
- `fallback_rate`

输出：
- `backend/reports/batch_eval.json`
- `backend/reports/batch_eval.md`

### 7.2 模板版本对比

脚本：`backend/scripts/template_ab_report.py`

输出：
- `backend/reports/template_versions_report.json`
- `backend/reports/template_versions_report.md`

## 8. 前端模块结构

新增目录：
- `frontend/src/types/`
- `frontend/src/services/`
- `frontend/src/store/`
- `frontend/src/components/`
- `frontend/src/pages/`

关键点：
- `services/api.ts`：HTTP client
- `services/ws.ts`：WebSocket client（自动重连）
- `store/gameStore.ts`：按 `game_id` 管理状态
- `components/ReplayPanel.tsx`：单步、跳转、导出

## 9. 本地联调命令

后端：
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：
```bash
cd frontend
npm install
npm run dev
```

测试：
```bash
cd /path/to/AgentMonopoly
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
cd frontend
npm run test
npm run build
```

## 10. A 侧对接清单

建议 A 按以下顺序接入：
1. 先以 `schemas.py` 作为统一字段源，避免多处重复定义。
2. 若 A 线引入 DB，优先对齐 `GameState`、`ReplayStep`、`DecisionAudit` 三类结构。
3. 若 A 线扩展规则引擎，确保 `allowed_actions` 依旧作为唯一动作入口。
4. 若 A 线新增事件类型，前端时间线可直接透传，无需改合同。
5. QUIZ 完整链路落地时，沿用 `QUIZ_TEMPLATE` 与 `quiz.placeholder` 事件位。

## 11. 风险与下一步

当前风险：
- 内存态数据在进程重启后会丢失。
- 目前评测模型默认 `heuristic`，真实模型效果依赖环境变量配置。

下一步建议：
- A 线补 DB 持久化与 replay 存档。
- 接入真实模型后，持续跑 `batch_eval.py` 与 `template_ab_report.py` 做量化迭代。
