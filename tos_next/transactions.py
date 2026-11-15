"""Transaction types (Receive Import, Deliver Empty and so on) are records, not code. This module reads them.
Receive is a Gate In and Deliver is a Gate Out; the rules each type carries are checked here, so a new terminal can add or
change its own list in the Desk without a release."""
import frappe
from frappe import _

LOADED = ("FCL", "LCL")


def get(name):
    if not name or not frappe.db.exists("Transaction Type", name):
        frappe.throw(_("{0} is not a transaction type. Choose one from the list.").format(name or _("(empty)")))
    return frappe.get_cached_doc("Transaction Type", name)


def is_in(name) -> bool:
    return get(name).direction == "In"


def direction(name) -> str:
    return get(name).direction


FIELDS = ["name", "direction", "cargo", "category", "counterparty", "requires_container", "requires_booking", "description", "sort_order"]


def offered(terminal=None):
    """The transactions a terminal offers: its own list when it has one, otherwise every active type."""
    rows = frappe.get_all("Transaction Type", filters={"is_active": 1}, fields=FIELDS, order_by="sort_order asc, name asc", limit_page_length=0)
    if terminal and frappe.db.exists("Terminal", terminal):
        picked = frappe.get_all("Terminal Transaction Type", filters={"parent": terminal, "parenttype": "Terminal"}, fields=["transaction_type", "is_enabled"], limit_page_length=0)
        if picked:
            on = {p.transaction_type for p in picked if p.is_enabled}
            rows = [r for r in rows if r["name"] in on]
    return rows


def assert_offered(name, terminal):
    if terminal and name not in {r["name"] for r in offered(terminal)}:
        frappe.throw(_("{0} is not offered at terminal {1}.").format(name, terminal))


def check_container_fits(tt, container, where=""):
    """The container (a Container document) must be in the right state for this transaction."""
    prefix = f"{where}: " if where else ""
    if tt.direction == "Out":
        if container.status != "On Terminal":
            frappe.throw(_("{0}{1} is not on the terminal.").format(prefix, container.name))
        if container.is_on_hold:
            frappe.throw(_("{0}{1} is on hold and cannot leave.").format(prefix, container.name))
        loaded = container.full_empty in LOADED
        if tt.cargo == "Loaded" and not loaded:
            frappe.throw(_("{0}{1} is empty, but {2} is for loaded containers.").format(prefix, container.name, tt.name))
        if tt.cargo == "Empty" and loaded:
            frappe.throw(_("{0}{1} is loaded, but {2} is for empty containers.").format(prefix, container.name, tt.name))
    elif container.status == "On Terminal":
        frappe.throw(_("{0}{1} is already on the terminal, so it cannot be received again.").format(prefix, container.name))


def arrival_state(tt, container=None):
    """Category and F/E a container gets when it is received under this transaction."""
    if tt.cargo == "Empty":
        full_empty = "MT"
    else:
        full_empty = container.full_empty if container is not None and container.full_empty in LOADED else "FCL"
    category = tt.category or (container.category if container is not None else None) or "Storage"
    return category, full_empty
