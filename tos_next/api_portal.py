"""Carrier portal endpoints. A carrier user sees and changes only their own carrier's trucks, drivers and
appointments. The boundary is a Frappe User Permission (user -> Carrier), and every endpoint here also checks it
itself, so a missing permission setting cannot expose another carrier's data.
Staff with an appointment role can use the page without a link (they see every carrier).

Least privilege: the Carrier Portal User role has READ-ONLY rights on Appointment, Truck and Driver. Every write a
carrier makes goes through this module, which checks carrier ownership and accepts only the fields it names, then
saves with ignore_permissions. A carrier calling the REST API directly can read their own records and change nothing.
Call as /api/method/tos_next.api_portal.<name>.
"""
import frappe
from frappe import _
from frappe.utils import add_days, get_time, getdate, now_datetime, nowdate

from tos_next.api import _terminal
from tos_next.tos_next.doctype.gate_transaction.gate_transaction import EARLY_MINUTES, LATE_MINUTES

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
        "early_minutes": EARLY_MINUTES,
        "late_minutes": LATE_MINUTES,
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
                          "booking_ref": booking_ref or None, "terminal": frappe.db.get_value("Slot Capacity", slot, "terminal")}).insert(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status, "qr_token": doc.qr_token}


@frappe.whitelist()
def portal_cancel(name, reason):
    _own(frappe.db.get_value("Appointment", name, "carrier"))
    doc = frappe.get_doc("Appointment", name)
    doc.flags.ignore_permissions = True
    doc.cancel_appointment(reason)
    return {"name": name, "status": frappe.db.get_value("Appointment", name, "status")}


# ---------- fleet self-service ----------
# Carriers may add and edit their own trucks and drivers. They may never touch block flags, move a record to
# another carrier or rename a plate: those fields are simply not accepted here.
TRUCK_TYPES = ("Tractor and Trailer", "Rigid", "Terminal Tractor")
MAX_LENGTHS = ("20 ft only", "Up to 40 ft", "Up to 45 ft")


@frappe.whitelist()
def portal_fleet():
    cars = _carriers()
    soon = add_days(nowdate(), 30)
    trucks = frappe.get_all("Truck", filters={"carrier": ["in", cars]}, order_by="plate_no",
                            fields=["name", "carrier", "plate_no", "truck_type", "max_container_length", "rfid_tag", "is_blocked", "block_reason"])
    drivers = frappe.get_all("Driver", filters={"carrier": ["in", cars]}, order_by="full_name",
                             fields=["name", "carrier", "full_name", "phone", "licence_no", "licence_expiry", "is_blocked", "block_reason"])
    for d in drivers:
        d["licence_state"] = "expired" if getdate(d.licence_expiry) < getdate(nowdate()) else "soon" if getdate(d.licence_expiry) <= getdate(soon) else "ok"
    return {"carriers": frappe.get_all("Carrier", filters={"name": ["in", cars]}, fields=["name", "carrier_name"]), "trucks": trucks, "drivers": drivers}


def _clean(v):
    return (v or "").strip() or None


@frappe.whitelist()
def portal_save_truck(carrier, plate_no=None, truck_type="Tractor and Trailer", max_container_length="Up to 40 ft", rfid_tag=None, name=None):
    _own(carrier)
    if truck_type not in TRUCK_TYPES or max_container_length not in MAX_LENGTHS:
        frappe.throw(_("Choose a valid truck type and size."))
    if name:
        doc = frappe.get_doc("Truck", name)
        _own(doc.carrier)
        if doc.is_blocked:
            frappe.throw(_("{0} is blocked by the terminal. Contact the terminal to have it released.").format(doc.name))
    else:
        plate = " ".join((plate_no or "").upper().split())
        if not plate:
            frappe.throw(_("Enter the plate number."))
        if frappe.db.exists("Truck", plate):
            frappe.throw(_("This plate number is already registered. Contact the terminal if the truck is yours."))
        doc = frappe.get_doc({"doctype": "Truck", "plate_no": plate, "carrier": carrier})
    doc.truck_type, doc.max_container_length, doc.rfid_tag = truck_type, max_container_length, _clean(rfid_tag)
    doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
    return {"name": doc.name}


@frappe.whitelist()
def portal_save_driver(carrier, full_name, licence_no, licence_expiry, phone=None, name=None):
    _own(carrier)
    full_name, licence_no = (full_name or "").strip(), (licence_no or "").strip().upper()
    if not (full_name and licence_no and licence_expiry):
        frappe.throw(_("Name, licence number and licence expiry are all required."))
    dup = frappe.db.get_value("Driver", {"licence_no": licence_no, "name": ["!=", name or ""]}, "name")
    if dup:
        frappe.throw(_("This licence number is already registered. Contact the terminal if the driver is yours."))
    if name:
        doc = frappe.get_doc("Driver", name)
        _own(doc.carrier)
        if doc.is_blocked:
            frappe.throw(_("{0} is blocked by the terminal. Contact the terminal to have the driver released.").format(doc.full_name))
    else:
        doc = frappe.get_doc({"doctype": "Driver", "carrier": carrier})
    doc.full_name, doc.licence_no, doc.licence_expiry, doc.phone = full_name, licence_no, getdate(licence_expiry), _clean(phone)
    doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
    return {"name": doc.name}
