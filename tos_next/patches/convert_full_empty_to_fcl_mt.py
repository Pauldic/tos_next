"""F/E now uses the terminal's own words: FCL (full), LCL (part load) and MT (empty). Converts containers that already have
Full or Empty, and fills in transit state and the position line again for any container that is missing them. Safe to run twice."""
import frappe

from tos_next.tos_next.doctype.container.container import position_text, transit_for


def execute():
    for old, new in (("Full", "FCL"), ("Empty", "MT")):
        frappe.db.sql("update `tabContainer` set full_empty=%s where full_empty=%s", (new, old))
    for c in frappe.get_all("Container", fields=["name", "status", "yard_stack", "partner_stack", "tier"]):
        frappe.db.set_value("Container", c.name, {
            "transit_state": transit_for(c.status, c.yard_stack), "position": position_text(c.yard_stack, c.partner_stack, c.tier),
        }, update_modified=False)
