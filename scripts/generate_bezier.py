import json
import os

def make_tile(tid, tindex, name, ttype, x, y, next_ids):
    return {
        "tile_id": tid,
        "tile_index": tindex,
        "name": name,
        "tile_type": ttype,
        "tile_subtype": ttype,
        "property_price": 200 + tindex * 10 if ttype == "PROPERTY" else None,
        "toll": 40 + tindex * 2 if ttype == "PROPERTY" else None,
        "event_key": "EVT_SMALL" if ttype == "EVENT" else None,
        "quiz_key": None,
        "next_tile_ids": next_ids,
        "render": {
            "x": x,
            "y": y,
            "w": 100,
            "h": 100,
            "rotation": 0,
            "label_anchor": "center"
        }
    }

tiles = []

# Map dimensions and spacing
center_x = 600
center_y = 400
# Outer Ring
# Top edge
tiles.append(make_tile("T00", 0, "Start", "START", 100, 100, ["T01"]))
tiles.append(make_tile("T01", 1, "Alpha St", "PROPERTY", 300, 100, ["T02"]))
tiles.append(make_tile("T02", 2, "Beta Ave", "PROPERTY", 500, 100, ["T03"]))
tiles.append(make_tile("T03", 3, "Gamma Rd", "PROPERTY", 700, 100, ["T04", "C01"])) # Branch 1 Top
tiles.append(make_tile("T04", 4, "Delta Way", "PROPERTY", 900, 100, ["T05"]))
tiles.append(make_tile("T05", 5, "Epsilon St", "PROPERTY", 1100, 100, ["T06"]))

# Right edge
tiles.append(make_tile("T06", 6, "Zeta Plaza", "EVENT", 1100, 300, ["T07"]))
tiles.append(make_tile("T07", 7, "Eta Park", "EMPTY", 1100, 500, ["T08"]))
tiles.append(make_tile("T08", 8, "Theta Bank", "BANK", 1100, 700, ["T09"]))

# Bottom edge
tiles.append(make_tile("T09", 9, "Iota Blvd", "PROPERTY", 900, 700, ["T10"]))
tiles.append(make_tile("T10", 10, "Kappa Ln", "PROPERTY", 700, 700, ["T11"]))
tiles.append(make_tile("T11", 11, "Lambda Dr", "PROPERTY", 500, 700, ["T12", "C02"])) # Branch 2 Bottom
tiles.append(make_tile("T12", 12, "Mu Court", "PROPERTY", 300, 700, ["T13"]))
tiles.append(make_tile("T13", 13, "Nu Square", "EVENT", 100, 700, ["T14"]))

# Left edge
tiles.append(make_tile("T14", 14, "Xi Circle", "PROPERTY", 100, 500, ["T15"]))
tiles.append(make_tile("T15", 15, "Omicron St", "PROPERTY", 100, 300, ["T00"]))

# Inner Nodes (Perfectly point-symmetric around (600, 400))
# Branch 1 path: T03(700,100) -> C01 -> C03 -> T15(100,300)
# Branch 2 path: T11(500,700) -> C02 -> C04 -> T07(1100,500)

tiles.append(make_tile("C01", 16, "Sweep Hub", "BANK", 500, 300, ["C03"]))
tiles.append(make_tile("C02", 17, "Arc Node", "EVENT", 700, 500, ["C04"]))

tiles.append(make_tile("C03", 18, "Merge West", "PROPERTY", 300, 300, ["T15"]))
tiles.append(make_tile("C04", 19, "Merge East", "PROPERTY", 900, 500, ["T07"]))

map_bezier = {
    "meta": {
        "map_id": "bezier_showcase",
        "track_length": 20,
        "theme": "city-bezier",
        "version": "1.0.0",
        "topology": "graph",
        "start_tile_id": "T00",
        "canvas": {"width": 1300, "height": 900}
    },
    "tiles": tiles
}

os.makedirs("backend/config/maps", exist_ok=True)
with open("backend/config/maps/board.06_bezier_showcase.json", "w", encoding="utf-8") as f:
    json.dump(map_bezier, f, indent=2, ensure_ascii=False)

print("Done generating Bezier Showcase map.")