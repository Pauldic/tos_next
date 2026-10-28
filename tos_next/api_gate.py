"""Write and lookup endpoints for the Gate and Appointments screens.
Every call goes through normal document permissions (insert / check_permission), never ignore_permissions.
Call as /api/method/tos_next.api_gate.<name>.
"""
import hmac

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from tos_next.api import _terminal
from tos_next.tos_next.doctype.appointment.appointment import slot_window
from tos_next.tos_next.doctype.gate_transaction.gate_transaction import EARLY_MINUTES, LATE_MINUTES

# action -> the only arguments the screen may pass to that Gate Transaction method
GATE_ACTIONS = {
    "record_ocr": ("container_no", "confidence"),
    "advance": ("remarks",),
    "fail_step": ("remarks",),
    "hold": ("reason",),
    "release_hold": ("note",),
    "waive_step": ("note",),
    "reject": ("reason",),
    "complete": (),
}


def _tx(gt):
    return {
        "name": gt.name, "status": gt.status, "hold_reason": gt.hold_reason, "lane": gt.lane, "direction": gt.direction,
        "truck": gt.truck, "carrier": gt.carrier, "driver": gt.driver, "move_type": gt.move_type,
        "container": gt.container or gt.container_no, "appointment": gt.appointment, "override": gt.override,
        "current_step": gt.current_step, "entered_at": gt.entered_at, "ocr_container_no": gt.ocr_container_no,
        "ocr_confidence": gt.ocr_confidence, "seal_intact": gt.seal_intact, "damage_found": gt.damage_found,
        "checks": [{"step": c.step, "result": c.result, "checked_by": c.checked_by, "remarks": c.remarks} for c in gt.checks],
    }


@frappe.whitelist()
def gate_action(transaction, action, **args):
    if action not in GATE_ACTIONS:
        frappe.throw(_("Unknown action."))
    gt = frappe.get_doc("Gate Transaction", transaction)
    gt.check_permission("write")
    allowed = GATE_ACTIONS[action]
    kwargs = {k: v for k, v in args.items() if k in allowed and v not in (None, "")}
    getattr(gt, action)(**kwargs)
    return _tx(frappe.get_doc("Gate Transaction", transaction))


@frappe.whitelist()
def start_visit(lane, carrier, truck, driver, move_type, appointment=None, override=None,
                container=None, container_no=None, booking_ref=None, seal_no=None, gross_weight_kg=None):
    doc = frappe.get_doc({
        "doctype": "Gate Transaction", "lane": lane, "carrier": carrier, "truck": truck, "driver": driver,
        "move_type": move_type, "appointment": appointment or None, "override": override or None,
        "container": container or None, "container_no": container_no or None, "booking_ref": booking_ref or None,
        "seal_no": seal_no or None, "gross_weight_kg": gross_weight_kg or None,
    }).insert()
    return _tx(doc)


@frappe.whitelist()
def lookups(carrier=None):
    out = {"carriers": frappe.get_list("Carrier", filters={"is_blocked": 0}, fields=["name", "carrier_name"], order_by="name", limit_page_length=0)}
    if carrier:
        out["trucks"] = frappe.get_list("Truck", filters={"carrier": carrier, "is_blocked": 0}, fields=["name"], order_by="name", limit_page_length=0)
        out["drivers"] = frappe.get_list("Driver", filters={"carrier": carrier, "is_blocked": 0}, fields=["name", "driver_name"], order_by="name", limit_page_length=0)
    else:
        out["trucks"], out["drivers"] = [], []
    return out


@frappe.whitelist()
def approved_overrides(terminal=None):
    terminal = _terminal(terminal)
    return frappe.get_list("Appointment Override", filters={"terminal": terminal, "status": "Approved", "valid_until": [">", now_datetime()]},
                           fields=["name", "override_type", "carrier", "truck", "appointment", "reason_category", "valid_until"],
                           order_by="valid_until asc", limit_page_length=50)


@frappe.whitelist()
def appointments_for_day(date, terminal=None):
    terminal = _terminal(terminal)
    return frappe.get_list("Appointment", filters={"terminal": terminal, "slot_date": date}, order_by="start_time asc, creation asc", limit_page_length=0,
                           fields=["name", "slot", "start_time", "end_time", "status", "move_type", "direction", "carrier", "truck", "driver", "container", "booking_ref", "override"])


@frappe.whitelist()
def book_appointment(slot, carrier, truck, driver, move_type, container=None, booking_ref=None, override=None):
    doc = frappe.get_doc({"doctype": "Appointment", "slot": slot, "carrier": carrier, "truck": truck, "driver": driver,
                          "move_type": move_type, "container": container or None, "booking_ref": booking_ref or None,
                          "override": override or None, "terminal": frappe.db.get_value("Slot Capacity", slot, "terminal")}).insert()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def cancel_appointment(name, reason):
    doc = frappe.get_doc("Appointment", name)
    doc.check_permission("write")
    doc.cancel_appointment(reason)
    return {"name": name, "status": frappe.db.get_value("Appointment", name, "status")}


@frappe.whitelist()
def pending_overrides(terminal=None):
    terminal = _terminal(terminal)
    return frappe.get_list("Appointment Override", filters={"terminal": terminal, "status": "Pending"}, order_by="creation asc", limit_page_length=50,
                           fields=["name", "override_type", "reason_category", "reason", "carrier", "truck", "appointment", "slot", "requested_by", "requested_on"])


@frappe.whitelist()
def request_override(override_type, reason_category, reason, terminal=None, carrier=None, truck=None, driver=None,
                     container=None, appointment=None, slot=None):
    terminal = _terminal(terminal)
    doc = frappe.get_doc({"doctype": "Appointment Override", "terminal": terminal, "override_type": override_type,
                          "reason_category": reason_category, "reason": reason, "carrier": carrier or None, "truck": truck or None,
                          "driver": driver or None, "container": container or None, "appointment": appointment or None, "slot": slot or None}).insert()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def decide_override(name, decision, note):
    if decision not in ("approve", "reject"):
        frappe.throw(_("Unknown decision."))
    doc = frappe.get_doc("Appointment Override", name)
    doc.check_permission("write")
    getattr(doc, decision)(note)
    return {"name": name, "status": frappe.db.get_value("Appointment Override", name, "status")}


GATE_ROLES = {"Gate Clerk", "Gate Supervisor", "Terminal Admin", "System Manager"}
APPT_FIELDS = ["name", "qr_token", "terminal", "slot", "status", "direction", "carrier", "truck", "driver", "move_type", "container", "booking_ref", "arrived_at"]


def _parse_pass(code):
    code = (code or "").strip()
    if code.upper().startswith("TOSAPPT|"):
        parts = code.split("|")
        if len(parts) != 3 or not parts[1] or not parts[2]:
            frappe.throw(_("This pass is not valid."))
        return parts[1], parts[2]
    return None, code  # a bare check-in code, typed in


@frappe.whitelist()
def scan_pass(code, terminal=None):
    """Look up a gate pass (scanned QR text or the typed check-in code). Read-only: nothing changes until a
    visit is started, and starting a visit re-runs every rule."""
    if not GATE_ROLES.intersection(frappe.get_roles()):
        frappe.throw(_("Only gate staff can scan passes."), frappe.PermissionError)
    terminal = _terminal(terminal)
    name, token = _parse_pass(code)
    if not token:
        frappe.throw(_("Scan a pass or type its code."))
    a = frappe.db.get_value("Appointment", name, APPT_FIELDS, as_dict=True) if name else frappe.db.get_value("Appointment", {"qr_token": token}, APPT_FIELDS, as_dict=True)
    if not a or not hmac.compare_digest(str(a.qr_token or ""), str(token)):
        frappe.throw(_("This pass is not valid."))
    if a.terminal != terminal:
        frappe.throw(_("This pass is for terminal {0}.").format(a.terminal))
    if a.status in ("Arrived", "In Progress"):
        frappe.throw(_("{0} has already been used (arrived {1}).").format(a.name, a.arrived_at))
    if a.status in ("Completed", "Cancelled"):
        frappe.throw(_("{0} is {1}.").format(a.name, a.status))
    if a.status == "No-show":
        frappe.throw(_("{0} was marked no-show. A supervisor must decide what to do.").format(a.name))

    start, end = slot_window(frappe.get_cached_doc("Slot Capacity", a.slot))
    opens, closes, now = add_to_date(start, minutes=-EARLY_MINUTES), add_to_date(end, minutes=LATE_MINUTES), now_datetime()
    state = "early" if now < opens else "late" if now > closes else "ok"
    minutes = int((opens - now).total_seconds() // 60) if state == "early" else int((now - closes).total_seconds() // 60) if state == "late" else 0

    blockers = []
    carrier = frappe.db.get_value("Carrier", a.carrier, ["is_blocked", "block_reason", "carrier_name"], as_dict=True)
    if carrier.is_blocked:
        blockers.append(_("Carrier is blocked: {0}").format(carrier.block_reason or ""))
    truck = frappe.db.get_value("Truck", a.truck, ["is_blocked", "block_reason"], as_dict=True)
    if truck.is_blocked:
        blockers.append(_("Truck is blocked: {0}").format(truck.block_reason or ""))
    try:
        frappe.get_doc("Driver", a.driver).assert_can_work()
    except frappe.ValidationError as e:
        blockers.append(frappe.utils.strip_html(str(e)))
    if a.direction == "Out" and a.container and frappe.db.get_value("Container", a.container, "is_on_hold"):
        blockers.append(_("{0} is on hold.").format(a.container))
    frappe.local.message_log = []  # the checks above are advice here; do not show them as popups

    return {
        "appointment": a.name, "status": a.status, "direction": a.direction, "move_type": a.move_type,
        "carrier": a.carrier, "carrier_name": carrier.carrier_name, "truck": a.truck, "driver": a.driver,
        "driver_name": frappe.db.get_value("Driver", a.driver, "full_name"), "container": a.container, "booking_ref": a.booking_ref,
        "slot_start": start.strftime("%H:%M"), "slot_end": end.strftime("%H:%M"),
        "window": {"state": state, "minutes": minutes, "opens": opens.strftime("%H:%M"), "closes": closes.strftime("%H:%M")},
        "needs_override": "Outside Slot Window" if state != "ok" else None,
        "blockers": blockers,
    }
