# 开发文档：OpenRouter 点开即玩 v2.1

## 1. 本次改动概览

## 1.1 后端
- 新增文件：`backend/config/openrouter_agent_config.template.json`
- 新增模块：`backend/app/core/agent_options.py`
- 扩展 schema：
  - `AgentConfig`
  - `PlayerConfig.agent_config`
  - `CreateGameRequest.room_name`
- API 增强：
  - `GET /games/agent-options`
  - `POST /games` 支持按玩家注入 agent_config
- Agent Runtime：改为按当前 AI 玩家动态构建 `RuntimeConfig`

## 1.2 前端
- 路由改造：
  - `/` -> `SetupPage`
  - `/game/:gameId` -> `GamePage`
  - `/replay/:gameId` -> `ReplayPage`
- 新增页面：
  - `frontend/src/pages/SetupPage.tsx`
  - `frontend/src/pages/ReplayPage.tsx`
- 新增组件：
  - `frontend/src/components/AgentStreamPanel.tsx`
- 状态管理：
  - `gameStore` 支持创建时传完整配置
  - 新增 `agentStream` 数据流

## 2. 关键接口

## 2.1 获取模型选项
`GET /games/agent-options`

返回：
```json
{
  "provider": "openai-compatible",
  "base_url": "https://openrouter.ai/api/v1",
  "models_checked_at": "2026-04-18",
  "model_options": ["..."]
}
```

## 2.2 创建对局（带 AI 配置）
`POST /games`

请求示例：
```json
{
  "game_id": "room-a",
  "room_name": "开放体验房",
  "max_rounds": 20,
  "seed": 20260418,
  "players": [
    {
      "player_id": "p1",
      "name": "玩家A",
      "is_agent": false,
      "agent_config": null
    },
    {
      "player_id": "p2",
      "name": "Agent-2",
      "is_agent": true,
      "agent_config": {
        "provider": "openai-compatible",
        "model": "openai/gpt-5",
        "base_url": "https://openrouter.ai/api/v1"
      }
    }
  ]
}
```

## 3. 配置文件说明
文件：`backend/config/openrouter_agent_config.template.json`

字段：
- `provider`
- `base_url`
- `api_key`
- `default_timeout_sec`
- `default_max_retries`
- `model_options`

可通过环境变量覆盖：
- `AGENT_OPTIONS_FILE`

## 4. 已验证项
- 后端单测：通过
- 后端 `ruff`：通过
- 后端 `mypy`：通过
- 前端 `build`：通过
- 前端 `vitest`：通过

## 5. 还需开发的任务清单
1. `SetupPage` 增加“从配置文件读取 API Key 状态”提示
2. 增加对 `agent_config` 的后端字段合法性校验（provider/model/base_url）
3. 增加 E2E 测试：配置页开局 -> 对局 -> 自动跳复盘
4. `AgentStreamPanel` 升级为 token 级流式显示（需后端 WS 流式事件）
5. 复盘页增加图表组件
6. 增加部署配置（生产 `VITE_API_BASE_URL` 与 CORS）

## 6. 风险点
- 若 `provider=openai-compatible` 且 `api_key` 为空，当前会自动 fallback，不会中断对局
- 模型下拉为“校验时可用”，后续可能因供应方变化失效
- 目前游戏状态为内存存储，服务重启后数据丢失
