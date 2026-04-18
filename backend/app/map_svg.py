from __future__ import annotations

import html
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
    cx = x + (w / 2)
    cy = y + (h * 0.78)
    if slots <= 1:
        return [(cx, cy)]
    gap = min(max(w * 0.14, 16.0), 28.0)
    total = gap * (slots - 1)
    start = cx - (total / 2)
    return [(start + (i * gap), cy) for i in range(slots)]


def _track_path_points(tiles: list[dict[str, Any]]) -> list[tuple[float, float]]:
    ordered = sorted(tiles, key=lambda item: int(item["tile_index"]))
    points = [_tile_center(tile) for tile in ordered]
    if points:
        points.append(points[0])
    return points


def _smooth_path_d(points: list[tuple[float, float]]) -> str:
    if len(points) < 2:
        return ""
    d = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for idx in range(1, len(points)):
        x0, y0 = points[idx - 1]
        x1, y1 = points[idx]
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        d.append(f"Q {cx:.1f} {cy:.1f} {x1:.1f} {y1:.1f}")
    return " ".join(d)


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
        f'  <text x="{width // 2}" y="30" text-anchor="middle" fill="#334155" font-size="16" font-family="Segoe UI, Arial">{html.escape(map_id)} / {html.escape(theme)}</text>',
    ]

    path_points = _track_path_points(tiles)
    path_d = _smooth_path_d(path_points)
    if path_d:
        lines.extend(
            [
                '  <g id="track-layer">',
                f'    <path d="{path_d}" fill="none" stroke="#dbeafe" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>',
                f'    <path d="{path_d}" fill="none" stroke="#60a5fa" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>',
                "  </g>",
            ]
        )

    for tile in tiles:
        tile_id = str(tile["tile_id"])
        tile_type = str(tile["tile_type"])
        render = tile["render"]
        x = float(render["x"])
        y = float(render["y"])
        w = float(render["w"])
        h = float(render["h"])
        fill = _FILL_BY_TYPE.get(tile_type, "#e5e7eb")
        name = html.escape(str(tile["name"]))
        label_type = html.escape(tile_type)
        price = tile.get("property_price")
        toll = tile.get("toll")
        extra = f"price={price if price is not None else '-'} toll={toll if toll is not None else '-'}"
        extra = html.escape(extra)
        center_x = x + (w / 2)
        slots = _slot_points(tile, slots=4)
        slots_attr = ";".join(f"{sx:.1f},{sy:.1f}" for sx, sy in slots)

        lines.extend(
            [
                f'  <g id="tile-{html.escape(tile_id)}" data-tile-id="{html.escape(tile_id)}" data-tile-index="{tile["tile_index"]}" data-token-slots="{slots_attr}">',
                f'    <rect x="{x:.1f}" y="{y:.1f}" rx="10" ry="10" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="#0f172a" stroke-width="2" filter="url(#tileShadow)"/>',
                f'    <text x="{center_x:.1f}" y="{y + 24:.1f}" text-anchor="middle" fill="#0f172a" font-size="12" font-family="Segoe UI, Arial">{html.escape(tile_id)} · {label_type}</text>',
                f'    <text x="{center_x:.1f}" y="{y + 48:.1f}" text-anchor="middle" fill="#111827" font-size="14" font-family="Segoe UI, Arial">{name}</text>',
                f'    <text x="{center_x:.1f}" y="{y + 68:.1f}" text-anchor="middle" fill="#334155" font-size="11" font-family="Consolas, monospace">{extra}</text>',
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
