# 程序员B已完成文档：地图生成引擎设计（v2.2）

## 1. 目标与范围

本设计文档对应 B2-1 到 B2-8，目标是在不改动现有前端页面业务流程的前提下，完成可落地的地图生成引擎方案设计，支持后续逐步实施。

本次仅完成设计，不直接改造 UI 页面与业务逻辑。

设计原则：
- 低耦合：地图资源、地图渲染、游戏规则分层。
- 可替换：地图主题切换不影响后端结算逻辑。
- 可回退：新渲染失败时可退回现有 grid 展示，保证可运行。
- 单一事实源：规则数据以后端输出为准，前端不重复计算结算。

## 2. 总体架构

采用三层结构：

1. JSON 配置层（静态数据）
- 文件：`backend/config/maps/board.default.json`
- 职责：定义地块顺序、类型、经济字段、布局坐标、视觉主题参数。

2. 静态底图层（构建产物）
- 生成脚本：`backend/scripts/generate_map_svg.py`（或 `frontend/scripts/generate-map-svg.ts`）
- 输出资源：`frontend/public/maps/default.svg`
- 职责：把 JSON 转成风格化底图，承载背景视觉与地块基础形状。

3. 动态交互层（运行时渲染）
- 建议组件：`frontend/src/components/map/MapStage.tsx`
- 职责：绘制玩家棋子、激活地块高亮、地产归属颜色、hover/click 信息。

边界约束：
- 后端负责规则状态（`board`、`players`、`active_tile_id`）。
- 前端负责表现层状态映射（颜色、位置、动画、面板）。

## 3. B2-1 到 B2-8 设计明细

### B2-1 地图配置抽象为 JSON

建议 Schema（核心字段）：

```json
{
  "meta": {
    "map_id": "default",
    "track_length": 16,
    "theme": "city-night",
    "version": "1.0.0"
  },
  "tiles": [
    {
      "tile_id": "T00",
      "tile_index": 0,
      "name": "Start",
      "tile_type": "START",
      "property_price": null,
      "toll": null,
      "event_key": null,
      "render": {
        "x": 40,
        "y": 40,
        "w": 120,
        "h": 90,
        "rotation": 0,
        "label_anchor": "center"
      }
    }
  ]
}
```

字段规则：
- `tile_id` 全局唯一。
- `tile_index` 必须从 `0` 连续到 `track_length - 1`。
- 规则字段与当前后端 `Tile` 模型对齐：`tile_type/property_price/toll/event_key`。
- `render` 仅用于视觉，不参与后端结算。

### B2-2 JSON 校验器

校验建议分两层：
- 构建期校验：脚本生成 SVG 前进行，失败即退出并报错。
- 运行期校验：前端加载 map 资源时做轻校验，失败时降级到 grid。

校验项最小集：
- 唯一性：`tile_id` 不重复。
- 完整性：`tile_index` 连续无缺口。
- 一致性：`track_length === tiles.length`。
- 边界性：`render.x/y/w/h` 在画布边界内。
- 类型性：`tile_type` 必须属于允许集合。

### B2-3 自动生成风格化底图

生成流程：
1. 读取 `board.default.json`。
2. 按 `render` 字段绘制每个 tile 的 SVG 节点。
3. 按 `tile_type` 应用主题颜色、纹理、角标。
4. 输出 `default.svg` 到 `frontend/public/maps/`。

输出要求：
- 每个地块节点带稳定 id：`id="tile-T00"`。
- 文本标签可读（最小字号阈值 12）。
- 画布尺寸固定（例如 `1280x720`）便于前端缩放。

### B2-4 前端动态交互层

`MapStage` 拆层建议：
- 底层：SVG 背景图（静态）。
- 中层：地块状态覆盖层（owner 边框、可点击区域）。
- 顶层：玩家棋子与当前回合高亮。

最小动态能力：
- `active_tile_id` 高亮。
- 地产归属按 `owner_id` 着色。
- 玩家位置根据 `player.position -> tile_index` 映射显示。

### B2-5 状态映射器（避免规则耦合）

新增纯函数适配层（建议）：
- `mapStateToRenderModel(gameState, mapMeta) -> renderModel`

职责：
- 把后端状态转为前端渲染坐标与样式信息。
- 不做任何经济计算和规则推导。
- 不修改后端返回数据。

### B2-6 交互行为设计

交互定义：
- `hover`：显示地块悬浮信息（名称、类型、价格、租金、owner）。
- `click`：锁定侧边详情面板。
- `keyboard`（可选）：左右切换地块焦点，提升可访问性。

事件约束：
- 交互只读，不直接触发后端规则动作。
- 动作提交仍走既有动作面板与 API。

### B2-7 稳健性与降级

必须具备：
- SVG 资源加载失败时自动降级到现有 `BoardGrid`。
- map JSON 校验失败时写入前端错误日志并降级。
- 后端 state 字段缺失时用安全默认值渲染，不让页面白屏。

可观测性：
- 记录地图加载耗时、渲染错误次数、降级次数。

### B2-8 验收与样例

样例要求：
- `board.default.json`：当前 16 格默认地图。
- `board.theme2.json`：同规则字段、不同视觉布局主题。

验收标准：
- 不改前端业务代码即可切换主题资源。
- 不改后端规则代码即可加载不同视觉地图。
- 地图层崩溃不影响游戏主流程（有降级兜底）。

## 4. 目录与文件规划

建议新增：
- `backend/config/maps/board.default.json`
- `backend/config/maps/board.theme2.json`
- `backend/scripts/generate_map_svg.py`
- `frontend/public/maps/default.svg`
- `frontend/public/maps/theme2.svg`
- `frontend/src/components/map/MapStage.tsx`
- `frontend/src/components/map/mapAdapter.ts`
- `frontend/src/components/map/mapTypes.ts`

说明：
- 其中前端组件文件属于后续实施目标，本次文档设计不直接改动页面。

## 5. 兼容当前项目的实施策略

分阶段实施，降低风险：

阶段 1（安全引入）：
- 先落地 JSON 与 SVG 生成脚本。
- 不替换现有 `BoardGrid`，只新增并行组件。

阶段 2（可控切换）：
- 增加特性开关 `VITE_MAP_RENDERER=svg|grid`。
- 默认 `grid`，开发环境先验证 `svg`。

阶段 3（默认启用）：
- 稳定后将默认渲染器切到 `svg`。
- 保留 `grid` 作为长期兜底。

## 6. 风险与规避

主要风险：
- JSON 与后端规则字段漂移。
- 自定义布局导致棋子重叠和可读性下降。
- SVG 资源过大导致首屏慢。

规避措施：
- 为 JSON 增加版本号和 schema 校验。
- 约束最小间距与 tile 尺寸阈值。
- 生成阶段做 SVG 压缩并限制资源体积。

## 7. 完成定义（Design Done）

本设计文档完成后，即视为 B2-1 到 B2-8 的“设计阶段完成”，判定条件：
- 结构方案明确（三层架构、边界清晰）。
- 数据合同明确（JSON schema 与状态映射职责明确）。
- 稳健性策略明确（降级、容错、可观测）。
- 实施路径明确（分阶段切换，不破坏现有可运行性）。

