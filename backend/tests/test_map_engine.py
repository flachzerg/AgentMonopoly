from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.game_engine import build_default_board
from app.map_engine import default_map_path, load_map_definition, load_runtime_board, validate_map_definition


class MapEngineTestCase(unittest.TestCase):
    def test_load_default_map_definition(self) -> None:
        payload = load_map_definition(default_map_path())
        self.assertEqual(payload["meta"]["map_id"], "loop16")
        self.assertEqual(payload["meta"]["track_length"], 16)
        self.assertEqual(len(payload["tiles"]), 16)

    def test_runtime_board_has_continuous_indexes(self) -> None:
        rows = load_runtime_board()
        self.assertEqual(len(rows), 16)
        self.assertEqual(sorted(item["tile_index"] for item in rows), list(range(16)))
        self.assertEqual(rows[0]["tile_id"], "T00")

    def test_validate_rejects_duplicate_tile_id(self) -> None:
        payload = {
            "meta": {"map_id": "x", "track_length": 2},
            "tiles": [
                {
                    "tile_id": "T00",
                    "tile_index": 0,
                    "tile_type": "START",
                    "name": "A",
                    "render": {"x": 0, "y": 0, "w": 10, "h": 10},
                },
                {
                    "tile_id": "T00",
                    "tile_index": 1,
                    "tile_type": "EMPTY",
                    "name": "B",
                    "render": {"x": 20, "y": 0, "w": 10, "h": 10},
                },
            ],
        }
        with self.assertRaisesRegex(ValueError, "duplicate tile_id"):
            validate_map_definition(payload)

    def test_load_map_from_custom_path(self) -> None:
        with TemporaryDirectory() as tmp:
            custom = Path(tmp) / "map.json"
            custom.write_text(
                """
{
  "meta": {"map_id": "tmp", "track_length": 2},
  "tiles": [
    {"tile_id": "T00", "tile_index": 0, "tile_type": "START", "name": "S", "render": {"x": 0, "y": 0, "w": 10, "h": 10}},
    {"tile_id": "T01", "tile_index": 1, "tile_type": "EMPTY", "name": "E", "render": {"x": 20, "y": 0, "w": 10, "h": 10}}
  ]
}
""".strip(),
                encoding="utf-8",
            )
            payload = load_map_definition(custom)
            self.assertEqual(payload["meta"]["map_id"], "tmp")

    def test_game_engine_fallback_board_when_loader_fails(self) -> None:
        with patch("app.game_engine.load_runtime_board", side_effect=RuntimeError("broken")):
            board = build_default_board()
        self.assertEqual(len(board), 16)
        self.assertEqual(board[0].tile_id, "T00")

    def test_default_map_file_exists(self) -> None:
        self.assertTrue(default_map_path().exists())

    def test_validate_rejects_unknown_next_tile_reference(self) -> None:
        payload = {
            "meta": {"map_id": "x", "track_length": 2},
            "tiles": [
                {
                    "tile_id": "T00",
                    "tile_index": 0,
                    "tile_type": "START",
                    "name": "A",
                    "next_tile_ids": ["T99"],
                    "render": {"x": 0, "y": 0, "w": 10, "h": 10},
                },
                {
                    "tile_id": "T01",
                    "tile_index": 1,
                    "tile_type": "EMPTY",
                    "name": "B",
                    "render": {"x": 20, "y": 0, "w": 10, "h": 10},
                },
            ],
        }
        with self.assertRaisesRegex(ValueError, "references unknown tile"):
            validate_map_definition(payload)

    def test_load_branch_map_definition(self) -> None:
        branch_map = default_map_path().parents[0] / "board.02_basic_branch.json"
        payload = load_map_definition(branch_map)
        self.assertEqual(payload["meta"]["map_id"], "branch18")
        self.assertEqual(payload["meta"]["track_length"], 18)
        branch_tile = next(item for item in payload["tiles"] if item["tile_id"] == "T03")
        self.assertEqual(sorted(branch_tile["next_tile_ids"]), ["T04A", "T04B"])


if __name__ == "__main__":
    unittest.main()
