"""Write and lookup endpoints for the Gate and Appointments screens.
Every call goes through normal document permissions (insert / check_permission), never ignore_permissions.
Call as /api/method/tos_next.api_gate.<name>.
"""
import hmac

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from tos_next import transactions
from tos_next.api import _terminal
from tos_next.tos_next.doctype.appointment.appointment import slot_window
from tos_next.settings import gate_window

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
def start_visit(lane, carrier, truck, driver, move_type=None, appointment=None, override=None, appointment_line=None,
                container=None, container_no=None, container_type=None, shipping_line=None, booking_ref=None, seal_no=None, gross_weight_kg=None):
    # A container typed at the gate that is not in the system yet is a NEW container: it needs a number and a type.
    if container and not frappe.db.exists("Container", container):
        container_no, container = container, None
    doc = frappe.get_doc({
        "doctype": "Gate Transaction", "lane": lane, "carrier": carrier, "truck": truck, "driver": driver,
        "move_type": move_type or _default_transaction(lane), "appointment": appointment or None, "override": override or None,
        "container": container or None, "container_no": container_no or None, "container_type": container_type or None, "shipping_line": shipping_line or None, "booking_ref": booking_ref or None,
        "seal_no": seal_no or None, "gross_weight_kg": gross_weight_kg or None,
    })
    doc.flags.appointment_line = appointment_line or None
    doc.insert()
    return _tx(doc)


@frappe.whitelist()
def set_container_details(transaction, container_no=None, container_type=None, shipping_line=None):
    """Fill in the number and type of a NEW container on a Gate In visit that is already under way."""
    gt = frappe.get_doc("Gate Transaction", transaction)
    gt.check_permission("write")
    if gt.direction != "In":
        frappe.throw(_("Only a Gate In visit can have a new container."))
    if gt.status not in ("Processing", "On Hold"):
        frappe.throw(_("This visit is {0}, so its container can no longer be changed.").format(gt.status))
    if gt.container:
        frappe.throw(_("This visit already has the container {0}.").format(gt.container))
    if container_type:
        if not frappe.db.exists("Container Type", container_type):
            frappe.throw(_("Unknown container type {0}.").format(container_type))
        gt.container_type = container_type
    if container_no:
        gt.container_no = container_no
    if shipping_line:
        if not frappe.db.exists("Shipping Line", shipping_line):
            frappe.throw(_("Unknown shipping line {0}.").format(shipping_line))
        gt.shipping_line = shipping_line
    if not (gt.container_no and gt.container_type):
        frappe.throw(_("Give both the container number and the container type."))
    gt.save()
    gt.add_comment("Info", _("Container details set by {0}: {1} ({2})").format(frappe.session.user, gt.container_no, gt.container_type))
    return _tx(frappe.get_doc("Gate Transaction", transaction))


@frappe.whitelist()
def shipping_lines():
    return frappe.get_list("Shipping Line", filters={"is_active": 1}, fields=["name", "line_name"], order_by="line_name", limit_page_length=0)


@frappe.whitelist()
def container_types():
    return frappe.get_list("Container Type", filters={"is_active": 1}, fields=["name", "description", "length_ft"], order_by="length_ft, name", limit_page_length=0)


@frappe.whitelist()
def lookups(carrier=None):
    out = {"carriers": frappe.get_list("Carrier", filters={"is_blocked": 0}, fields=["name", "carrier_name"], order_by="name", limit_page_length=0),
           "transaction_types": transactions.offered(None),
           "chassis_types": frappe.get_all("Chassis Type", filters={"is_active": 1}, fields=["name", "max_container_length_ft", "max_containers", "max_total_length_ft"]),
           "container_lengths": sorted({int(x) for x in frappe.get_all("Container Type", filters={"is_active": 1}, pluck="length_ft") if x})}
    if carrier:
        out["trucks"] = frappe.get_list("Truck", filters={"carrier": carrier, "is_blocked": 0}, fields=["name", "chassis_type"], order_by="name", limit_page_length=0)
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
    rows = frappe.get_list("Appointment", filters={"terminal": terminal, "slot_date": date}, order_by="start_time asc, creation asc", limit_page_length=0,
                           fields=["name", "slot", "start_time", "end_time", "status", "move_type", "direction", "visit_type", "carrier", "truck", "driver", "container", "booking_ref", "override"])
    return attach_lines(rows)


LINE_FIELDS = ["name", "parent", "idx", "move_type", "container", "container_length", "booking_ref", "status", "gate_transaction"]


def attach_lines(rows):
    """Adds the list of jobs ('lines') to each appointment row, with one query for all of them."""
    names = [r["name"] for r in rows]
    by = {}
    if names:
        for l in frappe.get_all("Appointment Line", filters={"parent": ["in", names], "parenttype": "Appointment"}, fields=LINE_FIELDS, order_by="idx asc", limit_page_length=0):
            by.setdefault(l.parent, []).append(l)
    for r in rows:
        r["lines"] = by.get(r["name"], [])
        for l in r["lines"]:
            l["direction"] = transactions.direction(l["move_type"])
    return rows


@frappe.whitelist()
def book_appointment(slot, carrier, truck, driver, lines=None, move_type=None, container=None, booking_ref=None, override=None):
    """lines: a list of jobs, each {move_type, container?, container_length?, booking_ref?}. The older single-job
    arguments (move_type, container, booking_ref) still work and make one job."""
    jobs = clean_lines(lines)
    doc = frappe.get_doc({"doctype": "Appointment", "slot": slot, "carrier": carrier, "truck": truck, "driver": driver,
                          "move_type": None if jobs else move_type, "container": None if jobs else (container or None),
                          "booking_ref": None if jobs else (booking_ref or None), "lines": jobs,
                          "override": override or None, "terminal": frappe.db.get_value("Slot Capacity", slot, "terminal")}).insert()
    return {"name": doc.name, "status": doc.status}


JOB_FIELDS = ("move_type", "container", "container_length", "booking_ref")


def clean_lines(lines):
    """Accepts the jobs as sent by a screen (a list, or JSON text) and keeps only the fields a job may carry."""
    if isinstance(lines, str):
        lines = frappe.parse_json(lines) if lines.strip() else []
    out = []
    for l in lines or []:
        row = {k: (l.get(k) if l.get(k) not in ("", None) else None) for k in JOB_FIELDS}
        if row["container"]:
            row["container"] = str(row["container"]).strip().upper().replace(" ", "").replace("-", "")
        out.append(row)
    return out


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
    lines = frappe.get_all("Appointment Line", filters={"parent": a.name, "parenttype": "Appointment"}, fields=LINE_FIELDS, order_by="idx asc")
    pending = [l for l in lines if l.status == "Pending"]
    if a.status == "Arrived":
        frappe.throw(_("{0} already has a visit under way (arrived {1}). Finish or reject it first.").format(a.name, a.arrived_at))
    if a.status == "In Progress" and not pending:
        frappe.throw(_("{0} has no job left.").format(a.name))
    if a.status in ("Completed", "Cancelled"):
        frappe.throw(_("{0} is {1}.").format(a.name, a.status))
    if a.status == "No-show":
        frappe.throw(_("{0} was marked no-show. A supervisor must decide what to do.").format(a.name))

    start, end = slot_window(frappe.get_cached_doc("Slot Capacity", a.slot))
    early, late = gate_window(a.terminal)
    opens, closes, now = add_to_date(start, minutes=-early), add_to_date(end, minutes=late), now_datetime()
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
    for l in pending:
        if not transactions.is_in(l.move_type) and l.container and frappe.db.get_value("Container", l.container, "is_on_hold"):
            blockers.append(_("{0} is on hold.").format(l.container))
    frappe.local.message_log = []  # the checks above are advice here; do not show them as popups

    return {
        "appointment": a.name, "status": a.status, "direction": a.direction, "move_type": a.move_type,
        "carrier": a.carrier, "carrier_name": carrier.carrier_name, "truck": a.truck, "driver": a.driver,
        "driver_name": frappe.db.get_value("Driver", a.driver, "full_name"), "container": a.container, "booking_ref": a.booking_ref,
        "visit_type": frappe.db.get_value("Appointment", a.name, "visit_type"), "lines": [dict(l, direction=transactions.direction(l.move_type)) for l in lines], "pending": [l.name for l in pending],
        "slot_start": start.strftime("%H:%M"), "slot_end": end.strftime("%H:%M"),
        "window": {"state": state, "minutes": minutes, "opens": opens.strftime("%H:%M"), "closes": closes.strftime("%H:%M")},
        "needs_override": "Outside Slot Window" if state != "ok" else None,
        "blockers": blockers,
    }


def _default_transaction(lane):
    """When a visit names no transaction (an appointment will fill it in), use the first active one that fits the lane."""
    direction = frappe.db.get_value("Gate Lane", lane, "direction")
    return frappe.db.get_value("Transaction Type", {"is_active": 1, "direction": direction}, "name", order_by="sort_order asc")


@frappe.whitelist()
def transaction_types(terminal=None):
    """The transactions this terminal offers (Receive Import, Deliver Empty ...), with the rules each carries."""
    return transactions.offered(_terminal(terminal))
