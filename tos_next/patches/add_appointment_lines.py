"""Appointments can now carry several jobs, and trucks have a chassis type.
1. Adds the chassis types a terminal normally needs (only when there are none yet; edit or add more in the Desk).
2. Gives every truck a chassis type from its old 'Can Carry' value.
3. Turns the single job of each existing appointment into one line, and fills in the visit type.
Safe to run twice."""
import frappe

CHASSIS = [
    # name, longest single container, most containers, total length (ft)
    ("20 ft", 20, 1, 20, "One 20 ft container."),
    ("40 ft", 40, 1, 40, "One 40 ft container, or one 20 ft."),
    ("45 ft", 45, 1, 45, "One container up to 45 ft."),
    ("Combo 40 ft or 2 x 20 ft", 40, 2, 40, "One 40 ft, one 20 ft, or two 20 ft."),
]
OLD_TO_NEW = {"20 ft only": "20 ft", "Up to 40 ft": "40 ft", "Up to 45 ft": "45 ft"}
IN_MOVES = ("Export Drop", "Empty Return")


def execute():
    if not frappe.db.count("Chassis Type"):
        for name, longest, most, total, text in CHASSIS:
            frappe.get_doc({"doctype": "Chassis Type", "chassis_name": name, "max_container_length_ft": longest, "max_containers": most,
                            "max_total_length_ft": total, "description": text}).insert(ignore_permissions=True)

    old_column = frappe.db.has_column("Truck", "max_container_length")
    default = "40 ft" if frappe.db.exists("Chassis Type", "40 ft") else frappe.db.get_value("Chassis Type", {}, "name")
    for t in frappe.get_all("Truck", fields=["name", "chassis_type"] + (["max_container_length"] if old_column else [])):
        if t.chassis_type:
            continue
        pick = OLD_TO_NEW.get(t.get("max_container_length"), default)
        if not frappe.db.exists("Chassis Type", pick):
            pick = default
        frappe.db.set_value("Truck", t.name, "chassis_type", pick, update_modified=False)

    for a in frappe.get_all("Appointment", fields=["name", "move_type", "container", "booking_ref", "status", "completed_at", "direction"]):
        if not frappe.db.exists("Appointment Line", {"parent": a.name, "parenttype": "Appointment"}) and a.move_type:
            length = frappe.db.get_value("Container", a.container, "length_ft") if a.container else None
            if not length:
                truck = frappe.db.get_value("Appointment", a.name, "truck")
                ctype = frappe.db.get_value("Truck", truck, "chassis_type") if truck else None
                length = frappe.db.get_value("Chassis Type", ctype, "max_container_length_ft") if ctype else 40
            row = frappe.get_doc({
                "doctype": "Appointment Line", "parent": a.name, "parenttype": "Appointment", "parentfield": "lines", "idx": 1,
                "move_type": a.move_type, "container": a.container, "booking_ref": a.booking_ref, "container_length": length,
                "status": "Done" if a.status == "Completed" else "Cancelled" if a.status in ("Cancelled", "No-show") else "Pending",
                "done_on": a.completed_at if a.status == "Completed" else None,
            })
            row.name = frappe.generate_hash(length=10)
            row.db_insert()
        direction = "In" if a.move_type in IN_MOVES else "Out"
        frappe.db.set_value("Appointment", a.name, "visit_type", "Drop Off" if direction == "In" else "Pick Up", update_modified=False)
