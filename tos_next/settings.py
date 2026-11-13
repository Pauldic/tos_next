"""Reads the company-wide settings page (TOS Settings) and the per-terminal overrides on the Terminal form.

Every value and its default lives in the DocType, not here. A terminal value wins when it is filled in;
a 0 (or 'Use company setting') means 'inherit the company value'.
"""
import frappe

# company setting -> the Terminal field that overrides it
TERMINAL_OVERRIDES = {
    "early_arrival_minutes": "early_arrival_minutes",
    "late_arrival_minutes": "late_arrival_minutes",
    "late_grace_minutes": "late_grace_minutes",
    "override_valid_hours": "override_valid_hours",
}


def company(key):
    """The company-wide value. If the page was saved before a field existed, the default set on the DocType field is used."""
    value = frappe.get_cached_doc("TOS Settings").get(key)
    if value is None:
        field = frappe.get_meta("TOS Settings").get_field(key)
        value = field.default if field else None
    return value


def get(key, terminal=None):
    """The company value, replaced by the terminal's own value when that is filled in."""
    if terminal and key in TERMINAL_OVERRIDES:
        value = frappe.db.get_value("Terminal", terminal, TERMINAL_OVERRIDES[key])
        if value:
            return value
    return company(key)


def gate_window(terminal=None):
    """(minutes a truck may arrive before its slot starts, minutes it may arrive after the slot ends)"""
    return int(get("early_arrival_minutes", terminal)), int(get("late_arrival_minutes", terminal))


def second_approver_required(terminal=None):
    """The stricter setting wins: company says so, or the terminal says so."""
    if company("override_needs_second_approver"):
        return True
    return bool(terminal and frappe.db.get_value("Terminal", terminal, "override_needs_second_approver"))


def auto_create_order(terminal=None):
    choice = frappe.db.get_value("Terminal", terminal, "auto_create_gate_in_order") if terminal else None
    if choice == "Yes":
        return True
    if choice == "No":
        return False
    return bool(company("auto_create_gate_in_order"))
