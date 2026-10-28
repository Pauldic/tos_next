"""Go-live audit. Read-only except for one self-contained test that rolls itself back.

    bench --site <site> execute tos_next.setup.audit.run

Every line is PASS, WARN or FAIL. Fix every FAIL before real users sign in.
Run it on staging first: the boundary test creates and then rolls back two throwaway carriers named 'AUDIT A/B ...'.
"""
import uuid

import frappe
from frappe.utils import add_days, nowdate

ROLES = ["Terminal Admin", "Yard Planner", "Equipment Operator", "Gate Clerk", "Gate Supervisor", "Appointment Planner", "Carrier Portal User"]
STAFF = {"System Manager", "Terminal Admin", "Yard Planner", "Equipment Operator", "Gate Clerk", "Gate Supervisor", "Appointment Planner"}
APPEND_ONLY = ["Container Movement", "Appointment Override", "Gate Transaction"]


class Report:
    def __init__(self):
        self.fail = 0

    def add(self, ok, label, detail="", warn=False):
        tag = "PASS" if ok else ("WARN" if warn else "FAIL")
        if not ok and not warn:
            self.fail += 1
        print(f"{tag:4}  {label}" + (f"  ({detail})" if detail else ""))


def _perm_rows(parent=None, role=None):
    flt = {}
    if parent:
        flt["parent"] = parent
    if role:
        flt["role"] = role
    rows = []
    for dt in ("DocPerm", "Custom DocPerm"):
        rows += frappe.get_all(dt, filters=flt, fields=["parent", "role", "read", "write", "create", "delete", "submit", "cancel"])
    return rows


def run():
    r = Report()

    # --- roles ---
    missing = [x for x in ROLES if not frappe.db.exists("Role", x)]
    r.add(not missing, "All TOS roles exist", ", ".join(missing))

    # --- carrier role is read-only everywhere ---
    bad = sorted({p.parent for p in _perm_rows(role="Carrier Portal User") if p.write or p.create or p.delete or p.submit or p.cancel})
    r.add(not bad, "Carrier Portal User cannot create, change or delete anything directly",
          (", ".join(bad) + " -> run tools/harden_permissions.py, then migrate") if bad else "")

    # --- audit trails cannot be deleted ---
    for dt in APPEND_ONLY:
        deleters = sorted({p.role for p in _perm_rows(parent=dt) if p.delete})
        r.add(not deleters, f"{dt} cannot be deleted", ", ".join(deleters))
    writers = sorted({p.role for p in _perm_rows(parent="Container Movement") if p.write and p.role != "System Manager"})
    r.add(not writers, "Container Movement is append-only for staff", ", ".join(writers), warn=True)

    # --- carrier logins ---
    portal_users = frappe.get_all("Has Role", filters={"role": "Carrier Portal User", "parenttype": "User"}, pluck="parent")
    portal_users = [u for u in portal_users if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")]
    unlinked = [u for u in portal_users if not frappe.db.exists("User Permission", {"user": u, "allow": "Carrier"})]
    r.add(not unlinked, f"All {len(portal_users)} carrier login(s) are tied to a carrier", ", ".join(unlinked))
    both = [u for u in portal_users if STAFF.intersection(frappe.get_roles(u))]
    r.add(not both, "No carrier login also holds a staff role", ", ".join(both), warn=True)

    # --- site setup ---
    try:
        from frappe.utils.scheduler import is_scheduler_disabled
        r.add(not is_scheduler_disabled(), "Scheduler is enabled (late and no-show marking, override expiry)")
    except Exception:
        r.add(False, "Scheduler state could not be read", warn=True)
    r.add(not frappe.conf.get("developer_mode"), "Developer mode is off", warn=True)
    r.add(True, "Realtime port", str(frappe.conf.get("socketio_port") or "default 9000"))
    term = frappe.get_all("Terminal", filters={"is_active": 1}, pluck="name")
    r.add(bool(term), "An active terminal exists", ", ".join(term))
    if term:
        t = term[0]
        r.add(bool(frappe.db.count("Yard Stack", {"terminal": t})), "Yard stacks exist (Yard Block -> Generate Stacks)")
        lanes_in = frappe.db.count("Gate Lane", {"terminal": t, "direction": "In"})
        lanes_out = frappe.db.count("Gate Lane", {"terminal": t, "direction": "Out"})
        r.add(bool(lanes_in and lanes_out), "Gate In and Gate Out lanes exist", f"{lanes_in} in, {lanes_out} out")
        r.add(bool(frappe.db.count("Container Type")), "Container types exist")
        r.add(bool(frappe.db.count("Equipment", {"terminal": t})), "Equipment exists", warn=True)
        ahead = frappe.db.count("Slot Capacity", {"terminal": t, "slot_date": ["between", [nowdate(), add_days(nowdate(), 7)]]})
        r.add(ahead > 0, "Appointment slots exist for the next 7 days", f"{ahead} slots; Slot Template -> Generate Slots")
    demo = frappe.db.count("Container", {"name": ["like", "DEMO%"]})
    r.add(not demo, "No demo containers on this site", f"{demo} found", warn=True)

    # --- the carrier boundary, proven by trying to break it ---
    boundary_test(r)

    print("\n" + ("ALL CLEAR" if not r.fail else f"{r.fail} FAILURE(S): fix before go-live"))
    return "ok" if not r.fail else "failures"


def boundary_test(r):
    """Two temporary carriers with a login each. Carrier B tries to reach carrier A's data and to clear a block.
    Everything is rolled back afterwards."""
    from tos_next import api_portal as p

    tag = uuid.uuid4().hex[:6]
    frappe.db.savepoint("tos_audit")
    try:
        frappe.set_user("Administrator")
        made = {}
        for k in ("a", "b"):
            c = frappe.get_doc({"doctype": "Carrier", "carrier_name": f"AUDIT {k.upper()} {tag}"}).insert(ignore_permissions=True)
            email = f"audit-{k}-{tag}@example.test"
            frappe.get_doc({
                "doctype": "User", "email": email, "first_name": f"Audit{k}", "user_type": "Website User", "send_welcome_email": 0,
                "new_password": frappe.generate_hash(length=16), "roles": [{"role": "Carrier Portal User"}],
            }).insert(ignore_permissions=True)
            frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Carrier", "for_value": c.name, "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)
            truck = frappe.get_doc({"doctype": "Truck", "plate_no": f"AUD{k.upper()}{tag}".upper(), "carrier": c.name}).insert(ignore_permissions=True)
            driver = frappe.get_doc({"doctype": "Driver", "full_name": f"Audit Driver {k}", "carrier": c.name, "licence_no": f"LIC{k}{tag}",
                                     "licence_expiry": add_days(nowdate(), 400)}).insert(ignore_permissions=True)
            made[k] = {"carrier": c.name, "user": email, "truck": truck.name, "driver": driver.name}
        frappe.db.set_value("Truck", made["b"]["truck"], {"is_blocked": 1, "block_reason": "audit"})

        frappe.set_user(made["b"]["user"])

        def denied(fn):
            try:
                fn()
            except (frappe.PermissionError, frappe.ValidationError):
                return True  # any other error type is a bug in the test and is reported below
            return False

        r.add(denied(lambda: p.portal_save_truck(carrier=made["a"]["carrier"], plate_no=f"HACK{tag}")), "Carrier B cannot add a truck to carrier A")
        r.add(denied(lambda: p.portal_save_driver(carrier=made["a"]["carrier"], full_name="X", licence_no=f"HX{tag}", licence_expiry=add_days(nowdate(), 100))),
              "Carrier B cannot add a driver to carrier A")
        r.add(denied(lambda: p.portal_save_truck(carrier=made["b"]["carrier"], name=made["a"]["truck"])), "Carrier B cannot edit carrier A's truck")
        r.add(denied(lambda: p.portal_book(slot="none", carrier=made["a"]["carrier"], truck=made["a"]["truck"], driver=made["a"]["driver"], move_type="Export Drop")),
              "Carrier B cannot book for carrier A")
        fleet = p.portal_fleet()
        r.add(len(fleet["trucks"]) == 1 and all(x["carrier"] == made["b"]["carrier"] for x in fleet["trucks"] + fleet["drivers"]), "Carrier B's fleet list shows only carrier B")

        def unblock():
            doc = frappe.get_doc("Truck", made["b"]["truck"])
            doc.is_blocked = 0
            doc.save()  # what a direct REST call does, with normal permission checks

        r.add(denied(unblock), "Carrier B cannot clear a terminal block on its own truck (direct save)")
        r.add(denied(lambda: p.portal_save_truck(carrier=made["b"]["carrier"], name=made["b"]["truck"])), "Carrier B cannot edit a blocked truck through the portal either")
        r.add(not frappe.has_permission("Truck", "read", doc=made["a"]["truck"]), "Carrier B cannot even read carrier A's truck (User Permission)")
    except Exception as e:  # the test itself broke: say so rather than pretend
        r.add(False, "Carrier boundary test could not complete", f"{type(e).__name__}: {e}")
    finally:
        frappe.set_user("Administrator")
        try:
            frappe.db.rollback(save_point="tos_audit")
        except Exception:
            frappe.db.rollback()
