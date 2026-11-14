"""The container inventory: one row per container with the columns the terminal's operators work from.
Used by the Container Inventory report in the Desk and by the Containers page in /tos."""
import frappe
from frappe.utils import add_to_date, date_diff, get_datetime, now_datetime

FIELDS = [
    "name", "terminal", "status", "transit_state", "position", "yard_stack", "tier", "category", "full_empty", "container_type", "length_ft",
    "shipping_line", "line", "terminal_line", "group_code", "is_reefer", "reefer_set_temp_c", "reefer_plugged", "is_hazmat", "imdg_summary",
    "is_on_hold", "seal_no", "seal_verified", "bill_of_lading", "booking_ref", "arrived_on", "gross_weight_kg",
    "ib_visit", "ib_vessel_id", "ib_vessel_name", "ib_vessel_voyage", "ib_vessel_class",
    "ob_visit", "ob_vessel_id", "ob_vessel_name", "ob_vessel_voyage", "ob_vessel_class",
    "special_stow_1", "special_stow_2", "special_stow_3", "special_stow_4", "special_stow_5",
    "planned_position", "destination", "pol", "pod", "place_of_delivery", "consignee",
    "storage_paid_date", "reefer_storage_paid", "line_storage_paid", "remarks",
]
FILTERABLE = ["terminal", "status", "transit_state", "category", "full_empty", "shipping_line", "line", "terminal_line", "is_hazmat", "is_reefer",
              "is_on_hold", "seal_verified", "ib_visit", "ob_visit", "container_type", "group_code", "yard_stack"]


def rows(filters=None, search=None, limit=500, start=0):
    """Container rows the caller may read, each with dwell_days (days since Time In, for containers still on the terminal)."""
    flt = {k: v for k, v in (filters or {}).items() if k in FILTERABLE and v not in (None, "")}
    or_filters = None
    if search:
        q = "".join(ch for ch in search.upper() if ch.isalnum())
        if q:
            or_filters = {"name": ["like", f"%{q}%"], "bill_of_lading": ["like", f"%{search}%"], "booking_ref": ["like", f"%{search}%"]}
    data = frappe.get_list("Container", filters=flt, or_filters=or_filters, fields=FIELDS, order_by="arrived_on desc, name asc", limit_start=int(start), limit_page_length=int(limit))
    now = now_datetime()
    for r in data:
        r["dwell_days"] = date_diff(now, r.arrived_on) if r.arrived_on and r.status == "On Terminal" else None
        r["reefer_temp"] = f"{r.reefer_set_temp_c:g} °C" if r.is_reefer and r.reefer_set_temp_c is not None else ""
    return data


def history(container):
    """Everything that has happened to one container, newest first: moves, holds, gate transactions and events."""
    doc = frappe.get_doc("Container", container)
    doc.check_permission("read")
    moves = frappe.get_list("Container Movement", filters={"container": container}, order_by="timestamp desc", limit_page_length=0,
                            fields=["name", "movement_type", "timestamp", "performed_by", "equipment", "from_stack", "from_tier", "to_stack", "to_tier", "source_doctype", "source_name"])
    holds = frappe.get_list("Container Hold", filters={"container": container}, order_by="placed_on desc", limit_page_length=0,
                            fields=["name", "hold_type", "status", "reason", "reference", "placed_by", "placed_on", "released_by", "released_on", "release_note"])
    gate = frappe.get_list("Gate Transaction", filters={"container": container}, order_by="entered_at desc", limit_page_length=0,
                           fields=["name", "direction", "move_type", "status", "lane", "carrier", "truck", "driver", "entered_at", "exited_at", "turn_minutes", "seal_intact", "damage_found", "damage_notes"])
    steps = {}
    if gate:
        for s in frappe.get_all("Gate Check Step", filters={"parent": ["in", [g.name for g in gate]], "parenttype": "Gate Transaction"},
                                fields=["parent", "step", "result", "checked_by", "checked_on", "remarks"], order_by="idx asc"):
            steps.setdefault(s.parent, []).append(s)
    for g in gate:
        g["steps"] = steps.get(g.name, [])
    events = frappe.get_list("Container Event", filters={"container": container}, order_by="event_time desc", limit_page_length=0,
                             fields=["name", "event_type", "event_time", "event_by", "summary", "source_doctype", "source_name"])

    line = []
    for m in moves:
        where = f"{m.from_stack or 'outside'} → {m.to_stack or 'outside'}" if (m.from_stack or m.to_stack) else ""
        line.append({"kind": "move", "time": m.timestamp, "by": m.performed_by, "title": m.movement_type, "detail": where, "ref": m.source_name or m.name})
    for h in holds:
        line.append({"kind": "hold", "time": h.placed_on, "by": h.placed_by, "title": f"Hold placed: {h.hold_type}", "detail": h.reason or "", "ref": h.name})
        if h.released_on:
            line.append({"kind": "hold", "time": h.released_on, "by": h.released_by, "title": f"Hold released: {h.hold_type}", "detail": h.release_note or "", "ref": h.name})
    for g in gate:
        bits = [f"lane {g.lane}", g.status] + (["damage found"] if g.damage_found else []) + ([f"{g.turn_minutes} min"] if g.turn_minutes else [])
        line.append({"kind": "gate", "time": g.entered_at, "by": None, "title": f"Gate {g.direction}", "detail": ", ".join(bits), "ref": g.name})
    for e in events:
        line.append({"kind": "event", "time": e.event_time, "by": e.event_by, "title": e.event_type, "detail": e.summary, "ref": e.name})
    line.sort(key=lambda x: get_datetime(x["time"]) if x["time"] else get_datetime("1970-01-01"), reverse=True)
    return {"moves": moves, "holds": holds, "gate": gate, "events": events, "timeline": line}
