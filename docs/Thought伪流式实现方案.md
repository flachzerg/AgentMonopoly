# Thought 伪流式实现方案（方式 A）

本文档只描述“方式 A：模型先完整返回 JSON，再对 `thought` 做伪流式推送”的实现方案。

## 1. 目标

1. 保持现有 JSON-only 输出合同不变。
2. 在观战端看到 `thought` 的实时滚动效果。
3. 不影响现有 `state.sync + audit` 主链路。

## 2. 总体思路

1. `AgentRuntime.decide()` 正常拿到最终 `AgentDecisionEnvelope`。
2. 从 `envelope.decision.thought` 提取完整文本。
3. 后端按“标点/长度”切片，依次通过 WebSocket 推送增量。
4. 推送完成后发 `done` 事件，再走原本 `state.sync` 广播。

该方式本质是“回放式流”，不是模型 token 级实时流。

## 3. 新增 WS 事件协议

### 3.1 `agent.thought.delta`

```json
{
  "type": "agent.thought.delta",
  "game_id": "demo-room-123",
  "player_id": "p2",
  "turn_index": 8,
  "seq": 3,
  "delta": "地产无人持有，且当前现金可覆盖价格，",
  "is_final": false,
  "ts": "2026-04-18T12:00:00Z"
}
```

### 3.2 `agent.thought.done`

```json
{
  "type": "agent.thought.done",
  "game_id": "demo-room-123",
  "player_id": "p2",
  "turn_index": 8,
  "full_text": "地产无人持有，且当前现金可覆盖价格，买入后净资产上限更高。",
  "ts": "2026-04-18T12:00:01Z"
}
```

## 4. 后端改造点

## 4.1 `games.py`

- 在 `_run_agent_turn_once()` 中，在 `runtime.decide()` 之后、`apply_action()` 之前加入伪流式广播：
  - 发送 `agent.thought.delta`（多次）
  - 发送 `agent.thought.done`（一次）
- 再执行 `apply_action()` 并发送 `state.sync`（保持兼容）。

## 4.2 切片与节奏建议

- 切片优先按中文标点 `，。；！？`，其次按固定长度（建议 10~20 字）。
- 每片发送间隔建议 `35~80ms`（可配置）。
- 最大长度建议 `1024` 字，超过截断并在尾部加 `...`。

伪代码：

```python
chunks = split_thought(thought, max_chunk=18)
for seq, chunk in enumerate(chunks, start=1):
    await ws_manager.broadcast(game_id, {
        "type": "agent.thought.delta",
        "player_id": player_id,
        "turn_index": turn_index,
        "seq": seq,
        "delta": chunk,
        "is_final": seq == len(chunks),
        "ts": now_iso(),
    })
    await asyncio.sleep(0.05)
await ws_manager.broadcast(game_id, {
    "type": "agent.thought.done",
    "player_id": player_id,
    "turn_index": turn_index,
    "full_text": thought,
    "ts": now_iso(),
})
```

## 5. 前端展示方案（微信群聊风格）

## 5.1 数据组织

- 以 `player_id + turn_index` 作为一条“思考消息线程”键。
- `delta` 到来时追加文本，`done` 到来时标记完成。
- UI 按时间排序展示，最近消息在底部。

## 5.2 头像策略

- 每个 `player_id` 映射固定头像（emoji 或静态资源）。
- 同一 agent 始终使用同一头像，增强识别度。

## 5.3 气泡样式建议

- 左侧头像 + 右侧气泡文本（群聊样式）。
- “流式中”状态显示打字光标（如 `...` 闪动）。
- 完成后显示动作摘要（如 `-> buy_property`）和状态（`ok/fallback`）。

## 6. 开关与安全

建议新增环境变量：

- `THOUGHT_STREAM_MODE=off|summary|raw`
- `THOUGHT_STREAM_DELAY_MS=50`
- `THOUGHT_STREAM_MAX_LEN=1024`

策略：

1. 默认 `summary`（线上推荐）。
2. `raw` 仅用于演示或内测。
3. `off` 时不发送 `agent.thought.*`，完全保持旧行为。

## 7. 验收标准（DoD）

1. 触发 agent 行动后，前端可看到 thought 增量气泡。
2. 增量结束后收到 `done`，文本与最终 `audit.final_decision.thought` 一致。
3. 旧客户端忽略新事件后不崩溃。
4. 关闭开关后，系统退化为当前非流式行为。

## 8. 测试建议

后端：

- 切片函数：空字符串/长字符串/标点混合场景。
- 广播顺序：`delta* -> done -> state.sync`。

前端：

- 多 agent 并发消息是否按 `player_id+turn_index` 正确聚合。
- `done` 后状态是否从“流式中”切换到“已完成”。
