"""The yard layout: where things stand on the site. Logical positions (block, bay, row, tier) never live here;
a layout only says where each block, road, building and so on is drawn.

Units are metres. Rotation is in degrees, clockwise when seen from above. x runs east, z runs south.
"""
import math

import frappe
from frappe import _

from tos_next.settings import company

# TOS Settings field for each geometry value the 3D yard needs
GEOMETRY_FIELDS = {
    "slot": "slot_length_m",
    "row": "row_pitch_m",
    "tier": "tier_height_m",
    "block_gap": "block_gap_m",
    "car_bay": "car_bay_width_m",
    "truck_bay": "truck_bay_width_m",
}
ITEM_FIELDS = ["item_type", "label", "yard_block", "shape", "x", "z", "rotation", "length", "width", "height", "surface",
               "colour", "direction", "door_side", "points", "locked"]
AUTO_COLUMNS = 2  # blocks that have no place in a layout yet are set out in this many columns


def geometry():
    return {key: float(company(field)) for key, field in GEOMETRY_FIELDS.items()}


def parse_points(text):
    """'120,40' per line -> [(120.0, 40.0), ...]. Raises ValueError on a line that is not two numbers."""
    pts = []
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = [p for p in line.replace(";", ",").split(",") if p.strip()]
        if len(parts) != 2:
            raise ValueError(_("Point {0} must look like 120,40").format(n))
        pts.append((float(parts[0]), float(parts[1])))
    return pts


def block_size(block, g=None):
    g = g or geometry()
    return block["bay_count"] * g["slot"], block["row_count"] * g["row"]


def active_blocks(terminal):
    return frappe.get_all("Yard Block", filters={"terminal": terminal, "is_active": 1}, order_by="block_code",
                          fields=["name", "block_code", "block_type", "bay_count", "row_count", "max_tier"])


def auto_items(blocks, g=None, start_x=0.0, start_z=0.0):
    """Set blocks out in a simple grid. Used for the first layout of a terminal and for blocks added later."""
    g = g or geometry()
    blocks = sorted(blocks, key=lambda b: str(b["block_code"]))
    widths = [block_size(b, g)[0] for b in blocks]
    col_x = []
    x = start_x
    for c in range(AUTO_COLUMNS):
        col_x.append(x)
        x += max([w for i, w in enumerate(widths) if i % AUTO_COLUMNS == c] or [0]) + g["block_gap"]
    items, z, row_depth = [], start_z, 0.0
    for i, b in enumerate(blocks):
        col = i % AUTO_COLUMNS
        if col == 0 and i > 0:
            z += row_depth + g["block_gap"]
            row_depth = 0.0
        w, d = block_size(b, g)
        items.append({"item_type": "Block", "yard_block": b["name"], "shape": "Rectangle", "x": col_x[col] + w / 2, "z": z + d / 2,
                      "rotation": 0, "door_side": "Lower bay end"})
        row_depth = max(row_depth, d)
    return items


def published(terminal):
    name = frappe.db.get_value("Yard Layout", {"terminal": terminal, "status": "Published"}, "name")
    return frappe.get_doc("Yard Layout", name) if name else None


def _row(i):
    return {k: i.get(k) for k in ITEM_FIELDS}


def effective(terminal, layout=None):
    """What the 3D yard draws: the published layout, plus an automatic place for any active block it does not mention,
    so a block can never be missing from the view."""
    g = geometry()
    blocks = {b["name"]: b for b in active_blocks(terminal)}
    layout = layout or published(terminal)
    items = [_row(i) for i in layout.items] if layout else []
    placed = {i["yard_block"] for i in items if i["item_type"] == "Block"}
    missing = [b for n, b in blocks.items() if n not in placed]
    if missing:
        right, top = 0.0, 0.0
        boxes = [corners(i, blocks, g) for i in items if i["item_type"] == "Block" and i["yard_block"] in blocks]
        if boxes:
            right = max(x for c in boxes for x, _z in c) + g["block_gap"]
            top = min(z for c in boxes for _x, z in c)
        items += [dict(a, auto=1) for a in auto_items(missing, g, right, top)]
    out = []
    for i in items:
        if i["item_type"] == "Block":
            b = blocks.get(i["yard_block"])
            if not b:
                continue  # the block was switched off after this layout was made
            w, d = block_size(b, g)
            i = dict(i, block_code=b["block_code"], bay_count=b["bay_count"], row_count=b["row_count"], max_tier=b["max_tier"],
                     block_type=b["block_type"], length=w, width=d)
        out.append(i)
    return {"name": layout.name if layout else None, "version": layout.version if layout else 0, "base_surface": layout.base_surface if layout else "Default",
            "automatic": not layout, "items": out, "geometry": g}


def corners(item, blocks, g):
    """The four corners of a Block item in site coordinates."""
    b = blocks[item["yard_block"]]
    w, d = block_size(b, g)
    a = math.radians(item.get("rotation") or 0)
    ca, sa = math.cos(a), math.sin(a)
    return [(item["x"] + lx * ca - lz * sa, item["z"] + lx * sa + lz * ca) for lx, lz in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]


def _overlap(p, q):
    """Separating-axis test for two convex quadrilaterals. Touching edges do not count as overlap."""
    for poly in (p, q):
        for i in range(len(poly)):
            ax, az = poly[i]
            bx, bz = poly[(i + 1) % len(poly)]
            nx, nz = -(bz - az), bx - ax
            p_proj = [x * nx + z * nz for x, z in p]
            q_proj = [x * nx + z * nz for x, z in q]
            if max(p_proj) <= min(q_proj) + 1e-6 or max(q_proj) <= min(p_proj) + 1e-6:
                return False
    return True


def publish_problems(layout):
    """Reasons a draft cannot be published yet. Empty when it is fine."""
    g = geometry()
    blocks = {b["name"]: b for b in active_blocks(layout.terminal)}
    rows = [_row(i) for i in layout.items if i.item_type == "Block"]
    placed = {r["yard_block"] for r in rows}
    problems = []
    missing = sorted(b["block_code"] for n, b in blocks.items() if n not in placed)
    if missing:
        problems.append(_("These blocks are not placed yet: {0}.").format(", ".join(missing)))
    inactive = sorted(p for p in placed if p not in blocks)
    if inactive:
        problems.append(_("These blocks are not active any more: {0}. Remove them from the layout.").format(", ".join(inactive)))
    live = [r for r in rows if r["yard_block"] in blocks]
    polys = [(blocks[r["yard_block"]]["block_code"], corners(r, blocks, g)) for r in live]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            if _overlap(polys[i][1], polys[j][1]):
                problems.append(_("Block {0} overlaps block {1}.").format(polys[i][0], polys[j][0]))
    return problems
