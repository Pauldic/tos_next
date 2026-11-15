"""Gate transactions are now records (Transaction Type) with the customer's own names: Receive = Gate In, Deliver = Gate Out.
1. Adds the six standard types when there are none.
2. Renames the old move types stored on appointments, jobs and gate visits.
3. Gives every terminal a profile and switches, and every container the marine flag its terminal has.
Safe to run twice."""
import frappe

TYPES = [
    # name, gate, cargo, category on arrival, from/to, container named, booking, order, description
    ("Receive Import", "In", "Loaded", "Import", "Marine Terminal", 0, 0, 10, "A loaded import container coming from the marine terminal, for storage."),
    ("Deliver Import", "Out", "Loaded", "", "Customer", 1, 0, 20, "A loaded import container going from the terminal to the customer."),
    ("Receive Empty", "In", "Empty", "Storage", "Customer", 0, 0, 30, "An empty container coming back from a customer or the community, for storage."),
    ("Deliver Empty", "Out", "Empty", "", "Customer or Marine Terminal", 0, 0, 40, "An empty container going to a customer or to the marine terminal, for loading or export."),
    ("Receive Export", "In", "Loaded", "Export", "Customer", 0, 1, 50, "A loaded container coming from the customer, for export."),
    ("Deliver Export", "Out", "Loaded", "", "Marine Terminal", 1, 0, 60, "A loaded export container going from the terminal to the marine terminal."),
]
RENAMES = {"Export Drop": "Receive Export", "Empty Return": "Receive Empty", "Import Pickup": "Deliver Import", "Empty Pickup": "Deliver Empty"}


def execute():
    if not frappe.db.count("Transaction Type"):
        for name, gate, cargo, cat, party, needs_c, needs_b, order, text in TYPES:
            frappe.get_doc({"doctype": "Transaction Type", "transaction_name": name, "direction": gate, "cargo": cargo, "category": cat or None,
                            "counterparty": party, "requires_container": needs_c, "requires_booking": needs_b, "sort_order": order,
                            "description": text, "is_active": 1}).insert(ignore_permissions=True)

    for table, field in (("Appointment", "move_type"), ("Appointment Line", "move_type"), ("Gate Transaction", "move_type")):
        for old, new in RENAMES.items():
            frappe.db.sql(f"update `tab{table}` set `{field}` = %s where `{field}` = %s", (new, old))
    frappe.db.sql("update `tabAppointment` set visit_type = case direction when 'In' then 'Receive' when 'Out' then 'Deliver' else 'Receive and Deliver' end")

    frappe.db.sql("update `tabTerminal` set terminal_profile = 'Both' where terminal_profile is null or terminal_profile = ''")
    frappe.db.sql("update `tabTerminal` set has_marine_side = 1 where has_marine_side is null")
    frappe.db.sql("update `tabTerminal` set has_bonded_side = 1 where has_bonded_side is null")
    if frappe.db.has_column("Container", "terminal_has_marine"):
        frappe.db.sql("update `tabContainer` c join `tabTerminal` t on t.name = c.terminal set c.terminal_has_marine = t.has_marine_side")
