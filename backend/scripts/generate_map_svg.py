from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.map_engine import default_map_path  # noqa: E402
from app.map_svg import generate_svg_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate map SVG from map JSON")
    parser.add_argument("--map", dest="map_path", default=str(default_map_path()))
    parser.add_argument("--out", dest="out_path", default="frontend/public/maps/default.svg")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_svg_file(Path(args.map_path), Path(args.out_path))


if __name__ == "__main__":
    main()
