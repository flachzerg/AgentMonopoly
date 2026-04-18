from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.map_engine import default_map_path, load_map_definition
from app.map_svg import generate_svg_file, render_map_svg


class MapSvgTestCase(unittest.TestCase):
    def test_render_map_svg_contains_tile_groups(self) -> None:
        payload = load_map_definition(default_map_path())
        svg = render_map_svg(payload)
        self.assertIn("<svg", svg)
        self.assertIn('id="tile-T00"', svg)
        self.assertIn("Hill Road", svg)
        self.assertIn('id="track-layer"', svg)
        self.assertNotIn("marker-end", svg)
        self.assertIn("data-token-slots=", svg)

    def test_generate_svg_file_writes_output(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "map.svg"
            generate_svg_file(default_map_path(), out)
            text = out.read_text(encoding="utf-8")
            self.assertTrue(out.exists())
            self.assertIn("</svg>", text)
            self.assertIn("data-tile-id", text)
            self.assertIn("<circle", text)


if __name__ == "__main__":
    unittest.main()
