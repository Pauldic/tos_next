"""Everything needed to test TOS Next end to end: users, equipment, a carrier with a blocked truck and an expired
driver, container holds, and fresh appointments for 'now'. Builds on demo_data.seed.

    bench --site tos.test execute tos_next.setup.test_kit.setup          # first time (safe to run again)
    bench --site tos.test execute tos_next.setup.test_kit.refresh_today  # new appointments for the current hour
    bench --site tos.test execute tos_next.setup.test_kit.show           # logins, addresses, pass codes

Every test user has the same password (PASSWORD below). Test data only: never run this on production.
"""
import frappe
from frappe.utils import add_days, add_to_date, get_time, getdate, nowdate, now_datetime
from frappe.utils.password import update_password

from tos_next.setup import demo_data
from tos_next.setup.portal_user import create as create_portal_user

PASSWORD = "PaulPaul@123"
TERMINAL = "T2"
CARRIER_1, CARRIER_2 = "Harbor Haul", "Redline Freight"

STAFF = [
    # email, first name, roles
    ("planner@tos.test", "Planner", ["Yard Planner", "Appointment Planner"]),
    ("clerk@tos.test", "Clerk", ["Gate Clerk"]),
    ("supervisor@tos.test", "Supervisor", ["Gate Supervisor"]),
    ("supervisor2@tos.test", "Supervisor Two", ["Gate Supervisor"]),
    ("operator1@tos.test", "Operator One", ["Equipment Operator"]),
    ("operator2@tos.test", "Operator Two", ["Equipment Operator"]),
]
PORTAL = [("carrier1@tos.test", CARRIER_1), ("carrier2@tos.test", CARRIER_2)]
EQUIPMENT = [
    # code, type, max tier, handles 40 ft
    ("RS-01", "Reach Stacker", 4, 1),
    ("RS-02", "Reach Stacker", 4, 1),
    ("RTG-01", "RTG", 5, 1),
    ("TT-01", "Terminal Tractor", 1, 1),   # cannot reach above tier 1: a good refusal test
    ("EH-01", "Empty Handler", 3, 0),      # 20 ft only: a good refusal test
]


def _staff_user(email, first, roles):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": first, "user_type": "System User",
                        "send_welcome_email": 0, "enabled": 1}).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    have = {r.role for r in user.roles}
    for role in roles:
        if role not in have:
            user.append("roles", {"role": role})
    user.enabled = 1
    user.save(ignore_permissions=True)


def _setup_people():
    for email, first, roles in STAFF:
        _staff_user(email, first, roles)
    for email, carrier in PORTAL:
        create_portal_user(email, carrier, first_name=email.split("@")[0].replace("carrier", "Carrier "))
    for email, *_ in STAFF + PORTAL:
        update_password(email, PASSWORD)  # skips the strength check on purpose: these are throwaway test logins
    frappe.db.commit()


def _setup_equipment():
    for code, kind, tier, forty in EQUIPMENT:
        if not frappe.db.exists("Equipment", code):
            frappe.get_doc({"doctype": "Equipment", "equipment_code": code, "terminal": TERMINAL, "equipment_type": kind,
                            "status": "Available", "max_lift_tier": tier, "handles_forty": forty, "capacity_tonnes": 45}).insert(ignore_permissions=True)


def _setup_blocks():
    """A blocked truck and an expired driver under carrier 1, to test the refusals."""
    if not frappe.db.exists("Truck", "DEMO BLK 01"):
        frappe.get_doc({"doctype": "Truck", "plate_no": "DEMO BLK 01", "carrier": CARRIER_1, "max_container_length": "Up to 45 ft",
                        "is_blocked": 1, "block_reason": "Unpaid gate fees (test)"}).insert(ignore_permissions=True)
    if not frappe.db.exists("Driver", {"licence_no": "DEMO-LIC-EXPIRED"}):
        frappe.get_doc({"doctype": "Driver", "full_name": "Expired Licence Driver", "carrier": CARRIER_1, "licence_no": "DEMO-LIC-EXPIRED",
                        "licence_expiry": add_days(nowdate(), -3)}).insert(ignore_permissions=True)


def _tops(extra=None, limit=10):
    """Containers that are on top of their stack (so they can leave), with no active appointment and no hold."""
    flt = {"terminal": TERMINAL, "status": "On Terminal", "is_on_hold": 0, "yard_stack": ["is", "set"]}
    flt.update(extra or {})
    out = []
    for c in frappe.get_all("Container", filters=flt, fields=["name", "yard_stack", "tier", "cargo_status", "length_ft"], order_by="arrived_on asc", limit_page_length=300):
        if c.tier == frappe.db.get_value("Yard Stack", c.yard_stack, "tier_count") and not frappe.db.exists("Appointment", {"container": c.name, "status": ["in", ["Booked", "Late", "Arrived", "In Progress"]]}):
            out.append(c)
        if len(out) >= limit:
            break
    return out


def _setup_holds():
    if frappe.db.exists("Container Hold", {"reference": "TESTKIT", "status": "Active"}):
        return
    for c in _tops({"cargo_status": ["in", ["Export", "Empty"]]}, limit=2):
        frappe.get_doc({"doctype": "Container Hold", "container": c.name, "terminal": TERMINAL, "hold_type": "Customs",
                        "reason": "Test hold: customs inspection pending.", "reference": "TESTKIT", "status": "Active"}).insert(ignore_permissions=True)


def _now_slot():
    """A slot that contains the current moment (so a truck can be admitted right now). Reuses an existing one."""
    now = now_datetime()
    today = getdate(nowdate())
    for s in frappe.get_all("Slot Capacity", filters={"terminal": TERMINAL, "slot_date": today, "is_closed": 0, "move_types": "All"},
                            fields=["name", "start_time", "end_time", "capacity", "booked"]):
        start = frappe.utils.get_datetime(f"{today} {get_time(s.start_time)}")
        end = frappe.utils.get_datetime(f"{today} {get_time(s.end_time)}")
        if add_to_date(start, minutes=-30) <= now <= add_to_date(end, minutes=60) and s.booked < s.capacity:
            return s.name
    start = now.replace(minute=0, second=0, microsecond=0)
    end = min(add_to_date(start, hours=3), now.replace(hour=23, minute=59, second=59, microsecond=0))
    doc = frappe.get_doc({"doctype": "Slot Capacity", "terminal": TERMINAL, "slot_date": today, "start_time": start.strftime("%H:%M:%S"),
                          "end_time": end.strftime("%H:%M:%S"), "capacity": 10, "move_types": "All"})
    if frappe.db.exists("Slot Capacity", doc.autoname() or f"{TERMINAL}-{today}-{start.strftime('%H%M')}"):
        return f"{TERMINAL}-{today}-{start.strftime('%H%M')}"
    doc.insert(ignore_permissions=True)
    return doc.name


def _parties(carrier, n=2):
    trucks = frappe.get_all("Truck", filters={"carrier": carrier, "is_blocked": 0}, pluck="name", order_by="name", limit_page_length=n)
    drivers = frappe.get_all("Driver", filters={"carrier": carrier, "is_blocked": 0, "licence_expiry": [">", add_days(nowdate(), 30)]},
                             pluck="name", order_by="name", limit_page_length=n)
    return trucks, drivers


def _next_n():
    return frappe.db.count("Appointment", {"booking_ref": ["like", "TESTKIT-%"]}) // 3 + 1


def refresh_today():
    """Cancel unused test appointments and book a fresh set around the current hour."""
    frappe.set_user("Administrator")
    # retire the previous set
    for a in frappe.get_all("Appointment", filters={"booking_ref": ["like", "TESTKIT-%"], "status": ["in", ["Booked", "Late"]]}, pluck="name"):
        doc = frappe.get_doc("Appointment", a)
        doc.cancel_appointment("Test refresh")
    for o in frappe.get_all("Appointment Override", filters={"status": "Pending", "reason": ["like", "TESTKIT%"]}, pluck="name"):
        frappe.set_user("supervisor@tos.test")
        try:
            frappe.get_doc("Appointment Override", o).reject("Test refresh")
        except Exception:
            pass
        frappe.set_user("Administrator")

    n = _next_n()
    slot = _now_slot()
    t1, d1 = _parties(CARRIER_1)
    t2, d2 = _parties(CARRIER_2)
    made = {}

    # 1. clean Gate In, carrier 1, in the current window
    made["gate_in"] = frappe.get_doc({"doctype": "Appointment", "slot": slot, "move_type": "Export Drop", "carrier": CARRIER_1, "truck": t1[0], "driver": d1[0],
                                      "booking_ref": f"TESTKIT-{n}-IN"}).insert(ignore_permissions=True).name

    # 2. clean Gate Out, carrier 2: pick up an import container that sits on top of its stack
    pick = _tops({"cargo_status": "Import"}, limit=1)
    if pick:
        made["gate_out"] = frappe.get_doc({"doctype": "Appointment", "slot": slot, "move_type": "Import Pickup", "carrier": CARRIER_2, "truck": t2[0], "driver": d2[0],
                                           "container": pick[0].name, "booking_ref": f"TESTKIT-{n}-OUT"}).insert(ignore_permissions=True).name

    # 3. a slot far from now (next weekday 10:00): the truck is 'too early', so it needs an override
    later = frappe.get_all("Slot Capacity", filters={"terminal": TERMINAL, "slot_date": [">", nowdate()], "start_time": "10:00:00", "is_closed": 0},
                           pluck="name", order_by="slot_date asc", limit=1)
    if later:
        early = frappe.get_doc({"doctype": "Appointment", "slot": later[0], "move_type": "Export Drop", "carrier": CARRIER_1, "truck": t1[1], "driver": d1[1],
                                "booking_ref": f"TESTKIT-{n}-EARLY"}).insert(ignore_permissions=True)
        made["too_early"] = early.name
        # the clerk asks for an override; the supervisor approves it during the test
        frappe.set_user("clerk@tos.test")
        try:
            ov = frappe.get_doc({"doctype": "Appointment Override", "terminal": TERMINAL, "override_type": "Outside Slot Window", "reason_category": "Vessel Delay",
                                 "appointment": early.name, "carrier": CARRIER_1, "truck": t1[1],
                                 "reason": f"TESTKIT {n}: the vessel was delayed, so this truck must be received before its slot."}).insert()
            made["override"] = ov.name
        finally:
            frappe.set_user("Administrator")
    frappe.db.commit()
    return made


def setup():
    """Create everything. Safe to run again."""
    frappe.set_user("Administrator")
    demo_data.seed(terminal=TERMINAL if frappe.db.exists("Terminal", TERMINAL) else None)
    _setup_people()
    _setup_equipment()
    _setup_blocks()
    try:
        _setup_holds()
    except Exception as e:  # holds are a nice-to-have for the 3D yard filter; never block the rest of the setup
        frappe.db.rollback()
        print(f"Note: could not create the test holds ({type(e).__name__}: {str(e)[:120]}). Everything else was created.")
    frappe.db.commit()
    made = refresh_today()
    print("Test data is ready.\n")
    show()
    return made


def show():
    """Print logins, addresses and the pass codes of the test appointments."""
    base = frappe.utils.get_url()
    print(f"Site address : {base}   (if you use the Vite dev server, use its address instead, same paths)")
    print(f"Password     : {PASSWORD}   (same for every test user)\n")
    print("Who                    Login                    Where to go")
    rows = [("Planner", "planner@tos.test", "/tos/yard  /tos/appointments"), ("Gate clerk", "clerk@tos.test", "/tos/gate"),
            ("Supervisor", "supervisor@tos.test", "/tos/appointments (Overrides tab)  /tos/gate"), ("Supervisor 2", "supervisor2@tos.test", "same as supervisor"),
            ("Operator 1", "operator1@tos.test", "/tos/ops"), ("Operator 2", "operator2@tos.test", "/tos/ops"),
            (f"Carrier: {CARRIER_1}", "carrier1@tos.test", "/tos/portal"), (f"Carrier: {CARRIER_2}", "carrier2@tos.test", "/tos/portal")]
    for who, email, where in rows:
        print(f"{who:22} {email:24} {where}")
    print("\nTest appointments (type the CODE in Gate -> Scan pass):")
    for a in frappe.get_all("Appointment", filters={"booking_ref": ["like", "TESTKIT-%"], "status": ["in", ["Booked", "Late", "Arrived"]]},
                            fields=["name", "booking_ref", "carrier", "truck", "move_type", "container", "status", "slot", "qr_token"], order_by="creation desc", limit_page_length=6):
        print(f"  {a.booking_ref:18} {a.status:8} code {a.qr_token}   {a.carrier} / {a.truck} / {a.move_type}" + (f" / {a.container}" if a.container else "") + f"   slot {a.slot}")
    ov = frappe.get_all("Appointment Override", filters={"status": "Pending", "reason": ["like", "TESTKIT%"]}, pluck="name")
    print(f"\nPending override waiting for the supervisor: {', '.join(ov) or 'none'}")
    print("Equipment: " + ", ".join(frappe.get_all("Equipment", filters={"terminal": TERMINAL}, pluck="name", order_by="name")))
    print("Containers on hold (test): " + ", ".join(frappe.get_all("Container Hold", filters={"reference": "TESTKIT", "status": "Active"}, pluck="container")))
