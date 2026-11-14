"""The container event log. Anything worth remembering about a container that is not already a move, a hold or a gate
transaction is written here, and the Container page merges all of them into one history."""
import frappe


def log(container, event_type, summary, terminal=None, source_doctype=None, source_name=None):
    if not summary:
        return None
    return frappe.get_doc({
        "doctype": "Container Event", "container": container, "terminal": terminal or frappe.db.get_value("Container", container, "terminal"),
        "event_type": event_type, "event_time": frappe.utils.now_datetime(), "event_by": frappe.session.user, "summary": summary,
        "source_doctype": source_doctype, "source_name": source_name,
    }).insert(ignore_permissions=True)
