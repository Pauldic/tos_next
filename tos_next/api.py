"""Read API for the Vue app. Every endpoint respects the caller's permissions (get_list, not get_all).

Call as  /api/method/tos_next.api.<name>  or  frappe.call({method: "tos_next.api.<name>"}).
Check argument handling and get_list options against Frappe v16 before relying on them.
"""
import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, get_time, getdate, now_datetime, nowdate

from tos_next import yard

NEEDS_TARGET = {"Yard Shift", "Reshuffle", "From Gate In", "From Vessel"}
OPEN_ORDER = ["Queued", "Assigned", "In Progress"]
BUSY_VISIT = ["Processing", "On Hold", "Cleared"]


def _terminal(terminal=None):
    if terminal:
        return terminal
    t = frappe.db.get_value("Terminal", {"is_active": 1}, "name")
    if not t:
        frappe.throw(_("No active terminal found."))
    return t


def _count(doctype, filters):
    return frappe.db.count(doctype, filters)


@frappe.whitelist()
def terminals():
    return frappe.get_list("Terminal", filters={"is_active": 1}, fields=["name", "terminal_name", "max_tier", "require_appointment"])


@frappe.whitelist()
def yard_snapshot(terminal=None):
    """Everything the 3D yard needs in one call. Keep it, then patch it from realtime events."""
    terminal = _terminal(terminal)
    frappe.has_permission("Yard Stack", "read", throw=True)
    blocks = frappe.get_list("Yard Block", filters={"terminal": terminal, "is_active": 1}, limit_page_length=0,
                             fields=["name", "block_code", "block_type", "bay_count", "row_count", "max_tier", "origin_x", "origin_y"])
    stacks = frappe.get_list("Yard Stack", filters={"terminal": terminal}, limit_page_length=0,
                             fields=["name", "yard_block", "bay", "row_no", "tier_count", "max_tier", "is_blocked", "is_forty_anchor", "pair_stack"])
    containers = frappe.get_list("Container", filters={"terminal": terminal, "status": "On Terminal", "yard_stack": ["is", "set"]}, limit_page_length=0,
                                 fields=["name", "shipping_line", "container_type", "length_ft", "slot_span", "cargo_status",
                                         "yard_stack", "partner_stack", "tier", "is_on_hold"])
    lines = frappe.get_list("Shipping Line", fields=["name", "line_name", "colour"], limit_page_length=0)
    return {"terminal": terminal, "as_of": str(now_datetime()), "blocks": blocks, "stacks": stacks, "containers": containers, "lines": lines}


@frappe.whitelist()
def stack_detail(stack):
    """Containers in one stack (either slot of a 40 ft pair), top first, with active holds."""
    frappe.has_permission("Yard Stack", "read", throw=True)
    rows = frappe.get_list(
        "Container", or_filters={"yard_stack": stack, "partner_stack": stack}, order_by="tier desc", limit_page_length=0,
        fields=["name", "shipping_line", "container_type", "length_ft", "cargo_status", "status", "yard_stack", "partner_stack", "tier",
                "gross_weight_kg", "seal_no", "arrived_on", "free_days_until", "booking_ref", "is_on_hold"])
    names = [r.name for r in rows]
    holds = frappe.get_list("Container Hold", filters={"container": ["in", names], "status": "Active"},
                            fields=["container", "hold_type", "reason", "placed_on"]) if names else []
    by_c = {}
    for h in holds:
        by_c.setdefault(h.container, []).append(h)
    for r in rows:
        r["holds"] = by_c.get(r.name, [])
        r["dwell_days"] = (now_datetime() - get_datetime(r.arrived_on)).days if r.arrived_on else None
    return {"stack": frappe.db.get_value("Yard Stack", stack, ["name", "yard_block", "bay", "row_no", "tier_count", "max_tier", "is_blocked"], as_dict=True),
            "containers": rows}


@frappe.whitelist()
def search_container(q, terminal=None):
    terminal = _terminal(terminal)
    q = "".join(ch for ch in (q or "").upper() if ch.isalnum())
    if len(q) < 2:
        return []
    return frappe.get_list("Container", filters={"terminal": terminal, "name": ["like", f"%{q}%"]}, limit_page_length=8,
                           fields=["name", "status", "yard_stack", "partner_stack", "tier", "shipping_line", "cargo_status"])


@frappe.whitelist()
def work_queue(terminal=None):
    terminal = _terminal(terminal)
    fields = ["name", "container", "move_type", "status", "priority", "from_stack", "from_tier", "to_stack", "to_tier",
              "equipment", "assigned_to", "started_at", "completed_at", "creation"]
    open_ = frappe.get_list("Move Order", filters={"terminal": terminal, "status": ["in", OPEN_ORDER]}, fields=fields, order_by="priority desc, creation asc", limit_page_length=50)
    done = frappe.get_list("Move Order", filters={"terminal": terminal, "status": "Completed"}, fields=fields, order_by="completed_at desc", limit_page_length=3)
    return {"open": open_, "recent": done}


@frappe.whitelist()
def create_move_order(container, move_type="Yard Shift", to_stack=None, priority="Normal", notes=None):
    """The 'Create move order' button. Picks a destination if none is given."""
    frappe.has_permission("Move Order", "create", throw=True)
    if move_type in NEEDS_TARGET and not to_stack:
        to_stack = yard.suggest_target(container)
        if not to_stack:
            frappe.throw(_("No free stack found for {0}.").format(container))
    doc = frappe.get_doc({"doctype": "Move Order", "container": container, "move_type": move_type,
                          "to_stack": to_stack, "priority": priority, "notes": notes}).insert()
    return {"name": doc.name, "to_stack": doc.to_stack}


@frappe.whitelist()
def gate_board(terminal=None):
    terminal = _terminal(terminal)
    frappe.has_permission("Gate Lane", "read", throw=True)
    lanes = frappe.get_list("Gate Lane", filters={"terminal": terminal}, fields=["name", "lane_code", "direction", "status", "current_transaction"], order_by="direction desc, lane_code asc", limit_page_length=0)
    for lane in lanes:
        lane["transaction"] = None
        if lane.current_transaction:
            gt = frappe.get_doc("Gate Transaction", lane.current_transaction)
            lane["transaction"] = {
                "name": gt.name, "status": gt.status, "hold_reason": gt.hold_reason, "truck": gt.truck, "carrier": gt.carrier, "driver": gt.driver,
                "move_type": gt.move_type, "container": gt.container or gt.container_no, "appointment": gt.appointment, "override": gt.override,
                "current_step": gt.current_step, "entered_at": gt.entered_at, "ocr_container_no": gt.ocr_container_no, "ocr_confidence": gt.ocr_confidence,
                "seal_intact": gt.seal_intact, "damage_found": gt.damage_found,
                "checks": [{"step": c.step, "result": c.result, "checked_by": c.checked_by, "remarks": c.remarks} for c in gt.checks],
            }
    now = now_datetime()
    appts = frappe.get_list("Appointment", filters={"terminal": terminal, "slot_date": nowdate(), "status": ["in", ["Booked", "Late"]]},
                            fields=["name", "truck", "carrier", "driver", "move_type", "direction", "start_time", "end_time", "status", "container", "booking_ref"], order_by="start_time asc", limit_page_length=50)
    queue = []
    for a in appts:
        start = get_datetime(f"{nowdate()} {get_time(a.start_time)}")
        if add_to_date(now, minutes=-90) <= start <= add_to_date(now, minutes=90):
            a["minutes_to_slot"] = int((start - now).total_seconds() // 60)
            queue.append(a)
    return {"lanes": lanes, "arrival_queue": queue}


@frappe.whitelist()
def capacity_for_day(date=None, terminal=None):
    terminal = _terminal(terminal)
    frappe.has_permission("Slot Capacity", "read", throw=True)
    return frappe.get_list("Slot Capacity", filters={"terminal": terminal, "slot_date": getdate(date or nowdate())}, order_by="start_time asc", limit_page_length=0,
                           fields=["name", "start_time", "end_time", "capacity", "booked", "is_closed", "move_types"])


@frappe.whitelist()
def appointments_for_slot(slot, direction=None):
    flt = {"slot": slot}
    if direction in ("In", "Out"):
        flt["direction"] = direction
    return frappe.get_list("Appointment", filters=flt, order_by="creation asc", limit_page_length=0,
                           fields=["name", "carrier", "truck", "driver", "move_type", "direction", "container", "booking_ref", "status", "start_time", "override"])


@frappe.whitelist()
def kpis(terminal=None):
    terminal = _terminal(terminal)
    for dt in ("Yard Stack", "Container", "Slot Capacity"):
        frappe.has_permission(dt, "read", throw=True)
    stacks = frappe.db.sql("select coalesce(sum(tier_count),0) as used, coalesce(sum(max_tier),0) as cap from `tabYard Stack` where terminal=%s", terminal, as_dict=True)[0]
    on_ground = frappe.db.sql("select count(name) as n from `tabContainer` where terminal=%s and status='On Terminal'", terminal, as_dict=True)[0]
    today = getdate(nowdate())
    slot = frappe.db.sql("select coalesce(sum(booked),0) as booked, coalesce(sum(capacity),0) as cap from `tabSlot Capacity` where terminal=%s and slot_date=%s", (terminal, today), as_dict=True)[0]
    return {
        "yard_occupancy_pct": round((stacks.used or 0) / stacks.cap * 100) if stacks.cap else 0,
        "containers_on_ground": on_ground.n or 0,
        "moves_today": _count("Container Movement", {"terminal": terminal, "movement_type": "Yard Move", "timestamp": [">=", today]}),
        "gate_in_today": _count("Gate Transaction", {"terminal": terminal, "direction": "In", "status": "Completed", "exited_at": [">=", today]}),
        "gate_out_today": _count("Gate Transaction", {"terminal": terminal, "direction": "Out", "status": "Completed", "exited_at": [">=", today]}),
        "trucks_in_terminal": _count("Gate Transaction", {"terminal": terminal, "status": ["in", BUSY_VISIT]}),
        "appointments_booked_today": slot.booked or 0,
        "appointment_capacity_today": slot.cap or 0,
        "open_move_orders": _count("Move Order", {"terminal": terminal, "status": ["in", OPEN_ORDER]}),
        "pending_overrides": _count("Appointment Override", {"terminal": terminal, "status": "Pending"}),
    }
