import json
import os

def make_tile(tid, tindex, name, ttype, col, row, next_ids, price=None, toll=None, event_key=None):
    return {
        "tile_id": tid,
        "tile_index": tindex,
        "name": name,
        "tile_type": ttype,
        "tile_subtype": ttype,
        "property_price": price,
        "toll": toll,
        "event_key": event_key,
        "quiz_key": None,
        "next_tile_ids": next_ids,
        "render": {
            "x": 60 + col * 160,
            "y": 60 + row * 160,
            "w": 100,
            "h": 100,
            "rotation": 0,
            "label_anchor": "center"
        }
    }

# Generate Loop 24
tiles_24 = []
coords_24 = []
# 8x6 grid
# Top edge (0..7, 0)
for i in range(8): coords_24.append((i, 0))
# Right edge (7, 1..4)
for i in range(1, 5): coords_24.append((7, i))
# Bottom edge (7..0, 5)
for i in range(7, -1, -1): coords_24.append((i, 5))
# Left edge (0, 4..1)
for i in range(4, 0, -1): coords_24.append((0, i))

types_24 = [
    "START", "PROPERTY", "PROPERTY", "EVENT", "PROPERTY", "PROPERTY", "BANK", "PROPERTY", 
    "EMPTY", "PROPERTY", "PROPERTY", "EVENT", 
    "PROPERTY", "PROPERTY", "BANK", "PROPERTY", "PROPERTY", "EVENT", "PROPERTY", "EMPTY", 
    "PROPERTY", "BANK", "PROPERTY", "PROPERTY"
]
names_24 = [
    "Start", "Elm St", "Oak St", "Lucky", "Maple St", "Pine St", "City Bank", "Cedar St",
    "Transit", "Ash St", "Birch St", "Chance",
    "Cherry St", "Walnut St", "Union Bank", "Spruce St", "Willow St", "Mystery", "Chestnut", "Park",
    "Poplar St", "Trust Bank", "Fir St", "Sycamore"
]

for i in range(24):
    tid = f"T{i:02d}"
    next_id = f"T{(i+1)%24:02d}"
    ttype = types_24[i]
    price = 100 + i*10 if ttype == "PROPERTY" else None
    toll = (100 + i*10)//5 if ttype == "PROPERTY" else None
    ekey = "EVT_SMALL" if ttype == "EVENT" else None
    c, r = coords_24[i]
    name = names_24[i]
    tiles_24.append(make_tile(tid, i, name, ttype, c, r, [next_id], price, toll, ekey))

map_24 = {
    "meta": {
        "map_id": "loop24",
        "track_length": 24,
        "theme": "city-loop-large",
        "version": "1.0.0",
        "topology": "loop",
        "start_tile_id": "T00",
        "canvas": {"width": 1340, "height": 1020}
    },
    "tiles": tiles_24
}

with open("backend/config/maps/board.03_large_loop.json", "w", encoding="utf-8") as f:
    json.dump(map_24, f, indent=2, ensure_ascii=False)

# Generate Branch 28
# Base is the 24 tiles loop. We add a branch going straight down from T04(4,0) to T15(4,5).
import copy
tiles_28 = copy.deepcopy(tiles_24)

# Modify T04
tiles_28[4]["next_tile_ids"] = ["T05", "B01"]

# Add B01 to B04
b_coords = [(4, 1), (4, 2), (4, 3), (4, 4)]
b_types = ["EVENT", "PROPERTY", "PROPERTY", "BANK"]
b_names = ["Secret Alley", "Gold Mine", "Diamond Hub", "Offshore Bank"]

for i in range(4):
    tid = f"B{i+1:02d}"
    next_id = f"B{i+2:02d}" if i < 3 else "T15"
    ttype = b_types[i]
    price = 300 + i*20 if ttype == "PROPERTY" else None
    toll = 60 + i*4 if ttype == "PROPERTY" else None
    ekey = "EVT_SMALL" if ttype == "EVENT" else None
    c, r = b_coords[i]
    name = b_names[i]
    tiles_28.append(make_tile(tid, 24+i, name, ttype, c, r, [next_id], price, toll, ekey))

map_28 = {
    "meta": {
        "map_id": "branch28",
        "track_length": 28,
        "theme": "city-branch-large",
        "version": "1.0.0",
        "topology": "graph",
        "start_tile_id": "T00",
        "canvas": {"width": 1340, "height": 1020}
    },
    "tiles": tiles_28
}

with open("backend/config/maps/board.04_large_branch.json", "w", encoding="utf-8") as f:
    json.dump(map_28, f, indent=2, ensure_ascii=False)

# Generate Complex 36
# Base is the 24 tiles loop. We add MULTIPLE intersecting branches and shortcuts.
# Grid size is 8x6.
# Branch 1: From T02 (2,0) vertically to T21 (2,5)
# Branch 2: From T06 (6,0) vertically to T17 (6,5)
# Cross Branch: Horizontal from B1_02 (2,2) to B2_02 (6,2)

tiles_36 = copy.deepcopy(tiles_24)

# Modify T02 to branch into B1_01
tiles_36[2]["next_tile_ids"] = ["T03", "C01"]
# Modify T06 to branch into B2_01
tiles_36[6]["next_tile_ids"] = ["T07", "C05"]

# Branch 1 (Vertical Left: C01 -> C02 -> C03 -> C04)
# C01 at (2,1), C02 at (2,2), C03 at (2,3), C04 at (2,4), merges to T17 (2,5)
c_coords = [
    (2, 1), (2, 2), (2, 3), (2, 4), # Branch 1: C01-C04
    (6, 1), (6, 2), (6, 3), (6, 4), # Branch 2: C05-C08
    (3, 2), (4, 2), (5, 2),         # Cross Branch: C09-C11 connecting C02 to C06
    (4, 4)                          # Extra shortcut: C12 connecting C04 to C08 (horizontal)
]

c_types = [
    "PROPERTY", "BANK", "EVENT", "PROPERTY",     # B1
    "EVENT", "PROPERTY", "PROPERTY", "EMPTY",    # B2
    "PROPERTY", "EVENT", "PROPERTY",             # Cross
    "BANK"                                       # Extra
]

c_names = [
    "Tech Hub", "Data Bank", "Server Crash", "Silicon St",
    "Bug Bounty", "AI Center", "Cloud Ave", "Dev Plaza",
    "Logic St", "Hackathon", "Cyber Way",
    "Crypto Bank"
]

# Create tiles C01 to C12
new_tiles = []
for i in range(12):
    tid = f"C{i+1:02d}"
    ttype = c_types[i]
    price = 400 + i*30 if ttype == "PROPERTY" else None
    toll = 80 + i*6 if ttype == "PROPERTY" else None
    ekey = "EVT_LARGE" if ttype == "EVENT" else None
    c, r = c_coords[i]
    name = c_names[i]
    # We will manually wire the next_tile_ids below
    new_tiles.append(make_tile(tid, 24+i, name, ttype, c, r, [], price, toll, ekey))

tiles_36.extend(new_tiles)

# Wiring the graph
def get_tile(tid):
    for t in tiles_36:
        if t["tile_id"] == tid: return t
    return None

# Branch 1: C01 -> C02 -> C03 -> C04 -> T17
get_tile("C01")["next_tile_ids"] = ["C02"]
get_tile("C02")["next_tile_ids"] = ["C03", "C09"] # Branches into Cross
get_tile("C03")["next_tile_ids"] = ["C04"]
get_tile("C04")["next_tile_ids"] = ["T17", "C12"] # Branches into Extra Shortcut

# Branch 2: C05 -> C06 -> C07 -> C08 -> T13
get_tile("C05")["next_tile_ids"] = ["C06"]
get_tile("C06")["next_tile_ids"] = ["C07"] # Receives from C11
get_tile("C07")["next_tile_ids"] = ["C08"]
get_tile("C08")["next_tile_ids"] = ["T13"] # Receives from C12

# Cross Branch: C09 -> C10 -> C11 -> C06
get_tile("C09")["next_tile_ids"] = ["C10"]
get_tile("C10")["next_tile_ids"] = ["C11"]
get_tile("C11")["next_tile_ids"] = ["C06"]

# Extra Shortcut: C12 -> C08
get_tile("C12")["next_tile_ids"] = ["C08"]


map_36 = {
    "meta": {
        "map_id": "complex36",
        "track_length": 36,
        "theme": "city-complex",
        "version": "1.0.0",
        "topology": "graph",
        "start_tile_id": "T00",
        "canvas": {"width": 1340, "height": 1020}
    },
    "tiles": tiles_36
}

with open("backend/config/maps/board.05_complex_branch.json", "w", encoding="utf-8") as f:
    json.dump(map_36, f, indent=2, ensure_ascii=False)

print("Done generating JSON maps.")