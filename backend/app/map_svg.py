from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any

from app.map_engine import load_map_definition

_FILL_BY_TYPE = {
    "START": "#ffe8b5",
    "PROPERTY": "#d9ecff",
    "EMPTY": "#ecf2f9",
    "BANK": "#cdf7df",
    "EVENT": "#ffd6ec",
    "QUIZ": "#e7dcff",
}


def _owner_fill(owner_id: str) -> str:
    palette = [
        "#fde68a",
        "#bfdbfe",
        "#fecdd3",
        "#bbf7d0",
        "#ddd6fe",
        "#fdba74",
        "#a7f3d0",
        "#fbcfe8",
    ]
    idx = sum(ord(ch) for ch in owner_id) % len(palette)
    return palette[idx]


def _tile_center(tile: dict[str, Any]) -> tuple[float, float]:
    render = tile["render"]
    x = float(render["x"])
    y = float(render["y"])
    w = float(render["w"])
    h = float(render["h"])
    return x + (w / 2), y + (h / 2)


def _slot_points(tile: dict[str, Any], slots: int = 4) -> list[tuple[float, float]]:
    render = tile["render"]
    x = float(render["x"])
    y = float(render["y"])
    w = float(render["w"])
    h = float(render["h"])
    
    pad_x = min(w * 0.15, 14.0)
    pad_y = min(h * 0.15, 14.0)
    
    corners = [
        (x + pad_x, y + pad_y),               # Top-left
        (x + w - pad_x, y + pad_y),           # Top-right
        (x + pad_x, y + h - pad_y),           # Bottom-left
        (x + w - pad_x, y + h - pad_y),       # Bottom-right
    ]
    
    return corners[:slots]


def _scale_for_density(tiles: list[dict[str, Any]]) -> float:
    # 移除自适应缩放，因为依赖正确且宽裕的地图坐标配置
    # 让地块大小原汁原味，防止因缩放导致文本溢出或样式崩坏
    return 1.0


def _get_connection_sides(source_center: tuple[float, float], target_center: tuple[float, float]) -> tuple[str, str]:
    scx, scy = source_center
    tcx, tcy = target_center
    dx = tcx - scx
    dy = tcy - scy
    if abs(dx) >= abs(dy):
        if dx > 0:
            return "RIGHT", "LEFT"
        else:
            return "LEFT", "RIGHT"
    else:
        if dy > 0:
            return "BOTTOM", "TOP"
        else:
            return "TOP", "BOTTOM"

def _edge_path_d(
    sx: float, sy: float, s_side: str,
    ex: float, ey: float, t_side: str,
) -> str:
    # Distance
    dist = math.hypot(ex - sx, ey - sy)
    # Control point distance
    cp_dist = max(dist * 0.45, 20.0)
    
    if s_side == "RIGHT":
        cp1_x = sx + cp_dist
        cp1_y = sy
    elif s_side == "LEFT":
        cp1_x = sx - cp_dist
        cp1_y = sy
    elif s_side == "BOTTOM":
        cp1_x = sx
        cp1_y = sy + cp_dist
    elif s_side == "TOP":
        cp1_x = sx
        cp1_y = sy - cp_dist

    if t_side == "RIGHT":
        cp2_x = ex + cp_dist
        cp2_y = ey
    elif t_side == "LEFT":
        cp2_x = ex - cp_dist
        cp2_y = ey
    elif t_side == "BOTTOM":
        cp2_x = ex
        cp2_y = ey + cp_dist
    elif t_side == "TOP":
        cp2_x = ex
        cp2_y = ey - cp_dist
        
    return f"M {sx:.1f} {sy:.1f} C {cp1_x:.1f} {cp1_y:.1f} {cp2_x:.1f} {cp2_y:.1f} {ex:.1f} {ey:.1f}"


def _next_tile_ids(tile: dict[str, Any], ordered: list[dict[str, Any]]) -> list[str]:
    next_ids = tile.get("next_tile_ids")
    if isinstance(next_ids, list) and next_ids:
        return [str(item) for item in next_ids]
    tile_id = str(tile["tile_id"])
    for idx, row in enumerate(ordered):
        if str(row["tile_id"]) == tile_id:
            return [str(ordered[(idx + 1) % len(ordered)]["tile_id"])]
    return []


def render_map_svg(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    tiles = payload["tiles"]
    canvas = meta.get("canvas", {})
    width = int(canvas.get("width", 960))
    height = int(canvas.get("height", 560))
    map_id = str(meta.get("map_id", "default"))
    theme = str(meta.get("theme", "default"))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="map-{html.escape(map_id)}">',
        "  <defs>",
        '    <linearGradient id="bgGradient" x1="0%" y1="0%" x2="100%" y2="100%">',
        '      <stop offset="0%" stop-color="#fff7ed"/>',
        '      <stop offset="100%" stop-color="#eff6ff"/>',
        "    </linearGradient>",
        '    <filter id="tileShadow" x="-20%" y="-20%" width="140%" height="140%">',
        '      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.18"/>',
        "    </filter>",
        "  </defs>",
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#bgGradient)"/>',
        f'  <rect x="10" y="10" width="{width - 20}" height="{height - 20}" rx="16" ry="16" fill="none" stroke="#d6dbe7" stroke-width="2"/>',
    ]

    ordered_tiles = sorted(tiles, key=lambda item: int(item["tile_index"]))
    tile_by_id = {str(item["tile_id"]): item for item in tiles}
    
    # Pre-calculate sides for all edges to distribute them evenly
    edges = []
    outgoing: dict[str, list[str]] = {}
    for tile in ordered_tiles:
        tile_id = str(tile["tile_id"])
        next_ids = [item for item in _next_tile_ids(tile, ordered_tiles) if item in tile_by_id]
        outgoing[tile_id] = next_ids
        for target in next_ids:
            edges.append((tile_id, target))
            
    # For each tile, map side -> list of edges
    tile_sides = {str(tile["tile_id"]): {"TOP": [], "BOTTOM": [], "LEFT": [], "RIGHT": []} for tile in tiles}
    
    for src, tgt in edges:
        s_center = _tile_center(tile_by_id[src])
        t_center = _tile_center(tile_by_id[tgt])
        s_side, t_side = _get_connection_sides(s_center, t_center)
        tile_sides[src][s_side].append((src, tgt))
        tile_sides[tgt][t_side].append((src, tgt))

    lines.append('  <g id="track-layer">')
    for src, tgt in edges:
        source_tile = tile_by_id[src]
        target_tile = tile_by_id[tgt]
        s_center = _tile_center(source_tile)
        t_center = _tile_center(target_tile)
        s_side, t_side = _get_connection_sides(s_center, t_center)
        
        # Calculate spacing offsets for source
        s_side_edges = tile_sides[src][s_side]
        s_idx = s_side_edges.index((src, tgt))
        s_span = len(s_side_edges)
        s_bias = s_idx - ((s_span - 1) / 2)
        
        # Calculate spacing offsets for target
        t_side_edges = tile_sides[tgt][t_side]
        t_idx = t_side_edges.index((src, tgt))
        t_span = len(t_side_edges)
        t_bias = t_idx - ((t_span - 1) / 2)
        
        from_offset = s_bias * 18.0
        to_offset = t_bias * 18.0
        
        # Determine exact starting coordinate based on side
        sw = float(source_tile["render"]["w"])
        sh = float(source_tile["render"]["h"])
        scx, scy = s_center
        if s_side == "RIGHT":
            sx = scx + sw / 2
            sy = scy + from_offset
        elif s_side == "LEFT":
            sx = scx - sw / 2
            sy = scy + from_offset
        elif s_side == "BOTTOM":
            sx = scx + from_offset
            sy = scy + sh / 2
        elif s_side == "TOP":
            sx = scx + from_offset
            sy = scy - sh / 2
            
        # Determine exact ending coordinate based on side
        tw = float(target_tile["render"]["w"])
        th = float(target_tile["render"]["h"])
        tcx, tcy = t_center
        if t_side == "RIGHT":
            ex = tcx + tw / 2
            ey = tcy + to_offset
        elif t_side == "LEFT":
            ex = tcx - tw / 2
            ey = tcy + to_offset
        elif t_side == "BOTTOM":
            ex = tcx + to_offset
            ey = tcy + th / 2
        elif t_side == "TOP":
            ex = tcx + to_offset
            ey = tcy - th / 2
            
        edge_d = _edge_path_d(sx, sy, s_side, ex, ey, t_side)
        lines.append(
            f'    <path d="{edge_d}" fill="none" stroke="#dbeafe" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        lines.append(
            f'    <path d="{edge_d}" fill="none" stroke="#60a5fa" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"/>'
        )
    lines.append("  </g>")

    density_scale = _scale_for_density(tiles)
    for tile in tiles:
        tile_id = str(tile["tile_id"])
        tile_type = str(tile["tile_type"])
        render = tile["render"]
        x = float(render["x"])
        y = float(render["y"])
        w = float(render["w"])
        h = float(render["h"])
        owner_id = tile.get("owner_id")
        fill = _owner_fill(str(owner_id)) if owner_id else _FILL_BY_TYPE.get(tile_type, "#e5e7eb")
        draw_w = w * density_scale
        draw_h = h * density_scale
        draw_x = x + ((w - draw_w) / 2)
        draw_y = y + ((h - draw_h) / 2)
        name = html.escape(str(tile["name"]))
        label_type = html.escape(tile_type)
        center_x = draw_x + (draw_w / 2)
        slots = _slot_points(tile, slots=4)
        slots_attr = ";".join(f"{sx:.1f},{sy:.1f}" for sx, sy in slots)

        lines.extend(
            [
                f'  <g id="tile-{html.escape(tile_id)}" data-tile-id="{html.escape(tile_id)}" data-tile-index="{tile["tile_index"]}" data-owner-id="{html.escape(str(owner_id or ""))}" data-token-slots="{slots_attr}">',
                f'    <rect x="{draw_x:.1f}" y="{draw_y:.1f}" rx="10" ry="10" width="{draw_w:.1f}" height="{draw_h:.1f}" fill="{fill}" stroke="#0f172a" stroke-width="2" filter="url(#tileShadow)"/>',
                f'    <text x="{center_x:.1f}" y="{draw_y + draw_h * 0.42:.1f}" text-anchor="middle" fill="#0f172a" font-size="12" font-family="Segoe UI, Arial" font-weight="bold">{label_type}</text>',
                f'    <text x="{center_x:.1f}" y="{draw_y + draw_h * 0.62:.1f}" text-anchor="middle" fill="#111827" font-size="15" font-family="Segoe UI, Arial">{name}</text>',
                "  </g>",
            ]
        )
        for sx, sy in slots:
            lines.append(f'  <circle cx="{sx:.1f}" cy="{sy:.1f}" r="4.5" fill="#ffffff" stroke="#64748b" stroke-width="1" opacity="0.9"/>')

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def generate_svg_file(map_json_path: Path, out_svg_path: Path) -> None:
    payload = load_map_definition(map_json_path)
    out_svg_path.parent.mkdir(parents=True, exist_ok=True)
    out_svg_path.write_text(render_map_svg(payload), encoding="utf-8")
