# Agent 输入输出协议

本文档只描述当前项目里 Agent 的输入/输出协议与字段语义，不包含流式实现细节。

## 1. 调用链路

1. `games.py` 组装 `TurnBuildInput`。
2. `agent_runtime.py` 构造 `TurnInput` 并渲染 prompt。
3. 模型返回 JSON，后端做协议与动作合法性校验。
4. 后端返回 `ActionResponse`，并通过 WebSocket 广播 `state.sync`（可带 `audit`）。

核心代码：

- `backend/app/api/games.py`
- `backend/app/agent_runtime.py`
- `backend/app/schemas.py`
- `backend/app/prompts/templates.py`

## 2. 输入协议：`TurnInput`

- 协议常量：`DY-MONO-TURN-IN/3.1`
- 定义位置：`backend/app/schemas.py::TurnInput`

### 2.1 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `protocol` | string | 是 | 固定 `DY-MONO-TURN-IN/3.1` |
| `turn_meta` | object | 是 | 回合元信息 |
| `tile_context` | object | 是 | 当前格子语义上下文 |
| `player_state` | object | 是 | 当前行动玩家状态 |
| `players_snapshot` | array | 是 | 所有玩家快照 |
| `board_snapshot` | object | 是 | 棋盘快照 |
| `history_records` | array | 是 | 最近事件（短期记忆） |
| `options` | array | 是 | 当前允许动作和参数约束 |
| `output_contract` | object | 是 | 输出合同（JSON-only/协议约束） |
| `template_key` | string | 是 | 模板 key |
| `template_version` | string | 是 | 模板版本 |
| `memory_summary` | string/null | 否 | 该玩家历史记忆摘要 |

### 2.2 关键子结构

#### `turn_meta`

| 字段 | 说明 |
|---|---|
| `game_id` | 对局 ID |
| `round_index`, `turn_index` | 回合编号 |
| `phase` | 当前阶段（当前为 `DECISION`） |
| `chain` | 阶段链路 |
| `current_player_id` | 当前玩家 |
| `tile_subtype` | 格子子类型（如 `PROPERTY_UNOWNED`） |

#### `tile_context`

| 字段 | 说明 |
|---|---|
| `tile_id`, `tile_index` | 格子标识与位置 |
| `tile_type`, `tile_subtype` | 格子类型 |
| `owner_id` | 拥有者 |
| `property_price`, `toll` | 地价和过路费 |
| `event_key`, `quiz_key` | 事件题目 key |

#### `options`（`ActionOption`）

- `action`: 动作名
- `required_args`: 必填参数
- `allowed_values`: 参数白名单
- `default_args`: 默认参数

### 2.3 输入示例（简化）

```json
{
  "protocol": "DY-MONO-TURN-IN/3.1",
  "turn_meta": {
    "game_id": "demo-room-123",
    "round_index": 2,
    "turn_index": 8,
    "phase": "DECISION",
    "current_player_id": "p2",
    "tile_subtype": "PROPERTY_UNOWNED",
    "chain": ["ROLL", "TILE_ENTER", "AUTO_SETTLE", "DECISION", "EXECUTE", "LOG"]
  },
  "tile_context": {
    "tile_id": "tile_05",
    "tile_index": 5,
    "tile_type": "PROPERTY",
    "tile_subtype": "PROPERTY_UNOWNED",
    "owner_id": null,
    "property_price": 300,
    "toll": 90
  },
  "player_state": {
    "player_id": "p2",
    "name": "Agent-2",
    "is_agent": true,
    "cash": 980,
    "deposit": 0,
    "net_worth": 1420,
    "position": 5,
    "property_ids": [],
    "alliance_with": null,
    "alive": true
  },
  "players_snapshot": [],
  "board_snapshot": { "track_length": 16, "tiles": [] },
  "history_records": [],
  "options": [
    { "action": "buy_property", "description": "购买地产", "required_args": [], "allowed_values": {}, "default_args": {} },
    { "action": "skip_buy", "description": "跳过购买", "required_args": [], "allowed_values": {}, "default_args": {} },
    { "action": "pass", "description": "结束决策", "required_args": [], "allowed_values": {}, "default_args": {} }
  ],
  "output_contract": {
    "protocol": "DY-MONO-TURN-OUT/3.1",
    "json_only": true,
    "required_fields": ["protocol", "action", "args"],
    "reject_extra_fields": true
  },
  "template_key": "PROPERTY_UNOWNED_TEMPLATE",
  "template_version": "1.1.0",
  "memory_summary": "上一轮现金吃紧，优先保证流动性。"
}
```

## 3. 输出协议：`AgentTurnOutput`

- 协议常量：`DY-MONO-TURN-OUT/3.1`
- 定义位置：`backend/app/schemas.py::AgentTurnOutput`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `protocol` | string | 是 | 固定 `DY-MONO-TURN-OUT/3.1` |
| `action` | string | 是 | 最终动作，必须在 `options` 中 |
| `args` | object | 是 | 动作参数 |
| `thought` | string/null | 否 | 解释文本 |
| `strategy_tags` | string[] | 否 | 策略标签 |
| `candidate_actions` | string[] | 否 | 候选动作 |
| `confidence` | number/null | 否 | 0~1 置信度 |

示例：

```json
{
  "protocol": "DY-MONO-TURN-OUT/3.1",
  "action": "buy_property",
  "args": {},
  "thought": "当前现金足够且地产无人持有，买入能提升净资产上限。",
  "strategy_tags": ["expansion"],
  "candidate_actions": ["buy_property", "skip_buy", "pass"],
  "confidence": 0.81
}
```

## 4. 校验规则（后端）

在 `agent_runtime.py::parse_turn_output()`：

1. 必须是 JSON 对象。
2. `protocol` 必须匹配合同。
3. `action` 必须在 `options` 中。
4. `required_args` 不可缺失。
5. `allowed_values` 必须满足约束。

任何失败将记入 `failure_codes`，并触发 fallback 决策。

## 5. 审计与前端消费

`DecisionAudit` 核心字段：

- `status`: `ok` / `fallback`
- `failure_codes`: 失败码
- `raw_response_summary`: 原始输出摘要
- `final_decision`: 最终结构化输出

当前 WebSocket 结构（核心）：

```json
{
  "type": "state.sync",
  "state": {},
  "event": {},
  "audit": {
    "status": "ok",
    "final_decision": {
      "action": "buy_property",
      "thought": "..."
    }
  }
}
```
