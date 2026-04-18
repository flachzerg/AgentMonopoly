# Agent 上下文管理系统重构完成记录

## 1. 背景与目标

本次重构基于 `docs/Agent输入系统标准化升级研究.md` 执行，目标是将原有“输入拼接”升级为“上下文管理系统”，实现：

- 每回合统一构建上下文包（静态地图、动态状态、短期记忆、长期记忆、合法动作合同）
- 后端单点构建、前后端统一消费，降低耦合
- 前端可在对局页折叠区域查看完整上下文

## 2. 本次完成内容

### 2.1 后端上下文管理链路

- 新增 `backend/app/context_builder.py`，统一构建：
  - `static_map`
  - `dynamic_state`
  - `recent_actions_3turns`
  - `memory_context`
- 扩展 `TurnInput` 上下文字段并接入运行时构建。
- `games.py` 在模型决策前生成并缓存上下文包，随后通过 `state.sync` 广播给前端（字段 `agent_context`）。

### 2.2 引擎与记忆增强

- `game_engine.py` 新增：
  - 前方多分支路径枚举 `build_local_horizon_paths(...)`
  - 最近目标类型地块距离计算 `distance_to_nearest_tile_type(...)`
- `agent_memory.py` 扩展：
  - 结构化短期记忆条目
  - 最近3回合动作回顾生成
  - 长期记忆摘要读写（进程内）

### 2.3 提示词模板升级

- `prompts/templates.py` 升级为分层上下文展示格式（Context Packet v2）。
- 保留 `## Turn Input JSON` 机器可读块，确保兼容既有 heuristic 提取逻辑。

### 2.4 前端上下文展示

- 类型系统新增 `AgentContextPacket`。
- `gameStore` 接收并存储 `state.sync.agent_context`。
- 对局页 `DecisionCenter` 折叠区新增上下文展示（真实上下文包）。

## 3. 修改文件清单

### 3.1 后端

- `backend/app/context_builder.py`（新增）
- `backend/app/schemas.py`
- `backend/app/game_engine.py`
- `backend/app/agent_memory.py`
- `backend/app/agent_runtime.py`
- `backend/app/api/games.py`
- `backend/app/prompts/templates.py`

### 3.2 前端

- `frontend/src/types/game.ts`
- `frontend/src/store/gameStore.ts`
- `frontend/src/components/DecisionCenter.tsx`
- `frontend/src/pages/GamePage.tsx`

### 3.3 文档

- `docs/Agent输入系统标准化升级研究.md`（已持续更新）
- `docs/Agent上下文管理系统重构完成记录.md`（本文件，新增）

## 4. 验证结果

- 后端测试：`..\.venv-Hackathon\Scripts\python.exe -m pytest`
  - 结果：`41 passed`
- 前端构建：`npm run build`
  - 结果：通过

## 5. 已知边界

- 长期记忆当前为进程内实现，尚未接入 SQLite 持久化仓储。
- 现有实现已为后续 `memory_repository_sqlite` 留出扩展入口。
