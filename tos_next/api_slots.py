"""Slot management for planners: see the day, change capacity, block and unblock, add and copy slots.
Everything goes through normal document saves, so Slot Capacity's own rules apply (capacity can never drop below
what is already booked) and the user's write permission is checked on every slot. A slot with bookings is never
closed or emptied silently: the call reports it and waits for allow_booked.
Call as /api/method/tos_next.api_slots.<name>.
"""
import frappe
from frappe import _
from frappe.utils import add_days, get_time, getdate, nowdate

from tos_next.api import _terminal

MANAGERS = {"System Manager", "Terminal Admin", "Appointment Planner"}
SCOPES = ("All", "Gate In", "Gate Out")
FIELDS = ["name", "slot_date", "start_time", "end_time", "capacity", "booked", "is_closed", "closed_reason", "move_types"]
ACTIONS = ("set_capacity", "add_capacity", "block", "unblock", "set_scope")


def _need_manager():
    if not MANAGERS.intersection(frappe.get_roles()):
        frappe.throw(_("Only an appointment planner can manage slots."), frappe.PermissionError)


def _hm(t):
    return str(get_time(t))[:5]


@frappe.whitelist()
def slots_for_day(date=None, terminal=None):
    terminal = _terminal(terminal)
    frappe.has_permission("Slot Capacity", "read", throw=True)
    return frappe.get_list("Slot Capacity", filters={"terminal": terminal, "slot_date": getdate(date or nowdate())},
                           order_by="start_time asc, move_types asc", limit_page_length=0, fields=FIELDS)


def _target_slots(terminal, slots=None, date_from=None, date_to=None, time_from=None, time_to=None, weekdays=None):
    """Either the named slots, or every slot of the terminal inside a date range and a time window."""
    slots = frappe.parse_json(slots) if isinstance(slots, str) else slots
    if slots:
        rows = frappe.get_all("Slot Capacity", filters={"name": ["in", slots], "terminal": terminal}, fields=FIELDS, order_by="slot_date, start_time", limit_page_length=0)
        if len(rows) != len(set(slots)):
            frappe.throw(_("Some of the chosen slots do not belong to this terminal."))
        return rows
    if not (date_from and date_to):
        frappe.throw(_("Choose slots, or a date range."))
    d1, d2 = getdate(date_from), getdate(date_to)
    if d2 < d1:
        frappe.throw(_("The end date is before the start date."))
    if (d2 - d1).days > 92:
        frappe.throw(_("A change can cover at most 93 days at a time."))
    rows = frappe.get_all("Slot Capacity", filters={"terminal": terminal, "slot_date": ["between", [d1, d2]]}, fields=FIELDS, order_by="slot_date, start_time", limit_page_length=0)
    days = {int(x) for x in (frappe.parse_json(weekdays) if isinstance(weekdays, str) else weekdays or [])}
    out = []
    for r in rows:
        if days and getdate(r.slot_date).weekday() not in days:
            continue
        if time_from and get_time(r.end_time) <= get_time(time_from):
            continue
        if time_to and get_time(r.start_time) >= get_time(time_to):
            continue
        out.append(r)
    return out


@frappe.whitelist()
def bulk_update(action, terminal=None, slots=None, date_from=None, date_to=None, time_from=None, time_to=None, weekdays=None,
                capacity=None, reason=None, move_types=None, allow_booked=0, preview=0):
    """Change many slots at once.
    action: set_capacity | add_capacity (capacity may be negative) | block | unblock | set_scope (move_types)
    Pick slots by name (slots) or by range (date_from, date_to, optional time_from/time_to and weekdays 0=Monday).
    preview=1 changes nothing and only reports what would happen. Returns changed, skipped (with the reason) and
    the number of existing bookings that sit in slots that were blocked."""
    _need_manager()
    terminal = _terminal(terminal)
    if action not in ACTIONS:
        frappe.throw(_("Unknown action."))
    if action in ("set_capacity", "add_capacity") and capacity in (None, ""):
        frappe.throw(_("Enter the capacity."))
    if action == "block" and not (reason or "").strip():
        frappe.throw(_("Say why the slots are blocked. The reason is shown to the planners."))
    if action == "set_scope" and move_types not in SCOPES:
        frappe.throw(_("Choose which jobs the slots take."))
    preview, allow_booked = int(preview or 0), int(allow_booked or 0)

    targets = _target_slots(terminal, slots, date_from, date_to, time_from, time_to, weekdays)
    if not targets:
        frappe.throw(_("No slots match."))
    changed, skipped, blocked_bookings = [], [], 0
    for r in targets:
        label = f"{r.slot_date} {_hm(r.start_time)}"
        doc = frappe.get_doc("Slot Capacity", r.name)
        doc.check_permission("write")
        why = None
        if action in ("set_capacity", "add_capacity"):
            cap = int(capacity) if action == "set_capacity" else int(doc.capacity or 0) + int(capacity)
            if cap < 0:
                why = _("capacity would be below zero")
            elif cap < int(doc.booked or 0):
                why = _("{0} trucks are already booked").format(doc.booked)
            else:
                doc.capacity = cap
        elif action == "block":
            if doc.is_closed:
                why = _("already blocked")
            elif doc.booked and not allow_booked:
                why = _("{0} trucks are already booked").format(doc.booked)
            else:
                doc.is_closed, doc.closed_reason = 1, reason.strip()
                blocked_bookings += int(doc.booked or 0)
        elif action == "unblock":
            if not doc.is_closed:
                why = _("not blocked")
            else:
                doc.is_closed, doc.closed_reason = 0, None
        elif action == "set_scope":
            if doc.move_types == move_types:
                why = _("already set")
            elif move_types != "All" and doc.booked and not _all_fit(doc.name, move_types):
                why = _("booked trucks do not fit {0} only").format(move_types)
            else:
                doc.move_types = move_types
        if why:
            skipped.append({"slot": r.name, "label": label, "reason": why})
            continue
        if not preview:
            doc.save()
        changed.append({"slot": r.name, "label": label})
    if not preview:
        frappe.db.commit()
    return {"changed": changed, "skipped": skipped, "booked_in_blocked_slots": blocked_bookings, "preview": bool(preview)}


def _all_fit(slot, scope):
    """True when every active appointment in the slot still fits a slot that only takes Gate In or Gate Out."""
    need = "In" if scope == "Gate In" else "Out"
    return not frappe.db.exists("Appointment", {"slot": slot, "status": ["in", ["Booked", "Late", "Arrived", "In Progress"]], "direction": ["!=", need]})


@frappe.whitelist()
def add_slot(date, time_from, time_to, capacity, move_types="All", terminal=None):
    """One extra slot, for a day that needs it."""
    _need_manager()
    terminal = _terminal(terminal)
    if move_types not in SCOPES:
        frappe.throw(_("Choose which jobs the slot takes."))
    doc = frappe.get_doc({"doctype": "Slot Capacity", "terminal": terminal, "slot_date": getdate(date), "start_time": time_from,
                          "end_time": time_to, "capacity": int(capacity), "move_types": move_types})
    clash = frappe.db.exists("Slot Capacity", {"terminal": terminal, "slot_date": doc.slot_date, "start_time": doc.start_time, "move_types": move_types})
    if clash:
        frappe.throw(_("A slot at {0} already exists on {1}.").format(_hm(time_from), doc.slot_date))
    try:
        doc.insert()
    except frappe.DuplicateEntryError:
        frappe.throw(_("A slot at {0} already exists on {1}.").format(_hm(time_from), doc.slot_date))
    return {"name": doc.name}


@frappe.whitelist()
def delete_slot(name):
    _need_manager()
    doc = frappe.get_doc("Slot Capacity", name)
    doc.check_permission("delete")
    if doc.booked:
        frappe.throw(_("This slot has {0} booking(s). Block it instead.").format(doc.booked))
    doc.delete()
    return {"deleted": name}


@frappe.whitelist()
def copy_day(from_date, to_dates, terminal=None):
    """Copy the day's slots (times, capacity, scope, blocked or not) to other days. A day that already has a slot at the
    same time keeps it; nothing existing is overwritten."""
    _need_manager()
    terminal = _terminal(terminal)
    targets = frappe.parse_json(to_dates) if isinstance(to_dates, str) else to_dates
    if not targets:
        frappe.throw(_("Choose the days to copy to."))
    if len(targets) > 31:
        frappe.throw(_("Copy to at most 31 days at a time."))
    source = frappe.get_all("Slot Capacity", filters={"terminal": terminal, "slot_date": getdate(from_date)}, fields=FIELDS, order_by="start_time", limit_page_length=0)
    if not source:
        frappe.throw(_("{0} has no slots to copy.").format(from_date))
    made, kept = 0, 0
    for day in targets:
        day = getdate(day)
        if day == getdate(from_date):
            continue
        for s in source:
            if frappe.db.exists("Slot Capacity", {"terminal": terminal, "slot_date": day, "start_time": s.start_time, "move_types": s.move_types}):
                kept += 1
                continue
            try:
                frappe.get_doc({"doctype": "Slot Capacity", "terminal": terminal, "slot_date": day, "start_time": s.start_time, "end_time": s.end_time,
                                "capacity": s.capacity, "move_types": s.move_types, "is_closed": s.is_closed, "closed_reason": s.closed_reason}).insert()
                made += 1
            except frappe.DuplicateEntryError:
                kept += 1
    frappe.db.commit()
    return {"created": made, "already_there": kept}
