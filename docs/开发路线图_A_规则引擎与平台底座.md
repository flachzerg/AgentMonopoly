# 开发路线图 A（规则引擎 + 平台底座）

适用对象：开发者 A  
主责范围：后端规则引擎、状态机、数据层、实时事件、平台级质量与可观测

---

## 0. 统一口径（必须先看）

你后续全部开发，以以下三类资料为同一基线：

1. `AI大富翁_整合版_产品与AI开发路线图.md`
2. `AgentMonopoly/AgentMonopoly_开发文档.md`
3. `AgentMonopoly/docs/MVP_开发配置与代码脉络.md`

统一规则如下：

- 规则执行与 AI 决策完全分离：系统执行业务，AI 仅给参数。
- 回合主链固定：`ROLL -> TILE_ENTER -> AUTO_SETTLE -> DECISION -> EXECUTE -> LOG`。
- 协议主版本固定：`DY-MONO-TURN-IN/3.1` 与 `DY-MONO-TURN-OUT/3.1`。
- MVP 阶段先完成 `START/EMPTY/BANK/EVENT/PROPERTY`，`QUIZ` 在 Phase 6 接入。
- 所有动作都过白名单与参数校验，非法参数统一走 fallback。
- 每回合必须写结构化事件日志 + 状态快照，支持 replay。

若发现新需求与三类文档不一致，以本文件的“冲突处理表”为准，并同步在 `docs/` 新增 ADR 记录。

---

## 1. 你的系统 owner 边界

你直接 owner 的目录与文件：

- `AgentMonopoly/backend/app/game_engine.py`
- `AgentMonopoly/backend/app/schemas.py`
- `AgentMonopoly/backend/app/api/games.py`
- `AgentMonopoly/backend/app/main.py`
- `AgentMonopoly/backend/app/core/config.py`
- 新增：`AgentMonopoly/backend/app/models.py`
- 新增：`AgentMonopoly/backend/app/db.py`
- 新增：`AgentMonopoly/backend/app/replay_service.py`
- 新增：`AgentMonopoly/backend/app/ws_manager.py`
- 新增：`AgentMonopoly/backend/tests/**`
- 新增：`AgentMonopoly/backend/alembic/**`（或你选定的迁移方案）

你无需 owner 的内容：

- `agent_runtime.py` 里的模型编排细节
- `frontend/src/**` UI 与交互

你要给 B 提供：

- 稳定 API 合同
- 稳定 WebSocket event schema
- 稳定 replay 数据结构

---

## 2. 冲突处理表（三类文档统一）

1. 关于 `QUIZ`
- 统一结论：MVP 主线先不阻塞在 `QUIZ`；先跑通主玩法。
- 你的动作：代码层预留 `QUIZ` tile type 与 handler stub，接口字段一次定好。

2. 关于“动作一步还是多步”
- 统一结论：同一回合允许多动作，但必须由状态机控制 phase gate。
- 你的动作：在引擎里限制 phase 可执行动作集，不允许跨 phase 动作。

3. 关于“银行/事件是否自动”
- 统一结论：自动项在 `AUTO_SETTLE`，可选项在 `DECISION`。
- 你的动作：每个 tile 逻辑拆成 `auto_effects()` 与 `decision_options()`。

4. 关于“破产流程触发点”
- 统一结论：强制扣款后立刻进行 insolvent 检查。
- 你的动作：`AUTO_SETTLE` 末尾进入 `INSOLVENCY_CHECK` 子流程。

---

## 3. Phase 路线（大任务版本）

## Phase A1：协议与状态机固化（高优先）

目标：形成平台级硬约束，后续开发全部依赖这层。

任务：

1. 在 `schemas.py` 固化以下模型：
- `TurnInputV31`
- `TurnOutputV31`
- `DecisionOptions`
- `OutputContract`
- `GameSnapshot`
- `EventEnvelope`

2. 固化动作枚举与参数模型：
- `roll_dice`
- `buy_property`
- `upgrade_property`
- `bank_deposit`
- `bank_withdraw`
- `event_choice`
- `propose_alliance`
- `accept_alliance`
- `reject_alliance`
- `pass`

3. 落地状态机：
- phase enum
- transition table
- illegal transition error code

4. 实现回合执行器：
- `run_turn(game_id, player_id)`
- 内部调用 phase handlers

完成标准：

- API + 内部逻辑都使用同一套 schema。
- 任意非法动作均可定位到明确错误码。
- 状态机可跑通 4 人 50 回合本地模拟。

---

## Phase A2：规则引擎全量主线

目标：主玩法一次跑通，不依赖 AI 也能完整完成一局。

任务：

1. `START`：起点奖励可配置。
2. `EMPTY`：无经济变更，允许社交动作挂载。
3. `BANK`：deposit/withdraw 额度与边界校验。
4. `EVENT`：自动型 + 选项型统一抽象。
5. `PROPERTY`：
- 无主：buy/skip
- 自有：upgrade/skip
- 盟友：免 toll
- 他人：自动扣 toll + insolvent check

6. 联盟规则：
- 每人最多 1 个盟友
- 双向确认
- 互免 toll
- 冷却回合配置

7. 破产与拍卖：
- cash 不足 -> deposit 扣减 -> 资产拍卖 -> 出局判断
- 拍卖流程可重复回合推进

完成标准：

- 本地 deterministic 测试覆盖全部 tile subtypes。
- 破产流程有完整 event trail。
- 规则测试覆盖率 >= 90%（engine 模块）。

---

## Phase A3：数据层与 replay

目标：每局对战可完整回放与审计。

任务：

1. 新增 SQLModel 实体：
- `Game`
- `Player`
- `Property`
- `Alliance`
- `Action`
- `EventLog`
- `GameSnapshot`

2. 设计索引：
- `(game_id, round_index)`
- `(game_id, ts)`
- `(game_id, player_id, round_index)`

3. replay 服务：
- `GET /games/{game_id}/replay`
- 支持按 round 范围查询
- 支持按 event_type 过滤

4. 批量模拟数据导出：
- 产出 JSONL，便于 B 做策略评测。

完成标准：

- 200 回合对局 replay 查询耗时可控。
- 日志、快照、动作三者可以互相关联。

---

## Phase A4：实时事件与平台质量

目标：前端可实时观战，系统可定位问题。

任务：

1. WebSocket 事件总线：
- `game.started`
- `turn.started`
- `dice.rolled`
- `player.moved`
- `action.accepted`
- `action.rejected`
- `settlement.applied`
- `player.bankrupt`
- `game.finished`

2. 统一 event envelope：
- `event_id`
- `game_id`
- `round_index`
- `turn_id`
- `ts`
- `payload`

3. 可观测：
- 结构化日志（JSON）
- 指标：phase latency、action reject rate、fallback rate、ws push latency
- trace_id 串联 API 与引擎

4. 稳定性：
- 幂等保护
- 并发下 phase 锁
- 断线重连后的事件补发

完成标准：

- 4 客户端并发观战稳定。
- 可通过 trace_id 快速定位单回合异常。

---

## Phase A5：测试、压测、CI 门禁

目标：后端变更具备工程级安全网。

任务：

1. 测试矩阵：
- 单测：规则函数
- 集成：API + DB
- 合同：schema snapshot
- 并发：多局并行

2. 压测：
- 目标：100 局并行模拟
- 指标：p95 延迟、错误率、DB 写入耗时

3. CI：
- `ruff`/`mypy`/`pytest`/合同测试
- 任何失败禁止 merge

完成标准：

- 主分支持续稳定可发布。

---

## 4. 与开发者 B 的协作接口

你必须先交付给 B 的内容：

1. API 合同文档：
- `POST /games/action`
- `GET /games/{id}/state`
- `GET /games/{id}/replay`
- `POST /games/{id}/agent/act`（由 B 消费）

2. WebSocket 合同文档：
- 事件名
- payload schema
- 错误事件格式

3. 错误码规范：
- phase 错误
- 参数错误
- 余额错误
- 资源不存在

4. 本地 mock 数据：
- 至少 3 局完整 replay 样本

---

## 5. 你的 DoD（Done Definition）

以下条件全满足，才算你这条线完成：

1. 引擎可独立跑完整局，且结果可复现。
2. API/WS 合同稳定，B 无需反复适配字段。
3. replay 可用于前端播放与策略分析。
4. 规则、合同、并发测试全绿。
5. 关键指标可观测，异常可快速定位。

---

## 6. 你要优先开的 GitHub Issues（建议）

1. `ENGINE-001` 状态机与 phase gate 实现
2. `ENGINE-002` 全 tile subtype 规则落地
3. `ENGINE-003` 破产与拍卖流程
4. `DATA-001` SQLModel 实体与迁移
5. `DATA-002` replay 查询与导出
6. `RT-001` WebSocket event bus 与补发
7. `OBS-001` tracing + metrics + structured log
8. `QA-001` 测试矩阵与压测脚本

