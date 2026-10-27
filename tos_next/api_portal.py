"""Carrier portal endpoints. A carrier user sees and changes only their own carrier's trucks, drivers and
appointments. The boundary is a Frappe User Permission (user -> Carrier), and every endpoint here also checks it
itself, so a missing permission setting cannot expose another carrier's data.
Staff with an appointment role can use the page without a link (they see every carrier).
Call as /api/method/tos_next.api_portal.<name>.
"""
import frappe
from frappe import _
from frappe.utils import add_days, get_time, getdate, now_datetime, nowdate

from tos_next.api import _terminal

STAFF = {"System Manager", "Terminal Admin", "Appointment Planner"}
IN_MOVES = ("Export Drop", "Empty Return")
OUT_MOVES = ("Import Pickup", "Empty Pickup")


def _carriers():
    mine = frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": "Carrier"}, pluck="for_value")
    if mine:
        return mine
    if STAFF.intersection(frappe.get_roles()):
        return frappe.get_all("Carrier", pluck="name")
    frappe.throw(_("Your login is not linked to a carrier. Ask the terminal to link it."), frappe.PermissionError)


def _own(carrier):
    if carrier not in _carriers():
        frappe.throw(_("That carrier is not yours."), frappe.PermissionError)


def _hhmm(t):
    return str(get_time(t))[:5]


@frappe.whitelist()
def portal_context(terminal=None):
    cars = _carriers()
    terminal = _terminal(terminal)
    return {
        "terminal": terminal,
        "terminal_name": frappe.db.get_value("Terminal", terminal, "terminal_name"),
        "require_appointment": frappe.db.get_value("Terminal", terminal, "require_appointment"),
        "carriers": frappe.get_all("Carrier", filters={"name": ["in", cars]}, fields=["name", "carrier_name", "is_blocked", "block_reason"]),
        "trucks": frappe.get_all("Truck", filters={"carrier": ["in", cars], "is_blocked": 0}, fields=["name", "carrier", "max_container_length"], order_by="name"),
        "drivers": frappe.get_all("Driver", filters={"carrier": ["in", cars], "is_blocked": 0}, fields=["name", "full_name", "carrier"], order_by="full_name"),
    }


@frappe.whitelist()
def portal_slots(date, move_type, terminal=None):
    _carriers()
    terminal = _terminal(terminal)
    direction = "In" if move_type in IN_MOVES else "Out"
    d = getdate(date)
    if d < getdate(nowdate()):
        return []
    rows = frappe.get_all("Slot Capacity", filters={"terminal": terminal, "slot_date": d, "is_closed": 0, "move_types": ["in", ["All", f"Gate {direction}"]]},
                          fields=["name", "start_time", "end_time", "capacity", "booked"], order_by="start_time asc")
    now_t = now_datetime().time()
    out = []
    for r in rows:
        if d == getdate(nowdate()) and get_time(r.end_time) <= now_t:
            continue
        out.append({"name": r.name, "start": _hhmm(r.start_time), "end": _hhmm(r.end_time), "left": max(0, int(r.capacity or 0) - int(r.booked or 0))})
    return out


@frappe.whitelist()
def portal_appointments():
    cars = _carriers()
    return frappe.get_all("Appointment", filters={"carrier": ["in", cars], "slot_date": [">=", add_days(nowdate(), -1)]},
                          fields=["name", "slot_date", "start_time", "end_time", "status", "move_type", "direction", "carrier", "truck", "driver", "container", "booking_ref", "qr_token"],
                          order_by="slot_date asc, start_time asc", limit_page_length=100)


@frappe.whitelist()
def portal_book(slot, carrier, truck, driver, move_type, container=None, booking_ref=None):
    _own(carrier)
    doc = frappe.get_doc({"doctype": "Appointment", "slot": slot, "carrier": carrier, "truck": truck, "driver": driver, "move_type": move_type,
                          "container": (container or "").strip().upper().replace(" ", "").replace("-", "") or None,
                          "booking_ref": booking_ref or None, "terminal": frappe.db.get_value("Slot Capacity", slot, "terminal")}).insert()
    return {"name": doc.name, "status": doc.status, "qr_token": doc.qr_token}


@frappe.whitelist()
def portal_cancel(name, reason):
    _own(frappe.db.get_value("Appointment", name, "carrier"))
    doc = frappe.get_doc("Appointment", name)
    doc.check_permission("write")
    doc.cancel_appointment(reason)
    return {"name": name, "status": frappe.db.get_value("Appointment", name, "status")}
