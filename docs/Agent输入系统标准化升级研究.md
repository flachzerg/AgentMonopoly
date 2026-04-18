# Agent 上下文管理系统升级研究（预研稿）

## 1. 目标重述

本方案将原“输入系统”正式重命名为 **Agent 上下文管理系统（Agent Context Management System）**。  
目标是让每个 Agent 在每个回合都按统一模板接收上下文，并保证“可扩展、可审计、可持久化、可回放”。

每回合上下文由七层组成：

- 固定系统提示：大富翁总规则、当前地块规则、输出规范
- 短期记忆摘要：前几步回合经验（每回合更新）
- 长期记忆摘要：上一局总结（持久化，跨局复用）
- 全局状态快照：全图/全员概况
- 局部状态快照：重点前方 6 格，且覆盖所有分支路径
- 自身状态快照：现金、存款、房产、位置、联盟等
- 合法动作合同：严格白名单 + 参数约束

---

## 2. 现状与差距（代码级）

## 2.1 当前已具备

- 协议与输出合同已稳定：`TurnInput` / `AgentTurnOutput` / `DecisionAudit`（`backend/app/schemas.py`）。
- 决策链路闭环：`games.py` -> `agent_runtime.py` -> `game_engine.py` -> WebSocket 广播。
- 动作安全边界已存在：`ActionOption.required_args/allowed_values/default_args` + runtime/engine 双校验。
- 分支偏好与前瞻基础能力已存在：`set_route_preference` 与 `_branch_targets_within_steps(..., lookahead=6)`。
- 提示词模板版本管理已具备：`prompts/templates.py` + `prompts/router.py`。

## 2.2 当前不足

- `agent_memory.py` 仅进程内短期记忆，无法跨局持久化。
- 尚无“上一局总结”存储、读取、压缩与版本化机制。
- 模板渲染是扁平拼接，未形成显式的上下文分层模型。
- 局部视野虽用于动作生成，但没有标准化结构 `dynamic_state.local_horizon_paths`。
- 尚未提供“最近 3 次操作回顾”的稳定字段。

---

## 3. 新上下文模型（核心定义）

## 3.1 `static_map`（静态全局地图，固定）

用途：定义“路怎么连”，供 Agent 理解拓扑与中长期路线价值。

建议内容：

- `map_id`, `topology`, `start_tile_id`
- `tiles[]`: `tile_id`, `tile_type`, `tile_subtype`, `base_price`, `base_toll`
- `edges[]`: `from_tile_id`, `to_tile_id`（从 `next_tile_ids` 展平）

数据来源：

- `game_engine.py` 的棋盘结构 + `map_engine.py` 运行时地图
- 通过统一 builder 只读生成，避免模板层重复推导

字段定义（建议）：

| 字段 | 类型 | 示例 | 含义 |
|---|---|---|---|
| `map_id` | string | `branch18` | 地图唯一标识，来自 map json `meta.map_id` |
| `topology` | string | `graph` | 拓扑类型：`loop` 或 `graph` |
| `track_length` | int | `18` | 地图总地块数 |
| `start_tile_id` | string | `T00` | 起点地块 ID |
| `theme` | string | `city-branch` | 地图主题（仅展示/语义辅助） |
| `version` | string | `1.1.0` | 地图定义版本 |
| `tiles` | array | 见下方示例 | 地块基础信息（静态） |
| `edges` | array | `[{"from":"T03","to":"T04A"}]` | 由 `next_tile_ids` 展平后的有向边 |

`static_map` 示例（来自 `board.02_basic_branch.json` 风格）：

```json
{
  "map_id": "branch18",
  "topology": "graph",
  "track_length": 18,
  "start_tile_id": "T00",
  "theme": "city-branch",
  "version": "1.1.0",
  "tiles": [
    {
      "tile_id": "T03",
      "tile_index": 3,
      "name": "Branch Gate",
      "tile_type": "BANK",
      "tile_subtype": "BANK",
      "property_price": null,
      "toll": null,
      "event_key": null,
      "quiz_key": null,
      "next_tile_ids": ["T04A", "T04B"],
      "render": {"x": 840, "y": 40, "w": 100, "h": 100}
    },
    {
      "tile_id": "T04A",
      "tile_index": 4,
      "name": "Skyline A",
      "tile_type": "PROPERTY",
      "tile_subtype": "PROPERTY",
      "property_price": 260,
      "toll": 52,
      "next_tile_ids": ["T05A"],
      "render": {"x": 840, "y": 200, "w": 100, "h": 100}
    }
  ],
  "edges": [
    {"from_tile_id": "T03", "to_tile_id": "T04A"},
    {"from_tile_id": "T03", "to_tile_id": "T04B"},
    {"from_tile_id": "T04A", "to_tile_id": "T05A"}
  ]
}
```

## 3.2 `dynamic_state`（动态局部快照，每回合更新）

用途：给 Agent 决策时直接可用的实时信息与“逻辑捷径”。

建议至少包含：

- `turn_meta`: round/turn/current_player/current_tile
- `self_state`: 现金、存款、净资产、房产、联盟、位置、当前偏好路线
- `others_state`: 其他玩家位置、资产、联盟、存活状态
- `risk_hints`: 例如“距离最近银行步数”“最近高收费地块步数”等
- `local_horizon_paths`: 重点字段，描述“从当前点出发的所有分叉路径，每条路径最多 6 格”

`local_horizon_paths` 建议结构：

```json
{
  "lookahead_steps": 6,
  "paths": [
    ["tile_08_a", "tile_09", "tile_10", "tile_11", "tile_12", "tile_13"],
    ["tile_08_b", "tile_14", "tile_15", "tile_16", "tile_17", "tile_18"]
  ]
}
```

字段定义（建议）：

| 字段 | 类型 | 示例 | 含义 |
|---|---|---|---|
| `turn_meta` | object | `{"round_index":3,"turn_index":11}` | 当前回合上下文 |
| `self_state` | object | `cash/deposit/property_ids/...` | 当前 Agent 自身状态 |
| `others_state` | array | `[{player_id, position, net_worth}]` | 其他玩家关键信息 |
| `risk_hints` | object | `distance_to_nearest_bank: 2` | 逻辑捷径，减少模型二次推理成本 |
| `local_horizon_paths.lookahead_steps` | int | `6` | 前瞻步数 |
| `local_horizon_paths.paths` | array[array] | `[["T04A","T05A"...],["T04B","T05B"...]]` | 从当前点出发的全部候选路径，每条最多 6 格 |
| `local_horizon_paths.branch_entry_tile_id` | string | `T03` | 最近分支入口，用于路线偏好决策 |

`dynamic_state` 示例（非空）：

```json
{
  "turn_meta": {
    "game_id": "demo-room-123",
    "round_index": 3,
    "turn_index": 11,
    "current_player_id": "p2",
    "current_tile_id": "T03",
    "current_tile_subtype": "BANK"
  },
  "self_state": {
    "player_id": "p2",
    "cash": 980,
    "deposit": 200,
    "net_worth": 1580,
    "property_ids": ["T01", "T07"],
    "position": 3,
    "route_preference_tile_id": null,
    "alliance_with": null,
    "alive": true
  },
  "others_state": [
    {"player_id": "p1", "position": 8, "net_worth": 1720, "alliance_with": null, "alive": true},
    {"player_id": "p3", "position": 5, "net_worth": 1490, "alliance_with": "p4", "alive": true},
    {"player_id": "p4", "position": 13, "net_worth": 1620, "alliance_with": "p3", "alive": true}
  ],
  "risk_hints": {
    "distance_to_nearest_bank": 0,
    "distance_to_nearest_enemy_property": 2,
    "distance_to_nearest_event": 1
  },
  "local_horizon_paths": {
    "lookahead_steps": 6,
    "branch_entry_tile_id": "T03",
    "paths": [
      ["T04A", "T05A", "T06", "T07", "T08", "T09"],
      ["T04B", "T05B", "T06", "T07", "T08", "T09"]
    ]
  }
}
```

## 3.3 `recent_actions_3turns`（近期步骤回顾，每回合更新）

用途：固定提供最近 3 次“动作 + 意图 + 结果”摘要，避免模型每次重读长历史。

建议结构：

- `turn_index`
- `action`
- `args`
- `thought_summary`
- `result`（accepted/rejected + 关键收益或损失）

说明：

- 这部分来自短期记忆层，不直接从全量 event log 原样拼接。
- `thought` 字段来自该 Agent 之前回合输出中的 `thought`（伪流式展示同源）。

字段定义（建议）：

| 字段 | 类型 | 示例 | 含义 |
|---|---|---|---|
| `turn` | int | `11` | 当时发生动作的回合序号 |
| `action` | string | `PAY_RENT` | 系统归一化动作标签 |
| `target` | string/null | `Tile_15` | 行为目标地块/对象 |
| `thought` | string/null | `现金流跌破警戒线` | 来自模型历史输出 thought |
| `amount` | int/null | `500` | 金额类动作的数值 |
| `to` | string/null | `Agent_B` | 对手或交易对象 |
| `result` | string | `accepted` | 系统执行结果（自动生成） |
| `delta_cash` | int | `-500` | 执行后现金变化（自动生成） |

短期记忆结构示例（按你给的格式扩展）：

```json
{
  "short_term_memory": [
    {"turn": 9, "action": "BUY", "target": "Tile_12", "thought": "抢占商业区核心", "result": "accepted", "delta_cash": -360},
    {"turn": 10, "action": "SKIP", "target": "Tile_13", "thought": "现金流跌破警戒线，放弃建设", "result": "accepted", "delta_cash": 0},
    {"turn": 11, "action": "PAY_RENT", "target": "Tile_15", "amount": 500, "to": "Agent_B", "thought": "先保流动性，避免破产连锁", "result": "accepted", "delta_cash": -500}
  ]
}
```

---

## 4. 需要同步修改的代码区域（防耦合）

## 4.1 协议与数据模型层

文件：

- `backend/app/schemas.py`

建议新增或扩展：

- `StaticMapContext`
- `DynamicStateContext`
- `RecentActionItem` / `RecentActionsContext`
- `MemoryContext`（short_term + long_term）
- `TurnInput` 增补字段：`static_map`、`dynamic_state`、`recent_actions_3turns`、`memory_context`

## 4.2 上下文构建层（建议新增，核心解耦）

建议新增文件：

- `backend/app/context_builder.py`

职责：

- 把 `GameSession` 转为标准 `AgentContextPacket`，统一产出 `static_map/dynamic_state/recent_actions_3turns`。
- `games.py` 和 `agent_runtime.py` 只调用 builder，不自行拼字段。

## 4.3 引擎与地图层（局部 6 格多路径）

文件：

- `backend/app/game_engine.py`
- `backend/app/map_engine.py`

需要同步：

- 在 `GameManager` 增加“枚举前方 6 格所有分叉路径”函数，作为单一事实源。
- `_allowed_actions()` 与 `dynamic_state.local_horizon_paths` 复用同一底层逻辑。

## 4.4 记忆层（短期 + 长期）

文件：

- 现有：`backend/app/agent_memory.py`
- 建议新增：`backend/app/memory_repository.py`、`backend/app/memory_repository_sqlite.py`、`backend/app/memory_summarizer.py`

需要同步：

- 短期记忆继续回合级更新（至少保留最近 3 次）。
- 对局结束时写入长期记忆（上一局总结）。
- 回合决策时融合短期 + 长期，并注入 `memory_context`。

## 4.5 提示词模板与 runtime 层

文件：

- `backend/app/prompts/templates.py`
- `backend/app/prompts/router.py`
- `backend/app/agent_runtime.py`

需要同步：

- 模板升级到 `2.x`，以“上下文分层”渲染。
- 保留 `## Turn Input JSON` 块，兼容 `HeuristicDecisionModel.extract_turn_input()`。
- `AgentRuntime.build_turn_input()` 切换为消费上下文 builder 的产物。

## 4.6 API、回放与测试层

文件：

- `backend/app/api/games.py`
- `backend/app/agent_eval.py`
- `backend/tests/test_agent_runtime.py`
- `backend/tests/test_prompt_templates.py`
- `backend/tests/test_contract_schema.py`
- `docs/Agent输入输出协议.md`

需要同步：

- API 输入组装改为调用上下文 builder。
- 评测逻辑适配新字段，确保 fallback/非法动作率不劣化。
- 协议文档同步更新为“上下文管理系统”术语。

## 4.7 前端同步修改区域（新增）

虽然本次升级核心在后端，但前端存在明确耦合点，必须同步。

文件（已识别）：

- `frontend/src/types/game.ts`
- `frontend/src/store/gameStore.ts`
- `frontend/src/services/ws.ts`
- `frontend/src/components/AgentStreamPanel.tsx`
- `frontend/src/components/ActionPanel.tsx`
- `frontend/src/components/ReplayPanel.tsx`
- `frontend/src/pages/GamePage.tsx`
- `frontend/src/pages/ReplayPage.tsx`

需要同步：

- 在类型层新增 `static_map`、`dynamic_state`、`recent_actions_3turns`、`memory_context`。
- `state.sync` 消费逻辑要兼容新上下文字段，避免丢字段导致 UI 状态回退。
- Agent 思维流面板与审计面板增加“最近3回合动作摘要”展示入口。
- 回放页兼容新 `DecisionAudit` 扩展字段（如 `memory_version`、`input_digest`）。
- 动作面板继续以 `allowed_actions` 为唯一执行源，不从上下文快照反推动作。

## 4.8 配置、脚本与可观测性层（新增）

文件：

- `backend/app/core/config.py`
- `backend/app/api/games.py`
- `backend/app/core/agent_options.py`
- `backend/scripts/*`（评测与报告）
- `backend/tests/test_map_engine.py`
- `backend/tests/test_map_svg.py`

建议新增配置：

- `CONTEXT_LOOKAHEAD_STEPS=6`
- `MEMORY_SHORT_WINDOW=3`
- `MEMORY_LONGTERM_PROVIDER=memory|sqlite`
- `MEMORY_SQLITE_PATH=backend/data/agent_memory.db`

需要同步：

- 把局部视野步数从硬编码改配置化。
- 在指标体系增加 `context_builder_latency_ms`、`memory_fetch_latency_ms`、`memory_hit_rate`。
- 批量评测脚本增加“上下文模板版本”维度对比。

---

## 5. 最终升级输入样式（建议模板）

```text
# Agent Context Packet v2

## 1) System Prompt (Fixed)
### 1.1 Monopoly Core Rules
{{system_rules.core_rules}}

### 1.2 Current Tile Rules
{{system_rules.current_tile_rules}}

### 1.3 Output Norm
必须仅返回 JSON；action 必须来自合法动作列表；参数必须满足约束。

## 2) Static Map (Fixed)
{{static_map_json}}

## 3) Dynamic State (Per Turn)
{{dynamic_state_json}}

## 4) Recent Actions Review (Last 3 Turns, Per Turn)
{{recent_actions_3turns_json}}

## 5) Memory
### 5.1 Short-Term Memory (Per Turn)
{{memory_context.short_term_summary}}

### 5.2 Long-Term Memory (Cross Game, Persistent)
{{memory_context.long_term_summary}}

### 5.3 Memory Guardrail
若记忆与当前合法动作冲突，以合法动作列表为准。

## 6) Legal Actions (Per Turn)
{{allowed_actions_json}}

## 7) Output Contract (Fixed)
{{output_contract_json}}

Allowed keys:
- protocol
- action
- args
- thought
- strategy_tags
- candidate_actions
- confidence

## 8) Turn Input JSON (Machine Readable)
{{turn_input_json}}
```

---

## 6. 建议的数据结构（示意）

## 6.1 上下文包字段总表

| 字段 | 类型 | 更新频率 | 说明 |
|---|---|---|---|
| `protocol` | string | 固定 | 输入协议版本 |
| `template_key` | string | 固定 | 模板键 |
| `template_version` | string | 可控升级 | 模板版本 |
| `system_rules` | object | 固定/低频 | 总规则、地块规则、输出规范 |
| `static_map` | object | 固定 | 静态地图拓扑与地块定义 |
| `dynamic_state` | object | 每回合 | 当前回合实时状态 |
| `recent_actions_3turns` | array | 每回合 | 最近 3 次操作回顾 |
| `memory_context` | object | 每回合 | 短期+长期记忆融合 |
| `options` | array | 每回合 | 合法动作与参数约束 |
| `output_contract` | object | 固定 | 输出字段和 JSON 合同 |

## 6.2 完整示例（非空）

```json
{
  "protocol": "DY-MONO-TURN-IN/3.2",
  "template_key": "AGENT_CONTEXT_TEMPLATE",
  "template_version": "2.0.0",
  "system_rules": {
    "core_rules": "目标是提升净资产并避免破产；经过起点奖励200；动作必须来自合法列表。",
    "current_tile_rules": "当前位于 BANK，可进行存款或取款，金额需满足100整数倍。",
    "output_norm": "仅输出 JSON 对象，必须包含 protocol/action/args。"
  },
  "static_map": {
    "map_id": "branch18",
    "topology": "graph",
    "track_length": 18,
    "start_tile_id": "T00",
    "edges": [
      {"from_tile_id": "T03", "to_tile_id": "T04A"},
      {"from_tile_id": "T03", "to_tile_id": "T04B"},
      {"from_tile_id": "T04A", "to_tile_id": "T05A"},
      {"from_tile_id": "T04B", "to_tile_id": "T05B"}
    ]
  },
  "dynamic_state": {
    "turn_meta": {
      "game_id": "demo-room-123",
      "round_index": 3,
      "turn_index": 11,
      "current_player_id": "p2",
      "current_tile_id": "T03",
      "current_tile_subtype": "BANK"
    },
    "self_state": {
      "cash": 980,
      "deposit": 200,
      "net_worth": 1580,
      "property_ids": ["T01", "T07"],
      "position": 3,
      "alliance_with": null
    },
    "others_state": [
      {"player_id": "p1", "position": 8, "net_worth": 1720},
      {"player_id": "p3", "position": 5, "net_worth": 1490},
      {"player_id": "p4", "position": 13, "net_worth": 1620}
    ],
    "risk_hints": {
      "distance_to_nearest_bank": 0,
      "distance_to_nearest_enemy_property": 2
    },
    "local_horizon_paths": {
      "lookahead_steps": 6,
      "branch_entry_tile_id": "T03",
      "paths": [
        ["T04A", "T05A", "T06", "T07", "T08", "T09"],
        ["T04B", "T05B", "T06", "T07", "T08", "T09"]
      ]
    }
  },
  "recent_actions_3turns": [
    {"turn": 9, "action": "BUY", "target": "Tile_12", "thought": "抢占商业区核心", "result": "accepted"},
    {"turn": 10, "action": "SKIP", "target": "Tile_13", "thought": "现金流跌破警戒线，放弃建设", "result": "accepted"},
    {"turn": 11, "action": "PAY_RENT", "target": "Tile_15", "amount": 500, "to": "Agent_B", "thought": "先保流动性，避免破产连锁", "result": "accepted"}
  ],
  "memory_context": {
    "short_term_summary": "最近3回合：买入1次、跳过1次、支付租金1次；当前现金承压。",
    "long_term_summary": "上一局在第12回合后因高杠杆破产；建议优先维持600+现金缓冲。",
    "summary_version": "v1"
  },
  "options": [
    {
      "action": "bank_deposit",
      "required_args": ["amount"],
      "allowed_values": {"amount": [100, 200, 300, 400, 500, 600, 700, 800, 900]},
      "default_args": {"amount": 200}
    },
    {
      "action": "bank_withdraw",
      "required_args": ["amount"],
      "allowed_values": {"amount": [100, 200]},
      "default_args": {"amount": 200}
    },
    {
      "action": "set_route_preference",
      "required_args": ["target_tile_id"],
      "allowed_values": {"target_tile_id": ["T04A", "T04B"]},
      "default_args": {"target_tile_id": "T04A"}
    },
    {"action": "pass", "required_args": [], "allowed_values": {}, "default_args": {}}
  ],
  "output_contract": {
    "protocol": "DY-MONO-TURN-OUT/3.1",
    "json_only": true,
    "required_fields": ["protocol", "action", "args"],
    "reject_extra_fields": true
  }
}
```

## 6.3 子结构字段细表（补充）

### A) `static_map.tiles[]`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tile_id` | string | 是 | 地块唯一 ID |
| `tile_index` | int | 是 | 地块序号（连续） |
| `name` | string | 是 | 地块显示名 |
| `tile_type` | string | 是 | `START/PROPERTY/EMPTY/BANK/EVENT/QUIZ` |
| `tile_subtype` | string | 否 | 子类型，默认同 `tile_type` |
| `property_price` | int/null | 否 | 地价，仅 PROPERTY 需要 |
| `toll` | int/null | 否 | 过路费，仅 PROPERTY 需要 |
| `event_key` | string/null | 否 | 事件键，仅 EVENT 需要 |
| `quiz_key` | string/null | 否 | 题目键，仅 QUIZ 需要 |
| `next_tile_ids` | string[] | 否 | 显式拓扑后继，分支地图关键字段 |
| `render` | object | 是 | 前端绘制参数，`x/y/w/h` 至少存在 |

### B) `dynamic_state.risk_hints`

| 字段 | 类型 | 示例 | 说明 |
|---|---|---|---|
| `distance_to_nearest_bank` | int | `0` | 最近银行步数，0 表示当前格即银行 |
| `distance_to_nearest_event` | int | `1` | 最近事件格步数 |
| `distance_to_nearest_enemy_property` | int | `2` | 最近非己方地产步数 |
| `projected_branch_count_6` | int | `2` | 前6步内可遇到的分支路径数 |
| `high_toll_tile_in_6` | bool | `true` | 前6步是否存在高过路费地块 |

### C) `recent_actions_3turns[]`

| 字段 | 来源 | 说明 |
|---|---|---|
| `turn` | 系统自动生成 | 记录发生动作的 turn index |
| `action` | 系统自动生成 | 归一化动作名 |
| `target` | 系统自动生成 | 目标地块或对象 |
| `thought` | 模型历史输出 | 对应当回合输出 `thought` |
| `amount` | 系统自动生成 | 金额类动作参数 |
| `to` | 系统自动生成 | 交易对手/收款方 |
| `result` | 系统自动生成 | accepted/rejected |
| `delta_cash` | 系统自动生成 | 执行后现金变动 |

### D) `options[]`

| 字段 | 类型 | 说明 |
|---|---|---|
| `action` | string | 可执行动作名 |
| `required_args` | string[] | 必填参数 |
| `allowed_values` | object | 参数白名单 |
| `default_args` | object | 默认参数 |

约束：

- Agent 只能在 `options.action` 中选择动作。
- 参数缺失或超出 `allowed_values` 必须判定非法。
- 若输出非法，仍走 fallback，保证对局推进。

兼容策略：

- 第一阶段可先维持 `DY-MONO-TURN-IN/3.1`，新字段设默认值。
- 模板先升到 `2.x`，协议版本后置升级到 `3.2`。
- A/B 路由逐步放量，防止一次性行为漂移。

---

## 7. 分阶段实施建议（先解耦后增强）

1. **Phase A**：新增 `context_builder.py`，不改协议，先产出 `static_map/dynamic_state/recent_actions_3turns`。
2. **Phase B**：模板升级到 `2.x`，接入上下文分层渲染，保留 `Turn Input JSON`。
3. **Phase C**：落长期记忆持久化（SQLite），接入上一局总结读写。
4. **Phase D**：扩展 `TurnInput/DecisionAudit` 字段，增强可追溯性。
5. **Phase E**：评测放量与回归，关注非法动作率、fallback 比例、局末耗时。

## 7.1 开发排期建议（可按两周节奏）

### Sprint 1（架构落地）

- 交付：`context_builder.py`、`local_horizon_paths` 统一计算、前后端类型占位。
- DoD：
  - 后端可稳定产出 `static_map/dynamic_state/recent_actions_3turns`。
  - 前端不报错且能忽略未知字段。
  - 单测覆盖分支地图前瞻路径生成。

### Sprint 2（模板和记忆）

- 交付：模板 `2.x`、短期记忆结构化、长期记忆 SQLite 仓储、局后总结写入。
- DoD：
  - `thought` 能回填到 `recent_actions_3turns`。
  - 服务重启后可读取长期记忆摘要。
  - 评测中非法动作率不高于基线。

### Sprint 3（审计与回放）

- 交付：`DecisionAudit` 扩展、回放页面与导出升级、指标补齐。
- DoD：
  - 可追溯“本回合使用了哪些上下文片段”。
  - 回放可查看最近3次动作与记忆命中摘要。
  - 关键链路指标可观测。

## 7.2 上线闸门（Release Gate）

- 功能闸门：分支地图、单环地图均能稳定生成 `local_horizon_paths`。
- 质量闸门：核心测试通过，新增字段不会破坏旧客户端。
- 性能闸门：上下文构建耗时 P95 可控（建议 < 20ms，不含模型推理）。
- 安全闸门：动作合法性和参数校验仍为最终裁决层。

---

## 8. 耦合风险与规避

- 风险 1：动作与局部快照计算分裂  
  规避：统一由 `GameManager` 计算前方 6 格多路径，`options` 与 `dynamic_state` 共用逻辑。

- 风险 2：短期记忆和最近 3 次回顾重复维护  
  规避：`recent_actions_3turns` 由 memory 层单点产出，模板只读消费。

- 风险 3：长期记忆影响当前合法性  
  规避：在模板中显式 `Memory Guardrail`，并坚持动作合同校验优先级最高。

- 风险 4：模板改造影响 heuristic 测试链  
  规避：保留 `## Turn Input JSON` 机器块，待 heuristic 升级后再移除耦合。

---

## 9. 分支实施建议

- 分支名建议：`feature/agent-context-management-v2`
- 提交粒度建议：
  1. `refactor: add agent context builder skeleton`
  2. `feat: add static_map and dynamic_state local_horizon_paths`
  3. `feat: add recent_actions_3turns and memory context`
  4. `feat: template v2 for agent context packet`
  5. `feat: persistent long-term memory and summary pipeline`
  6. `test/docs: align protocol docs and runtime tests`

## 9.1 建议补充分支策略

- 主分支：`feature/agent-context-management-v2`
- 子分支建议：
  - `feature/acms-context-builder`
  - `feature/acms-template-v2`
  - `feature/acms-memory-persistence`
  - `feature/acms-frontend-alignment`
- 合并策略：
  - 每个子分支独立通过测试后再合并主功能分支。
  - 主功能分支最终走一次完整回归再合并到主干。

---

## 10. 结论

“Agent 上下文管理系统”不是简单加字段，而是把当前可用链路升级为**统一上下文构建 + 分层提示词渲染 + 记忆双层管理**。  
按本预研稿推进，可以先解决耦合风险，再平滑引入 `static_map`、`dynamic_state`、`recent_actions_3turns` 三个关键能力，最终支撑后续策略迭代和复盘优化。

