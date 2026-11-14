"""Moves containers over to the new model: the old Cargo field becomes Category and F/E, and the transit state and
position line are filled in for containers that already exist. Safe to run twice."""
import frappe

from tos_next.tos_next.doctype.container.container import position_text, transit_for

# old Cargo value -> (Category, F/E). Reefer is now known from the container type, so a Reefer becomes an ordinary full import.
CARGO = {"Import": ("Import", "FCL"), "Export": ("Export", "FCL"), "Empty": ("Storage", "MT"),
         "Reefer": ("Import", "FCL"), "Transshipment": ("Transshipment", "FCL")}


def execute():
    if frappe.db.has_column("Container", "cargo_status"):
        for old, (category, full_empty) in CARGO.items():
            frappe.db.sql(
                "update `tabContainer` set category=%s, full_empty=%s where cargo_status=%s and (category is null or category='' or category='Import') and (full_empty is null or full_empty='' or full_empty in ('Full','FCL'))",
                (category, full_empty, old),
            )
    for c in frappe.get_all("Container", fields=["name", "status", "yard_stack", "partner_stack", "tier", "container_type"]):
        is_reefer = frappe.db.get_value("Container Type", c.container_type, "is_reefer") if c.container_type else 0
        frappe.db.set_value("Container", c.name, {
            "transit_state": transit_for(c.status, c.yard_stack), "position": position_text(c.yard_stack, c.partner_stack, c.tier), "is_reefer": is_reefer or 0,
        }, update_modified=False)
