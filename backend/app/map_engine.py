from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALLOWED_TILE_TYPES = {"START", "PROPERTY", "EMPTY", "BANK", "EVENT", "QUIZ"}
DEFAULT_MAP_PATH = Path(__file__).resolve().parents[1] / "config" / "maps" / "board.01_basic_loop.json"


def default_map_path() -> Path:
    return DEFAULT_MAP_PATH


def load_map_definition(path: Path | None = None) -> dict[str, Any]:
    map_path = path or DEFAULT_MAP_PATH
    payload = json.loads(map_path.read_text(encoding="utf-8"))
    validate_map_definition(payload)
    return payload


def validate_map_definition(payload: dict[str, Any]) -> None:
    meta = payload.get("meta")
    tiles = payload.get("tiles")
    if not isinstance(meta, dict):
        raise ValueError("map.meta must be an object")
    if not isinstance(tiles, list) or not tiles:
        raise ValueError("map.tiles must be a non-empty list")

    track_length = meta.get("track_length")
    if not isinstance(track_length, int) or track_length <= 0:
        raise ValueError("map.meta.track_length must be a positive int")
    if track_length != len(tiles):
        raise ValueError("map.meta.track_length must match tiles length")

    tile_ids: set[str] = set()
    indices: list[int] = []
    for index, tile in enumerate(tiles):
        if not isinstance(tile, dict):
            raise ValueError(f"map.tiles[{index}] must be an object")

        tile_id = tile.get("tile_id")
        tile_index = tile.get("tile_index")
        tile_type = tile.get("tile_type")
        name = tile.get("name")
        render = tile.get("render")

        if not isinstance(tile_id, str) or not tile_id:
            raise ValueError(f"map.tiles[{index}].tile_id must be non-empty string")
        if tile_id in tile_ids:
            raise ValueError(f"duplicate tile_id: {tile_id}")
        tile_ids.add(tile_id)

        if not isinstance(tile_index, int):
            raise ValueError(f"map.tiles[{index}].tile_index must be int")
        indices.append(tile_index)

        if not isinstance(tile_type, str) or tile_type not in ALLOWED_TILE_TYPES:
            raise ValueError(f"map.tiles[{index}].tile_type is invalid: {tile_type}")
        if not isinstance(name, str) or not name:
            raise ValueError(f"map.tiles[{index}].name must be non-empty string")

        if not isinstance(render, dict):
            raise ValueError(f"map.tiles[{index}].render must be an object")
        for key in ("x", "y", "w", "h"):
            value = render.get(key)
            if not isinstance(value, (int, float)):
                raise ValueError(f"map.tiles[{index}].render.{key} must be number")

    expected = list(range(track_length))
    if sorted(indices) != expected:
        raise ValueError("tile_index must be continuous from 0 to track_length - 1")

    tile_id_set = set(tile_ids)
    start_tile_id = meta.get("start_tile_id")
    if start_tile_id is not None:
        if not isinstance(start_tile_id, str) or not start_tile_id:
            raise ValueError("map.meta.start_tile_id must be non-empty string when provided")
        if start_tile_id not in tile_id_set:
            raise ValueError(f"map.meta.start_tile_id not found in tiles: {start_tile_id}")

    for index, tile in enumerate(tiles):
        next_tile_ids = tile.get("next_tile_ids")
        if next_tile_ids is None:
            continue
        if not isinstance(next_tile_ids, list) or not next_tile_ids:
            raise ValueError(f"map.tiles[{index}].next_tile_ids must be non-empty list when provided")
        seen_next: set[str] = set()
        for next_tile_id in next_tile_ids:
            if not isinstance(next_tile_id, str) or not next_tile_id:
                raise ValueError(f"map.tiles[{index}].next_tile_ids contains invalid tile id")
            if next_tile_id in seen_next:
                raise ValueError(f"map.tiles[{index}].next_tile_ids contains duplicate: {next_tile_id}")
            if next_tile_id not in tile_id_set:
                raise ValueError(f"map.tiles[{index}].next_tile_ids references unknown tile: {next_tile_id}")
            seen_next.add(next_tile_id)


def load_runtime_board(path: Path | None = None) -> list[dict[str, Any]]:
    payload = load_map_definition(path)
    rows: list[dict[str, Any]] = []
    for tile in payload["tiles"]:
        rows.append(
            {
                "tile_id": tile["tile_id"],
                "tile_index": tile["tile_index"],
                "tile_type": tile["tile_type"],
                "tile_subtype": tile.get("tile_subtype", tile["tile_type"]),
                "name": tile["name"],
                "property_price": tile.get("property_price"),
                "toll": tile.get("toll"),
                "event_key": tile.get("event_key"),
                "quiz_key": tile.get("quiz_key"),
                "next_tile_ids": tile.get("next_tile_ids"),
            }
        )
    return rows
