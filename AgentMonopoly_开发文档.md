# AgentMonopoly 开发文档（Web 前端 + Python Agent 后端）

## 1. 项目概述

### 1.1 项目定位
AgentMonopoly 是一个支持多人（人类或 AI Agent）对战的“类大富翁”网页游戏。  
核心目标是：在可控规则下，让不同策略风格的 Agent 在有限信息和有限回合中进行博弈，便于观察策略表现、复盘和持续优化。

### 1.2 产品目标
- 提供可运行的多人回合制大富翁对战体验。
- 支持 Agent 自动决策与日志记录。
- 支持结盟、买地、过路费、破产拍卖等核心经济交互。
- 支持回放与复盘，为后续 Agent 迭代提供数据基础。

### 1.3 MVP 范围
- 地图为单环路（无岔路）。
- 四名玩家（可混合：真人 + Agent）。
- 核心格子：空地、无人地产、有人地产、银行、随机事件。
- 结盟：每人最多结盟 1 人，互免过路费。
- 破产机制：流动资产为 0 时触发破产拍卖（现金+存款受约束）。
- 有限回合模式优先（避免无限局时长不可控）。

## 2. 规则定义（规范化）

### 2.1 胜负条件
- 有限回合模式：回合结束后总资产最高者获胜。
- 无限回合模式（后续可选）：除自己外其余玩家全部破产即获胜。

### 2.2 资产定义
- 现金：可立即支付和购买。
- 存款：银行账户，可存取。
- 地产价值：所持地块与建筑的总估值。
- 总资产 = 现金 + 存款 + 地产估值。

### 2.3 回合流程
1. 系统掷骰子（1-6）。
2. 玩家移动到目标格子。
3. 系统执行自动行为（如过路费）。
4. 生成本轮“合法动作列表”。
5. 玩家或 Agent 选择动作（可多步，直到回合结束条件满足）。
6. 写入结构化日志并广播状态快照。

### 2.4 格子行为
- 空格子：通常无强制行为，可允许发起结盟。
- 无人地产：可购买或放弃，可发起结盟。
- 有人地产：自动支付过路费，可发起结盟。
- 银行：可存款/取款。
- 随机事件：抽取事件卡并结算（MVP 可简化为资金增减）。
- 有奖问答：暂缓，不纳入 MVP。

### 2.5 联盟规则
- 每位玩家最多同时与 1 名玩家结盟。
- 联盟双方互免过路费。
- 结盟需双方确认（双向同意）。
- 可主动解盟（建议设置冷却回合，防止刷机制）。

### 2.6 破产与拍卖
- 当玩家无法支付应付款且流动资产（现金+可立即取出的存款）不足时，触发破产流程。
- 破产玩家地产进入拍卖池，其他玩家可竞拍。
- 拍卖后仍无法偿付则出局。

## 3. 技术栈（前后端分离，简化版）

### 3.1 第一版 MVP 必需
- 前端：`React + TypeScript + Vite + TailwindCSS`
- 前端状态：`Zustand`
- 后端：`FastAPI + Pydantic + Uvicorn`
- 实时：`WebSocket`（后端推送回合状态）
- 数据库：`SQLite`
- ORM：`SQLModel`（或 `SQLAlchemy` 二选一）
- Agent：`PydanticAI + OpenAI Compatible API`
- Agent 执行链：`状态注入 -> 模型决策 -> 结构化解析 -> 动作白名单校验 -> 引擎执行`

### 3.2 后期可升级
- 数据库：`SQLite -> PostgreSQL`
- Agent 编排：`PydanticAI -> LangGraph`（多阶段策略/复盘流程）
- 任务系统：增加 `Celery/RQ` 处理复盘、批量对局、离线评估
- 缓存与房间并发：增加 `Redis`
- 部署：本地双进程 -> `Docker Compose` -> 云上容器化

### 3.3 Agent 框架结论
- 当前主推：`PydanticAI`（24 小时内最稳妥）
- 原因：结构化输出和类型校验直接可用，能显著降低“非法动作/解析失败”风险
- 备选：`OpenAI SDK + 自定义 Runtime`（更轻）；`LangGraph`（更强但更重）

## 4. 系统架构设计

### 4.1 总体架构
- 前端负责：房间管理、棋盘展示、操作交互、日志与回放 UI。
- 后端负责：游戏规则引擎、回合推进、合法动作计算、结算、Agent 调用。
- Agent 层负责：根据状态快照输出标准化动作与思考日志。
- 数据层负责：游戏状态持久化、日志存储、复盘数据集。

### 4.2 核心模块
- Room 服务：创建房间、加入/离开、玩家就绪、开局参数。
- Game Engine：骰子、移动、规则判定、结算、胜负判断。
- Action Validator：合法动作生成与参数校验。
- Agent Runtime：组装上下文、调用模型、解析动作、容错重试。
- Event Bus：广播状态变化（WebSocket）。
- Replay 服务：按时间线回放并导出日志。

## 5. 数据模型（建议）

### 5.1 关键实体
- `Player`: id, name, type(human/agent), cash, deposit, position, alive, alliance_with
- `Property`: id, position, owner_id, level, base_price, toll_formula
- `Game`: id, status, round_index, max_rounds, map_id, current_player_id
- `Action`: id, game_id, round_index, player_id, action_type, payload, valid, reason
- `EventLog`: id, game_id, ts, event_type, actor_id, data(json)
- `AgentProfile`: id, player_id, model, api_base, api_key_ref, style_tag

### 5.2 状态快照建议
- 每回合落地 `GameSnapshot`（JSON），用于回放与复盘。
- 快照内容：所有玩家资产、位置、联盟关系、地产归属、剩余回合等。

## 6. API 与实时协议（MVP）

### 6.1 HTTP API（示例）
- `POST /rooms` 创建房间
- `POST /rooms/{room_id}/join` 加入房间
- `POST /games/{game_id}/start` 开始游戏
- `GET /games/{game_id}/state` 获取当前状态
- `POST /games/{game_id}/actions` 提交动作
- `POST /games/{game_id}/agent/act` 触发 Agent 决策
- `GET /games/{game_id}/logs` 拉取日志
- `GET /games/{game_id}/replay` 回放数据

### 6.2 WebSocket 事件（示例）
- `game.started`
- `turn.started`
- `dice.rolled`
- `player.moved`
- `action.accepted`
- `action.rejected`
- `settlement.applied`
- `player.bankrupt`
- `game.finished`

## 7. Agent 设计规范

### 7.1 输入分层（与你的大纲对齐）
1. 当前情境说明：你正在玩大富翁 + 当前回合任务。
2. 规则摘要：与当前格子相关的必要规则。
3. 私有历史经验：该 Agent 的短期记忆摘要（1-2 句）。
4. 当前自身状态：现金、存款、房产、位置、联盟状态。
5. 全局快照：其他玩家位置与资产概览。
6. 本轮合法动作列表：必须严格从列表中选择。
7. 输出格式要求：标准 JSON 动作 + 自然语言思考日志。

### 7.2 输出格式（建议）
```json
{
  "action": "buy_property",
  "args": {
    "property_id": "P12"
  },
  "thought": "当前现金充足，且该地块预计回报率高于持币收益，执行购买。"
}
```

### 7.3 上下文管理策略
- 保留上一步详细上下文。
- 更早历史压缩成摘要（减少 token 成本）。
- 注入前方 6 格风险信息（若未来有岔路，附带分支信息）。
- 不同格子类型注入不同模板上下文（银行/地产/事件）。

### 7.4 容错与安全
- 仅接受合法动作白名单。
- 动作参数二次校验，非法则回退为 `pass` 或重新请求。
- 模型超时与异常走降级策略（默认保守动作）。

## 8. 复盘系统设计

### 8.1 日志体系
- 结构化日志：动作、结算、状态变化、异常。
- 叙事日志：Agent 独白（用于可解释性和调试）。
- 统一关联键：`game_id + round + player_id`。

### 8.2 复盘功能
- 时间轴回放每回合状态。
- 对比“候选动作 vs 实际动作”。
- 导出复盘样本（可用于提示词优化或小规模微调数据）。

### 8.3 镜子协议（自我复盘）
- 回合后生成“决策得失总结”。
- 沉淀成 Agent 私有经验短句（受长度上限控制）。


## 11. 技术栈落地清单（MVP/升级）

### 11.1 MVP 必需（开工即用）
- 前端：`React + TS + Vite + Tailwind + Zustand`
- 后端：`FastAPI + Pydantic + SQLModel + WebSocket`
- Agent：`PydanticAI`
- 存储：`SQLite`
- 配置：前后端各自 `.env`
- 启动：前端 `npm run dev`，后端 `uvicorn app.main:app --reload`

### 11.2 后期升级（MVP 后再做）
- 数据库升级到 `PostgreSQL`
- Agent 工作流升级到 `LangGraph`
- 引入 `Redis` 做房间状态与并发优化
- 引入异步任务队列处理复盘和评测
- 使用 `Docker Compose` 或云部署标准化环境

