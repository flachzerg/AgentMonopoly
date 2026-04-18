# 程序员A分工文档（引擎与 AI 系统，v2.2）

角色定位：后端负责人（规则引擎、自动推进、复盘生成、自进化闭环）  
协作对象：程序员B（前端体验）

## 1. 目标边界

你负责让“对局可自动流畅推进 + 复盘可自动产出 + 自进化可闭环验证”。

不负责：页面视觉细节与前端样式实现。

## 2. 核心交付列表

## A1. 真人回合极简动作后端化
1. 新增/改造状态字段：
   - `turn_owner_type`: `human | ai`
   - `awaiting_human_decision`: `boolean`
   - `human_allowed_actions`: `string[]`
2. 动作接口限制：
   - 真人回合仅允许 `roll_dice` 与必要分支决策
   - 非真人回合拒绝前端人工动作请求
3. 自动推进接口：
   - `POST /games/{id}/auto-advance`
   - 行为：连续推进直到遇到真人决策点或对局结束

## A2. 复盘生成服务（全局中文）
1. 新增复盘任务接口：
   - `POST /games/{id}/replay/generate`
   - `GET /games/{id}/replay/report`
2. Prompt 模板版本化：
   - `prompt_version`
   - `template_id`
3. 输出结构固定：
   - overview
   - phase_analysis
   - turning_points
   - player_profiles
   - next_game_advice
4. 失败降级：
   - LLM 调用失败时返回规则摘要版复盘

## A3. AI 自进化 v1
1. 数据采集：
   - 每局指标：胜负、资产变化、非法动作率、fallback 次数
2. 评估任务：
   - `POST /evolution/jobs`
   - 输入：最近 N 局日志
   - 输出：模板参数建议
3. 策略版本管理：
   - `strategy_version`
   - `change_note`
   - `created_at`
4. 回退机制：
   - `POST /evolution/rollback/{version}`

## A4. 对外接口合同（给程序员B）
1. `GET /games/{id}/state` 增加字段：
   - `phase`
   - `awaiting_human_decision`
   - `human_allowed_actions`
   - `auto_advancing`
2. `GET /games/{id}/replay/report` 返回固定 JSON
3. `GET /games/{id}/timeline` 返回关键事件
4. `GET /evolution/summary` 返回自进化指标

## 3. 任务拆分与顺序

### 第 1 天
1. 明确状态机与动作白名单
2. 补接口 schema 与错误码

### 第 2-3 天
1. 打通 auto-advance 主链路
2. 写并发与边界测试

### 第 4-5 天
1. 接入复盘生成任务
2. 完成失败降级与超时处理

### 第 6-7 天
1. 自进化 v1 最小闭环
2. 策略版本与回退接口

## 4. 质量门槛

1. 单测覆盖：状态机关键分支 >= 90%
2. 端到端：
   - 一局对战从开局到复盘可完整跑通
   - 真人回合外的人工动作请求全部被拦截
3. 复盘接口成功率 >= 98%
4. 自进化任务失败不影响正常对局

## 5. 协作约定（与程序员B）

1. 任意接口字段变动，提前同步 OpenAPI 与示例响应
2. 每天固定一次联调窗口（30 分钟）
3. 若联调阻塞超过半天，优先给临时兼容字段

## 6. 主要风险与预案

1. LLM 超时导致复盘延迟
- 预案：异步任务 + 轮询 + 规则摘要降级

2. 自动推进与手动动作竞争
- 预案：game 级互斥锁 + 幂等 token

3. 自进化建议质量不稳定
- 预案：仅对离线对局生效，线上默认只读观察

## 7. 交付件清单

1. 接口文档（OpenAPI + 示例）
2. 状态机说明图（mermaid 或 markdown）
3. 复盘 Prompt 模板 v1
4. 自进化任务说明与版本表结构
5. 测试报告（核心链路）
