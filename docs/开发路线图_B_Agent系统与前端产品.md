# 开发路线图 B（Agent 系统 + 前端产品）

适用对象：开发者 B  
主责范围：Agent Runtime、Prompt 体系、前端对局体验、复盘体验、策略评测

---

## 0. 统一口径（必须先看）

你后续全部开发，以以下三类资料为同一基线：

1. `AI大富翁_整合版_产品与AI开发路线图.md`
2. `AgentMonopoly/AgentMonopoly_开发文档.md`
3. `AgentMonopoly/docs/MVP_开发配置与代码脉络.md`

统一规则如下：

- AI 仅给参数化动作，不写业务代码。
- AI 决策必须严格来自后端给定 `options.allowed_values`。
- AI 结果必须满足 `output_contract`，且 `json_only`。
- MVP 主线先完成 `START/EMPTY/BANK/EVENT/PROPERTY` 对应模板；`QUIZ` 在后续阶段加入。
- 前端与后端通过合同字段对齐，不做“猜字段”适配。
- 复盘视图以后端快照与事件流为唯一真值。

若发现需求与三类文档不一致，以本文件“冲突处理表”为准，并同步在 `docs/` 新增 ADR。

---

## 1. 你的系统 owner 边界

你直接 owner 的目录与文件：

- `AgentMonopoly/backend/app/agent_runtime.py`
- 新增：`AgentMonopoly/backend/app/prompts/**`
- 新增：`AgentMonopoly/backend/app/agent_memory.py`
- 新增：`AgentMonopoly/backend/app/agent_eval.py`
- `AgentMonopoly/frontend/src/App.tsx`
- 新增：`AgentMonopoly/frontend/src/store/**`
- 新增：`AgentMonopoly/frontend/src/components/**`
- 新增：`AgentMonopoly/frontend/src/services/api.ts`
- 新增：`AgentMonopoly/frontend/src/services/ws.ts`
- 新增：`AgentMonopoly/frontend/src/pages/**`
- 新增：`AgentMonopoly/frontend/tests/**`

你无需 owner 的内容：

- 引擎状态机内部规则
- DB 实体与 replay 存储细节

你要给 A 提供：

- Agent 输入字段需求清单
- 模型异常样本与 fallback 触发样本
- 前端事件消费契约问题单

---

## 2. 冲突处理表（三类文档统一）

1. 关于“AI 思考日志是否必传”
- 统一结论：业务执行只依赖结构化动作；思考日志作为可选调试字段。
- 你的动作：`thought` 字段可选，不参与动作合法性判定。

2. 关于“模板是一个还是按格子拆分”
- 统一结论：按 tile subtype 拆模板。
- 你的动作：至少 8 类模板，独立版本号。

3. 关于“前端真值来源”
- 统一结论：后端状态与事件为唯一真值。
- 你的动作：前端本地状态仅做展示缓存，不自行演算经济结果。

4. 关于“QUIZ 节奏”
- 统一结论：先预留 UI 与 runtime 插槽，MVP 主线不阻塞。
- 你的动作：在 Agent Runtime 与前端事件面板保留 `quiz.*` 占位。

---

## 3. Phase 路线（大任务版本）

## Phase B1：Agent Runtime 真链路

目标：从 fallback 变为可控、可解释、可降级的模型执行链。

任务：

1. 输入构建器：
- 拼装 `turn_meta/tile_context/player_state/players_snapshot/board_snapshot/options/output_contract`
- 对不同 tile subtype 注入差异化上下文

2. 输出解析器：
- 强制 `DY-MONO-TURN-OUT/3.1`
- 严格字段校验
- 拒绝额外字段

3. 失败治理：
- 超时重试
- 解析失败重试
- 非法动作降级 `pass/default_value`

4. 审计记录：
- prompt hash
- model tag
- raw response 摘要
- final decision

完成标准：

- 模型异常不影响游戏主链稳定。
- 非法动作率可追踪。

---

## Phase B2：Prompt 模板体系

目标：让策略行为具备可调、可 A/B、可追溯。

任务：

1. 模板分组（至少）：
- `PROPERTY_UNOWNED_TEMPLATE`
- `PROPERTY_SELF_TEMPLATE`
- `PROPERTY_ALLY_TEMPLATE`
- `PROPERTY_OTHER_TEMPLATE`
- `BANK_TEMPLATE`
- `EVENT_TEMPLATE`
- `EMPTY_TEMPLATE`
- `QUIZ_TEMPLATE`（预留）

2. 每个模板统一结构：
- 当前目标
- 参数范围
- 输出合同
- 风险提示

3. 版本管理：
- 模板版本号
- 变更日志
- A/B 策略路由

4. 评测脚本：
- 针对同一局面比较模板版本效果

完成标准：

- 任意回合可定位使用了哪个模板版本。
- A/B 对比可复现。

---

## Phase B3：前端对局主界面

目标：从 demo 页面升级成可观战可操作产品界面。

任务：

1. 页面结构：
- 房间与对局控制区
- 棋盘区
- 玩家资产与联盟面板
- 实时事件时间线
- 动作面板

2. 数据接入：
- HTTP：state/action/replay
- WebSocket：实时事件
- 断线后自动重连与状态同步

3. 状态管理：
- Zustand 模块拆分
- 按 game_id 隔离状态
- 事件驱动更新

4. UI 交互：
- 动作合法性提示
- 错误反馈
- 当前 phase 可视化

完成标准：

- 人类玩家可完整参与一局。
- 观战客户端可实时看到全局状态变化。

---

## Phase B4：复盘与策略分析体验

目标：让产品具备“复盘价值”，不只是一局游戏。

任务：

1. replay 播放器：
- 按回合播放
- 单步前进/后退
- 跳转到指定回合

2. 事件对比面板：
- 候选动作 vs 最终动作
- 关键资产变化曲线

3. 策略标签体系：
- 保守型/扩张型/现金优先等标签
- 回合内策略切换记录

4. 导出能力：
- 对局摘要导出（JSON/Markdown）

完成标准：

- 一局结束后能直接查看策略演化轨迹。

---

## Phase B5：评测与提效体系

目标：把 Agent 迭代变成工程化流程。

任务：

1. 指标体系：
- 胜率
- 平均总资产
- 破产率
- 非法动作率
- fallback 触发率

2. 批量评测：
- 多种 Agent profile 对战
- 固定随机种子
- 自动汇总结果

3. 策略改进闭环：
- 差局回放定位
- prompt 微调
- 再评测

完成标准：

- 每次模板变更都有量化结果对比。

---

## 4. 与开发者 A 的协作接口

你必须依赖 A 提供：

1. 稳定 schema
2. 稳定 API/WS 合同
3. replay 查询格式
4. 错误码体系

你必须回传给 A：

1. 模型异常样例（用于规则层 fallback 校验）
2. 前端消费痛点（字段缺失、事件歧义）
3. 评测指标需求（便于 A 增加埋点）

---

## 5. 你的 DoD（Done Definition）

以下条件全满足，才算你这条线完成：

1. Agent Runtime 可稳定跑完整局，不因模型异常拖垮流程。
2. 模板体系具备版本化与 A/B 对比能力。
3. 前端可实时对局 + 回放 + 核心分析。
4. 指标体系可用于持续优化策略。
5. 与 A 的合同长期稳定，无频繁字段改动。

---

## 6. 你要优先开的 GitHub Issues（建议）

1. `AGENT-001` turn input builder 与 output parser
2. `AGENT-002` 模型异常治理与降级链
3. `PROMPT-001` 8 类模板落地与版本化
4. `PROMPT-002` A/B 路由与评测脚本
5. `FE-001` 对局主界面重构
6. `FE-002` WebSocket 事件消费与重连
7. `FE-003` replay 播放器与时间线
8. `EVAL-001` 策略指标面板与批量对战汇总

