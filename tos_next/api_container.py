"""Container endpoints for the Vue app. Call as /api/method/tos_next.api_container.<name>. Every one respects the caller's permissions."""
import frappe
from frappe import _
from frappe.utils import date_diff, now_datetime

from tos_next import inventory


@frappe.whitelist()
def container_list(terminal=None, filters=None, search=None, limit=100, start=0):
    frappe.has_permission("Container", "read", throw=True)
    f = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    if terminal:
        f["terminal"] = terminal
    return inventory.rows(f, search, limit, start)


@frappe.whitelist()
def container_detail(container):
    doc = frappe.get_doc("Container", container)
    doc.check_permission("read")
    d = doc.as_dict()
    d["dwell_days"] = date_diff(now_datetime(), doc.arrived_on) if doc.arrived_on and doc.status == "On Terminal" else None
    d["can_edit"] = bool(doc.has_permission("write"))
    return d


@frappe.whitelist()
def container_history(container):
    return inventory.history(container)
