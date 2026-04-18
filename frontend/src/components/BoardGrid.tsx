import { useEffect, useMemo, useRef, useState, type CSSProperties, type FC } from "react";

import type { GameState, TileState } from "../types/game";

type Props = {
  state: GameState;
};

type Slot = { x: number; y: number };
type BoardViewBox = { x: number; y: number; width: number; height: number };
type TileLayout = {
  tileId: string;
  tileIndex: number;
  centerX: number;
  centerY: number;
  width: number;
  height: number;
  slots: Slot[];
};

const TOKEN_PALETTE = [
  { solid: "#1667d9", glow: "rgba(22, 103, 217, 0.22)" },
  { solid: "#d84c2f", glow: "rgba(216, 76, 47, 0.24)" },
  { solid: "#117a65", glow: "rgba(17, 122, 101, 0.24)" },
  { solid: "#d99614", glow: "rgba(217, 150, 20, 0.24)" },
  { solid: "#8b5cf6", glow: "rgba(139, 92, 246, 0.22)" },
  { solid: "#0f766e", glow: "rgba(15, 118, 110, 0.24)" },
] as const;

const DEFAULT_VIEWBOX: BoardViewBox = { x: 0, y: 0, width: 940, height: 560 };

function parseSlots(raw: string | null): Slot[] {
  if (!raw) {
    return [];
  }
  const rows = raw.split(";").map((item) => item.trim()).filter(Boolean);
  return rows
    .map((row) => {
      const [xs, ys] = row.split(",");
      const x = Number(xs);
      const y = Number(ys);
      return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
    })
    .filter((item): item is Slot => Boolean(item));
}

function readNumber(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseViewBox(value: string | null): BoardViewBox {
  if (!value) {
    return DEFAULT_VIEWBOX;
  }
  const parts = value.split(/\s+/).map((item) => Number(item));
  if (parts.length !== 4 || parts.some((item) => !Number.isFinite(item))) {
    return DEFAULT_VIEWBOX;
  }
  return {
    x: parts[0] ?? DEFAULT_VIEWBOX.x,
    y: parts[1] ?? DEFAULT_VIEWBOX.y,
    width: parts[2] ?? DEFAULT_VIEWBOX.width,
    height: parts[3] ?? DEFAULT_VIEWBOX.height,
  };
}

function getTokenOffset(index: number, total: number): { x: number; y: number } {
  const presets: Record<number, readonly { x: number; y: number }[]> = {
    1: [{ x: 0, y: 0 }],
    2: [
      { x: -13, y: -10 },
      { x: 13, y: 10 },
    ],
    3: [
      { x: 0, y: -14 },
      { x: -14, y: 11 },
      { x: 14, y: 11 },
    ],
    4: [
      { x: -13, y: -11 },
      { x: 13, y: -11 },
      { x: -13, y: 11 },
      { x: 13, y: 11 },
    ],
    5: [
      { x: 0, y: 0 },
      { x: -14, y: -14 },
      { x: 14, y: -14 },
      { x: -14, y: 14 },
      { x: 14, y: 14 },
    ],
  };
  const fallback = [
    { x: -16, y: -16 },
    { x: 0, y: -16 },
    { x: 16, y: -16 },
    { x: -16, y: 16 },
    { x: 0, y: 16 },
    { x: 16, y: 16 },
  ] as const;
  const layout = presets[Math.min(total, 5)] ?? fallback;
  return layout[index] ?? fallback[index % fallback.length] ?? { x: 0, y: 0 };
}

function tileExplain(tile: TileState, ownerName: string | null): string {
  switch (tile.tile_type) {
    case "PROPERTY":
      return ownerName
        ? `当前归属 ${ownerName}，地价 ${tile.property_price ?? "-"}，过路费 ${tile.toll ?? "-"}。`
        : `当前无人持有，地价 ${tile.property_price ?? "-"}，可评估买入。`;
    case "EVENT":
      return "触发事件格，收益和风险都会波动。";
    case "BANK":
      return "银行格，可能触发金融相关结算。";
    case "START":
      return "起点格，通常和基础奖励相关。";
    default:
      return "普通格，按当前规则执行结算。";
  }
}

function extractPathArray(payload: Record<string, unknown>): number[] {
  const keys = ["path_position_indexes", "path", "positions", "tile_indexes", "movement_path"];
  for (const key of keys) {
    const value = payload[key];
    if (!Array.isArray(value)) {
      continue;
    }
    const numbers = value
      .map((item) => Number(item))
      .filter((item) => Number.isFinite(item))
      .map((item) => Math.trunc(item));
    if (numbers.length > 0) {
      return numbers;
    }
  }
  return [];
}

function extractPoint(payload: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const raw = payload[key];
    const value = Number(raw);
    if (Number.isFinite(value)) {
      return Math.trunc(value);
    }
  }
  return null;
}

function buildPathByRange(fromIndex: number, toIndex: number, total: number): number[] {
  if (total <= 0) {
    return [];
  }
  const path: number[] = [];
  let cursor = ((fromIndex % total) + total) % total;
  const target = ((toIndex % total) + total) % total;
  path.push(cursor);
  while (cursor !== target) {
    cursor = (cursor + 1) % total;
    path.push(cursor);
    if (path.length > total + 1) {
      break;
    }
  }
  return path;
}

function derivePathIndexes(state: GameState): number[] {
  const events = [...state.last_events].reverse();
  const boardSize = state.board.length;
  for (const event of events) {
    const payload = event.payload && typeof event.payload === "object" ? (event.payload as Record<string, unknown>) : {};
    const directPath = extractPathArray(payload);
    if (directPath.length > 0) {
      return directPath;
    }

    const fromIndex = extractPoint(payload, [
      "from_position_index",
      "from_position",
      "position_from",
      "start_position_index",
      "old_position",
      "source_position",
    ]);
    const toIndex = extractPoint(payload, [
      "to_position_index",
      "to_position",
      "position_index",
      "new_position",
      "target_position",
      "destination_position",
    ]);
    if (fromIndex !== null && toIndex !== null) {
      return buildPathByRange(fromIndex, toIndex, boardSize);
    }
  }
  return [];
}

function projectSvgPoint(
  layout: TileLayout,
  viewBox: BoardViewBox,
  widthPx: number,
  heightPx: number,
): { centerX: number; centerY: number; width: number; height: number; slots: Slot[] } {
  const scaleX = widthPx / viewBox.width;
  const scaleY = heightPx / viewBox.height;
  return {
    centerX: (layout.centerX - viewBox.x) * scaleX,
    centerY: (layout.centerY - viewBox.y) * scaleY,
    width: layout.width * scaleX,
    height: layout.height * scaleY,
    slots: layout.slots.map((slot) => ({
      x: (slot.x - viewBox.x) * scaleX,
      y: (slot.y - viewBox.y) * scaleY,
    })),
  };
}

export const BoardGrid: FC<Props> = ({ state }) => {
  const mapAsset = useMemo(() => {
    if (state.map_asset && state.map_asset.trim().length > 0) {
      return state.map_asset.trim();
    }
    if (typeof window !== "undefined") {
      return localStorage.getItem("am-map-theme") || "default";
    }
    return "default";
  }, [state.map_asset]);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [rawSvg, setRawSvg] = useState<string>("");
  const [svgError, setSvgError] = useState<string>("");
  const [hoveredTileId, setHoveredTileId] = useState<string | null>(null);
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = stageRef.current;
    if (!element) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      setStageSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const response = await fetch(`/maps/${mapAsset}.svg`, { cache: "no-cache" });
        if (!response.ok) {
          throw new Error(`load map failed: ${response.status}`);
        }
        const text = await response.text();
        if (!alive) {
          return;
        }
        setRawSvg(text);
        setSvgError("");
      } catch (error) {
        if (!alive) {
          return;
        }
        setSvgError(String(error));
      }
    })();
    return () => {
      alive = false;
    };
  }, [mapAsset]);

  const playersByTile = useMemo(() => {
    const map = new Map<number, GameState["players"]>();
    for (const player of state.players) {
      const bucket = map.get(player.position) ?? [];
      bucket.push(player);
      map.set(player.position, bucket);
    }
    return map;
  }, [state.players]);

  const playerNameMap = useMemo(() => {
    return state.players.reduce<Record<string, string>>((acc, player) => {
      acc[player.player_id] = player.name || player.player_id;
      return acc;
    }, {});
  }, [state.players]);

  const boardByTileId = useMemo(() => {
    return new Map(state.board.map((tile) => [tile.tile_id, tile]));
  }, [state.board]);

  const pathTileIds = useMemo(() => {
    const indexes = derivePathIndexes(state);
    const indexToId = new Map(state.board.map((tile) => [tile.tile_index, tile.tile_id]));
    return new Set(indexes.map((index) => indexToId.get(index)).filter((id): id is string => Boolean(id)));
  }, [state]);

  const parsedMap = useMemo(() => {
    if (!rawSvg) {
      return {
        renderedSvg: "",
        viewBox: DEFAULT_VIEWBOX,
        layouts: [] as TileLayout[],
      };
    }

    const parser = new DOMParser();
    const doc = parser.parseFromString(rawSvg, "image/svg+xml");
    const svg = doc.querySelector("svg");
    if (!svg) {
      return {
        renderedSvg: rawSvg,
        viewBox: DEFAULT_VIEWBOX,
        layouts: [] as TileLayout[],
      };
    }

    for (const old of doc.querySelectorAll(".runtime-token")) {
      old.remove();
    }

    const viewBox = parseViewBox(svg.getAttribute("viewBox"));
    const layouts: TileLayout[] = [];

    for (const tile of state.board) {
      const group = doc.querySelector(`#tile-${tile.tile_id}`) as SVGGElement | null;
      if (!group) {
        continue;
      }
      const rect = group.querySelector("rect");
      if (!rect) {
        continue;
      }

      const x = readNumber(rect.getAttribute("x")) ?? 0;
      const y = readNumber(rect.getAttribute("y")) ?? 0;
      const width = readNumber(rect.getAttribute("width")) ?? 64;
      const height = readNumber(rect.getAttribute("height")) ?? 64;
      const slots = parseSlots(group.getAttribute("data-token-slots"));

      layouts.push({
        tileId: tile.tile_id,
        tileIndex: tile.tile_index,
        centerX: x + width / 2,
        centerY: y + height / 2,
        width,
        height,
        slots,
      });

      const title = doc.createElementNS("http://www.w3.org/2000/svg", "title");
      const ownerName = tile.owner_id ? (playerNameMap[tile.owner_id] ?? tile.owner_id) : "none";
      title.textContent = `${tile.name} | ${tile.tile_type} | owner=${ownerName}`;
      group.appendChild(title);

      group.classList.add("map-runtime-tile");
      if (tile.tile_type === "EVENT") {
        group.classList.add("map-runtime-event");
      }
      if (tile.owner_id) {
        group.classList.add("map-runtime-owned");
      }
      if (pathTileIds.has(tile.tile_id)) {
        group.classList.add("map-runtime-path");
      }
      if (tile.tile_id === state.active_tile_id) {
        group.classList.add("map-runtime-active");
      }
      if (tile.tile_id === state.active_tile_id && state.human_wait_reason === "branch_decision") {
        group.classList.add("map-runtime-decision");
      }
    }

    const hasLayouts = layouts.length > 0;
    const computedViewBox = hasLayouts
      ? (() => {
          const minX = Math.min(...layouts.map((layout) => layout.centerX - layout.width / 2));
          const minY = Math.min(...layouts.map((layout) => layout.centerY - layout.height / 2));
          const maxX = Math.max(...layouts.map((layout) => layout.centerX + layout.width / 2));
          const maxY = Math.max(...layouts.map((layout) => layout.centerY + layout.height / 2));
          const padX = Math.max((maxX - minX) * 0.08, 24);
          const padY = Math.max((maxY - minY) * 0.12, 24);
          return {
            x: minX - padX,
            y: minY - padY,
            width: maxX - minX + padX * 2,
            height: maxY - minY + padY * 2,
          } satisfies BoardViewBox;
        })()
      : viewBox;
    svg.setAttribute(
      "viewBox",
      `${computedViewBox.x} ${computedViewBox.y} ${computedViewBox.width} ${computedViewBox.height}`,
    );

    const style = doc.createElementNS("http://www.w3.org/2000/svg", "style");
    style.textContent = `
      .map-runtime-tile rect { transition: transform .16s ease, filter .16s ease, stroke-width .16s ease; transform-origin: center; }
      .map-runtime-tile text:nth-of-type(3) { opacity: 0.38; transition: opacity .14s ease; }
      .map-runtime-tile:hover rect { transform: translateY(-1px); filter: drop-shadow(0 8px 8px rgba(46, 27, 0, 0.22)); }
      .map-runtime-tile:hover text:nth-of-type(3) { opacity: 1; }
      .map-runtime-active rect { stroke: #c66d14 !important; stroke-width: 3 !important; }
      .map-runtime-owned rect { filter: drop-shadow(0 0 8px rgba(42,108,176,0.35)); }
      .map-runtime-event rect { fill: #ffe4f3 !important; }
      .map-runtime-path rect { stroke: #2f6fd6 !important; stroke-width: 3 !important; }
      .map-runtime-decision rect { stroke-dasharray: 6 3; }
    `;
    svg.appendChild(style);

    return {
      renderedSvg: new XMLSerializer().serializeToString(svg),
      viewBox: computedViewBox,
      layouts,
    };
  }, [rawSvg, state, pathTileIds, playerNameMap]);

  const layoutMap = useMemo(() => {
    return new Map(parsedMap.layouts.map((layout) => [layout.tileId, layout]));
  }, [parsedMap.layouts]);

  const hoverTile = hoveredTileId ? boardByTileId.get(hoveredTileId) ?? null : null;
  const hoverLayout = hoveredTileId ? layoutMap.get(hoveredTileId) ?? null : null;

  const hoverCardStyle = useMemo(() => {
    if (!hoverLayout || stageSize.width <= 0 || stageSize.height <= 0) {
      return null;
    }
    const projected = projectSvgPoint(hoverLayout, parsedMap.viewBox, stageSize.width, stageSize.height);
    const normalizedY = projected.centerY / Math.max(stageSize.height, 1);
    const isTop = normalizedY <= 0.48;
    return {
      left: `${projected.centerX}px`,
      top: `${projected.centerY + (isTop ? Math.max(projected.height * 0.28, 14) : -Math.max(projected.height * 0.32, 16))}px`,
      transform: `translate(-50%, ${isTop ? "0" : "-100%"})`,
    } as CSSProperties;
  }, [hoverLayout, parsedMap.viewBox, stageSize.height, stageSize.width]);

  return (
    <section className={`panel board-panel board-theme-${mapAsset}`}>
      <div className="panel-title-row">
        <h2>棋盘战场</h2>
        <div className="tiny-note">当前格：{state.active_tile_id} · 地图：{mapAsset}</div>
      </div>
      {svgError ? (
        <div className="board-fallback">
          <p className="error-text">地图加载失败，已降级展示：{svgError}</p>
          <div className="board-fallback-grid">
            {state.board.map((tile) => (
              <span key={tile.tile_id} className={tile.tile_id === state.active_tile_id ? "fallback-active" : ""}>
                {tile.tile_id}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <div ref={stageRef} className="board-stage svg-map-stage board-stage-runtime">
          <div className="board-svg-layer" dangerouslySetInnerHTML={{ __html: parsedMap.renderedSvg || rawSvg }} />

          <div className="board-token-layer" aria-hidden="true">
            {parsedMap.layouts.flatMap((layout) => {
              const players = playersByTile.get(layout.tileIndex) ?? [];
              if (players.length === 0 || stageSize.width <= 0 || stageSize.height <= 0) {
                return [];
              }
              const projected = projectSvgPoint(layout, parsedMap.viewBox, stageSize.width, stageSize.height);
              return players.map((player, index) => {
                const accent = TOKEN_PALETTE[index % TOKEN_PALETTE.length] ?? TOKEN_PALETTE[0];
                const total = players.length;
                const offset = getTokenOffset(index, total);
                const slot = projected.slots[index] ?? projected.slots[projected.slots.length - 1];
                const left = slot ? slot.x : projected.centerX + offset.x;
                const top = slot ? slot.y : projected.centerY + offset.y;
                const style = {
                  left: `${left}px`,
                  top: `${top}px`,
                  transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px))`,
                  ["--piece-color" as string]: accent.solid,
                  ["--piece-glow" as string]: accent.glow,
                } as CSSProperties;
                const isFocus = player.player_id === state.current_player_id;
                return (
                  <span
                    key={`${layout.tileId}-${player.player_id}`}
                    className={[
                      "board-token",
                      isFocus ? "board-token--focus" : "",
                      !player.alive ? "board-token--bankrupt" : "",
                    ]
                      .join(" ")
                      .trim()}
                    style={style}
                  >
                    <span>{player.name?.slice(0, 1) || player.player_id.slice(0, 1)}</span>
                  </span>
                );
              });
            })}
          </div>

          <div className="board-hotspot-layer">
            {parsedMap.layouts.map((layout) => {
              if (stageSize.width <= 0 || stageSize.height <= 0) {
                return null;
              }
              const projected = projectSvgPoint(layout, parsedMap.viewBox, stageSize.width, stageSize.height);
              const tile = boardByTileId.get(layout.tileId);
              if (!tile) {
                return null;
              }
              const isPath = pathTileIds.has(layout.tileId);
              const isActive = tile.tile_id === state.active_tile_id;
              return (
                <button
                  key={`hotspot-${layout.tileId}`}
                  type="button"
                  className={[
                    "board-hotspot",
                    isPath ? "board-hotspot--path" : "",
                    isActive ? "board-hotspot--active" : "",
                  ]
                    .join(" ")
                    .trim()}
                  style={{
                    left: `${projected.centerX}px`,
                    top: `${projected.centerY}px`,
                    width: `${projected.width}px`,
                    height: `${projected.height}px`,
                  }}
                  aria-label={`查看格子：${tile.name}`}
                  onMouseEnter={() => setHoveredTileId(layout.tileId)}
                  onFocus={() => setHoveredTileId(layout.tileId)}
                  onMouseLeave={() => setHoveredTileId((current) => (current === layout.tileId ? null : current))}
                  onBlur={() => setHoveredTileId((current) => (current === layout.tileId ? null : current))}
                />
              );
            })}
          </div>

          {hoverTile && hoverCardStyle ? (
            <div className="board-tile-toast" style={hoverCardStyle} role="status" aria-live="polite">
              <p className="board-tile-toast__kicker">
                {String(hoverTile.tile_index).padStart(2, "0")} · {hoverTile.tile_type}
              </p>
              <strong>{hoverTile.name}</strong>
              <p>owner：{hoverTile.owner_id ? playerNameMap[hoverTile.owner_id] ?? hoverTile.owner_id : "无"}</p>
              <p>{tileExplain(hoverTile, hoverTile.owner_id ? playerNameMap[hoverTile.owner_id] ?? hoverTile.owner_id : null)}</p>
            </div>
          ) : null}
        </div>
      )}
      <div className="board-legend">
        <span className="legend-item legend-active">当前落点</span>
        <span className="legend-item legend-path">行动路径</span>
        <span className="legend-item legend-event">事件格</span>
        <span className="legend-item legend-owned">已有归属</span>
        <span className="legend-item legend-token-focus">当前玩家</span>
        <span className="legend-item legend-token-bankrupt">破产玩家</span>
        {state.human_wait_reason === "branch_decision" ? <span className="legend-item legend-decision">真人决策点</span> : null}
      </div>
    </section>
  );
};
