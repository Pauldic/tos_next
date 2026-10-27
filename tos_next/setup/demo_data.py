"""Demo data and rule checks for TOS Next.

Put this file at  tos_next/setup/demo_data.py  and run, from the bench folder:

    bench --site yoursite execute tos_next.setup.demo_data.seed
    bench --site yoursite execute tos_next.setup.demo_data.run_checks

Both are safe to run again: seed skips what exists, run_checks creates uniquely named test records.
Pass a terminal that already exists:

    bench --site yoursite execute tos_next.setup.demo_data.seed --kwargs "{'terminal': 'YOUR-TERMINAL'}"
"""
import random

import frappe
from frappe.utils import add_days, getdate, nowdate

from tos_next import yard
from tos_next.tos_next.doctype.container.container import iso6346_check_digit
from tos_next.tos_next.doctype.slot_template.slot_template import generate_slots

BLOCK_TYPES = ["Import", "Export", "Empty", "Reefer"]

LINES = [
    ("NWD", "Northwind", "#7FA9C9"),
    ("AZR", "Azure Reach", "#5FB3A1"),
    ("KST", "Kestrel", "#C98A62"),
    ("SLM", "Saltmere", "#A18BCB"),
]
TYPES = [
    # iso_type, length, height, reefer, tare, max gross
    ("22G1", "20", "Standard", 0, 2200, 30480),
    ("42G1", "40", "Standard", 0, 3700, 30480),
    ("45G1", "45", "High Cube", 0, 4800, 32500),
    ("45R1", "45", "High Cube", 1, 4900, 32500),
]
CARRIERS = ["Harbor Haul", "Redline Freight", "Omega Logistics", "Greyline Cartage"]


def _ensure(doctype, name, **fields):
    """Insert the document if it does not exist yet. Returns its name."""
    if frappe.db.exists(doctype, name):
        return name
    doc = frappe.get_doc({"doctype": doctype, **fields})
    doc.insert(ignore_permissions=True)
    return doc.name


def _letters(rnd, n):
    return "".join(rnd.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(n))


def _container_no(rnd, prefix3):
    body = prefix3 + "U" + "".join(str(rnd.randint(0, 9)) for _ in range(6))
    return body + str(iso6346_check_digit(body))


def _random_place(container_type, terminal, rnd, tries=80):
    """Pick a random stack where this container fits (20 ft: any stack. 40/45 ft: anchor bay with an equal neighbour)."""
    stacks = frappe.get_all("Yard Stack", filters={"terminal": terminal, "is_blocked": 0}, pluck="name")
    for _ in range(tries):
        s = rnd.choice(stacks)
        try:
            yard.check_can_place(s, container_type)
            return s
        except frappe.ValidationError:
            frappe.clear_messages()
    return None


# ---------------------------------------------------------------------------
def seed(terminal=None, blocks="A,B,C,D", bays=10, rows=6, containers=120, seed_value=7):
    """Create a working yard: blocks and stacks, types, lines, carriers, trucks, drivers, slots, containers, lanes."""
    rnd = random.Random(seed_value)
    bays, rows = int(bays), int(rows)
    if bays % 2:
        frappe.throw("bays must be even, for example 10")

    # terminal
    if not terminal:
        terminal = _ensure("Terminal", "T2", terminal_code="T2", terminal_name="Terminal 2", is_active=1, max_tier=5)
    elif not frappe.db.exists("Terminal", terminal):
        frappe.throw(f"Terminal {terminal} does not exist. Create it first or leave terminal out.")

    # yard blocks and stacks
    for i, code in enumerate([b.strip() for b in blocks.split(",") if b.strip()]):
        name = f"{terminal}-{code}"
        if not frappe.db.exists("Yard Block", name):
            blk = frappe.get_doc({
                "doctype": "Yard Block", "terminal": terminal, "block_code": code,
                "block_type": BLOCK_TYPES[i % len(BLOCK_TYPES)], "bay_count": bays, "row_count": rows, "max_tier": 4,
                "origin_x": (i % 2) * 260, "origin_y": (i // 2) * 320, "is_active": 1,
            })
            blk.insert(ignore_permissions=True)
        else:
            blk = frappe.get_doc("Yard Block", name)
        blk.generate_stacks()

    # container types, lines
    for iso, length, height, reefer, tare, gross in TYPES:
        _ensure("Container Type", iso, iso_type=iso, length_ft=length, height=height, is_reefer=reefer,
                tare_kg=tare, max_gross_kg=gross, description=f"{length} ft {height}")
    for code, name, colour in LINES:
        _ensure("Shipping Line", code, line_code=code, line_name=name, colour=colour, iso_prefixes=f"{code}U")

    # carriers, trucks, drivers
    for c in CARRIERS:
        _ensure("Carrier", c, carrier_name=c, daily_appointment_limit=0)
    for ci, c in enumerate(CARRIERS):
        for k in range(2):
            plate = f"DEMO {ci}{k} {_letters(rnd, 2)}"
            if not frappe.db.exists("Truck", plate):
                _ensure("Truck", plate, plate_no=plate, carrier=c, max_container_length="Up to 45 ft")
            lic = f"DEMO-LIC-{ci}{k}"
            if not frappe.db.exists("Driver", {"licence_no": lic}):
                frappe.get_doc({
                    "doctype": "Driver", "full_name": f"Driver {ci}{k}", "carrier": c, "licence_no": lic,
                    "licence_expiry": add_days(nowdate(), 365),
                }).insert(ignore_permissions=True)

    # gate lanes
    for code, direction in [("IN-1", "In"), ("IN-2", "In"), ("IN-3", "In"), ("OUT-1", "Out"), ("OUT-2", "Out"), ("OUT-3", "Out")]:
        _ensure("Gate Lane", f"{terminal}-{code}", terminal=terminal, lane_code=code, direction=direction, status="Open")

    # appointment slots: hourly 06:00 to 22:00, Monday to Friday, 36 trucks an hour
    tname = f"{terminal}-Weekdays"
    if not frappe.db.exists("Slot Template", tname):
        lines = [{"from_time": f"{h:02d}:00:00", "to_time": f"{h + 1:02d}:00:00", "capacity_trucks": 36, "move_types": "All"} for h in range(6, 22)]
        frappe.get_doc({"doctype": "Slot Template", "terminal": terminal, "template_name": "Weekdays",
                        "saturday": 0, "sunday": 0, "lines": lines}).insert(ignore_permissions=True)
    made = generate_slots(template=tname, days_ahead=14)

    # containers on the ground
    placed = 0
    existing = frappe.db.count("Container", {"terminal": terminal, "status": "On Terminal"})
    for _ in range(max(0, int(containers) - existing)):
        iso = rnd.choices([t[0] for t in TYPES], weights=[40, 20, 30, 10])[0]
        line = rnd.choice(LINES)
        no = _container_no(rnd, line[0])
        if frappe.db.exists("Container", no):
            continue
        stack = _random_place(iso, terminal, rnd)
        if not stack:
            break
        cargo = "Reefer" if iso == "45R1" else rnd.choice(["Import", "Export", "Empty"])
        c = frappe.get_doc({
            "doctype": "Container", "container_no": no, "terminal": terminal, "shipping_line": line[0],
            "container_type": iso, "cargo_status": cargo, "status": "On Terminal",
            "arrived_on": frappe.utils.add_to_date(None, days=-rnd.randint(0, 8)),
            "gross_weight_kg": rnd.randint(8000, 26000), "seal_no": f"SL{rnd.randint(100000, 999999)}",
        }).insert(ignore_permissions=True)
        yard.log_movement(c, "Gate In")
        yard.move_container(c.name, stack, "Yard Move")
        placed += 1

    # a few appointments for the next working days
    slots = frappe.get_all("Slot Capacity", filters={"terminal": terminal, "slot_date": [">", nowdate()], "start_time": "10:00:00"},
                           pluck="name", order_by="slot_date asc", limit=3)
    booked = 0
    for i, slot in enumerate(slots):
        truck = frappe.get_all("Truck", filters={"plate_no": ["like", f"DEMO {i}%"]}, fields=["name", "carrier"], limit=1)
        driver = frappe.get_all("Driver", filters={"carrier": CARRIERS[i]}, pluck="name", limit=1)
        if truck and driver and not frappe.db.exists("Appointment", {"slot": slot, "truck": truck[0].name}):
            frappe.get_doc({"doctype": "Appointment", "slot": slot, "move_type": "Export Drop", "carrier": truck[0].carrier,
                            "truck": truck[0].name, "driver": driver[0], "booking_ref": f"DEMO-BK-{i + 1}"}).insert(ignore_permissions=True)
            booked += 1

    frappe.db.commit()
    return {"terminal": terminal, "stacks": frappe.db.count("Yard Stack", {"terminal": terminal}),
            "slots_created": made, "containers_placed": placed, "appointments": booked}


# ---------------------------------------------------------------------------
def _user(email, role):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
                            "roles": [{"role": role}]})
        u.insert(ignore_permissions=True)
    return email


def cleanup_checks():
    """Free any lane left busy by an interrupted run_checks. Test visits are the ones booked as TEST-xxxx."""
    rows = frappe.get_all("Gate Transaction", filters={"booking_ref": ["like", "TEST-%"], "status": ["in", ["Processing", "On Hold", "Cleared"]]},
                          fields=["name", "lane"])
    for r in rows:
        frappe.db.set_value("Gate Transaction", r.name, "status", "Rejected")
        frappe.db.set_value("Gate Lane", r.lane, {"status": "Open", "current_transaction": None})
    frappe.db.commit()
    return len(rows)


def run_checks(terminal=None):
    """Try to break the rules from steps 5 and 6 of the README. Returns one line per check."""
    cleanup_checks()
    terminal = terminal or frappe.db.get_value("Terminal", {}, "name")
    out = []

    def expect_refused(label, fn):
        try:
            fn()
            out.append(f"FAIL  {label}: it was allowed")
        except Exception as e:  # noqa: BLE001
            msg = (str(e) or e.__class__.__name__).splitlines()[0][:110]
            out.append(f"ok    {label}: refused ({msg})")
        finally:
            frappe.clear_messages()

    def expect_ok(label, fn):
        try:
            res = fn()
            out.append(f"ok    {label}" + (f": {res}" if res else ""))
        except Exception as e:  # noqa: BLE001
            out.append(f"FAIL  {label}: {str(e).splitlines()[0][:140] if str(e) else e.__class__.__name__}")
        finally:
            frappe.clear_messages()

    # --- yard: 20 ft and 40 ft footprints ---
    even = frappe.get_all("Yard Stack", filters={"terminal": terminal, "is_forty_anchor": 0, "is_blocked": 0}, pluck="name", limit=1)
    if even:
        expect_refused("45 ft container on an even (non-anchor) bay", lambda: yard.check_can_place(even[0], "45G1"))
    uneven = None
    for a in frappe.get_all("Yard Stack", filters={"terminal": terminal, "is_forty_anchor": 1}, fields=["name", "pair_stack", "tier_count"]):
        if frappe.db.get_value("Yard Stack", a.pair_stack, "tier_count") != a.tier_count:
            uneven = a.name
            break
    if uneven:
        expect_refused("45 ft container where the two slots are at different heights", lambda: yard.check_can_place(uneven, "45G1"))
    fits = None
    for a in frappe.get_all("Yard Stack", filters={"terminal": terminal, "is_forty_anchor": 1, "is_blocked": 0}, fields=["name", "pair_stack", "tier_count", "max_tier"]):
        if a.tier_count < a.max_tier and frappe.db.get_value("Yard Stack", a.pair_stack, "tier_count") == a.tier_count:
            fits = a.name
            break
    if fits:
        expect_ok("45 ft container on an anchor with an equal neighbour", lambda: yard.check_can_place(fits, "45G1")[0])
    expect_ok("20 ft container takes one slot", lambda: yard.check_can_place(even[0], "22G1")[0] if even else None)

    # --- gate: appointment is mandatory, override is audited ---
    clerk = _user("clerk@tos.test", "Gate Clerk")
    boss = _user("supervisor@tos.test", "Gate Supervisor")
    frappe.db.commit()
    truck = frappe.get_all("Truck", fields=["name", "carrier"], limit=1)[0]
    driver = frappe.get_all("Driver", filters={"carrier": truck.carrier}, pluck="name", limit=1)[0]
    lane = f"{terminal}-IN-1"
    tag = frappe.generate_hash(length=4).upper()
    no = _container_no(random.Random(tag), "TST")

    def new_visit(override=None):
        return frappe.get_doc({
            "doctype": "Gate Transaction", "lane": lane, "carrier": truck.carrier, "truck": truck.name, "driver": driver,
            "move_type": "Export Drop", "booking_ref": f"TEST-{tag}", "container_no": no, "container_type": "45G1",
            "shipping_line": "NWD", "override": override,
        }).insert()

    try:
        frappe.set_user(clerk)
        expect_refused("truck with no appointment and no override", new_visit)

        ov = frappe.get_doc({
            "doctype": "Appointment Override", "terminal": terminal, "override_type": "No Appointment",
            "reason_category": "Customs Request", "carrier": truck.carrier, "truck": truck.name,
            "reason": "Test: customs asked us to receive this truck although it has no booking.",
        }).insert()
        out.append(f"ok    clerk requested override {ov.name}")
        expect_refused("clerk approving their own override", lambda: ov.approve("looks fine"))
        expect_refused("override that is still pending", lambda: new_visit(ov.name))

        frappe.set_user(boss)
        ov = frappe.get_doc("Appointment Override", ov.name)
        expect_refused("approval without a note", lambda: ov.approve(""))
        expect_ok("supervisor approves the override", lambda: ov.approve("Confirmed with customs desk, ref " + tag))

        frappe.set_user(clerk)
        holder = {}

        def visit():
            gt = new_visit(ov.name)
            holder["gt"] = gt
            return gt.name
        expect_ok("truck admitted using the approved override", visit)
        gt = holder.get("gt")
        if gt:
            def run_through():
                n = 0
                while gt.status == "Processing" and n < 10:
                    gt.advance()
                    n += 1
                gt.complete()
                return f"{n} steps, status {gt.status}, turn {gt.turn_minutes} min"
            expect_ok("steps advanced and transaction completed", run_through)
            expect_ok("container now on the terminal", lambda: frappe.db.get_value("Container", no, "status"))
            expect_refused("using the same override a second time (lane is free again)", lambda: new_visit(ov.name))
            expect_refused("deleting an override", lambda: frappe.delete_doc("Appointment Override", ov.name, force=True))
    finally:
        frappe.set_user("Administrator")
        frappe.db.commit()

    for line in out:
        print(line)
    return {"passed": sum(1 for x in out if x.startswith("ok")), "failed": sum(1 for x in out if x.startswith("FAIL"))}
