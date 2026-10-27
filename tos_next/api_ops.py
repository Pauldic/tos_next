"""Equipment operator endpoints for the mobile 'My moves' screen.
Everything runs under the caller's own permissions. Move Order itself enforces that an operator can only
start and complete orders assigned to them.
Call as /api/method/tos_next.api_ops.<name>.
"""
import frappe
from frappe import _

from tos_next.api import _terminal

OPEN = ("Assigned", "In Progress")
ORDER_FIELDS = ["name", "container", "length_ft", "move_type", "status", "priority", "from_stack", "from_tier",
                "to_stack", "to_tier", "equipment", "started_at", "completed_at", "notes"]
EQ_FIELDS = ["name", "equipment_type", "status", "current_operator", "max_lift_tier", "handles_forty"]


@frappe.whitelist()
def ops_board(terminal=None):
    terminal = _terminal(terminal)
    me = frappe.session.user
    mine = frappe.get_list("Equipment", filters={"terminal": terminal, "current_operator": me}, fields=EQ_FIELDS, limit_page_length=10)
    free = frappe.get_list("Equipment", filters={"terminal": terminal, "current_operator": ["is", "not set"]}, fields=EQ_FIELDS,
                           order_by="equipment_type asc, name asc", limit_page_length=50)
    orders = frappe.get_list("Move Order", filters={"terminal": terminal, "assigned_to": me, "status": ["in", OPEN]}, fields=ORDER_FIELDS,
                             order_by="status desc, priority desc, creation asc", limit_page_length=50)
    recent = frappe.get_list("Move Order", filters={"terminal": terminal, "assigned_to": me, "status": "Completed"}, fields=ORDER_FIELDS,
                             order_by="completed_at desc", limit_page_length=3)
    return {"user": me, "equipment": mine, "available": free, "orders": orders, "recent": recent}


@frappe.whitelist()
def move_action(order, action):
    if action not in ("start", "complete"):
        frappe.throw(_("Unknown action."))
    doc = frappe.get_doc("Move Order", order)
    doc.check_permission("write")
    getattr(doc, action)()
    return frappe.db.get_value("Move Order", order, ORDER_FIELDS, as_dict=True)


@frappe.whitelist()
def sign_on(equipment):
    me = frappe.session.user
    eq = frappe.get_doc("Equipment", equipment)
    eq.check_permission("write")
    if eq.status in ("Maintenance", "Offline"):
        frappe.throw(_("{0} is {1}.").format(eq.name, eq.status))
    if eq.current_operator and eq.current_operator != me:
        frappe.throw(_("{0} is being used by {1}.").format(eq.name, eq.current_operator))
    other = frappe.db.get_value("Equipment", {"current_operator": me, "name": ["!=", eq.name]}, "name")
    if other:
        frappe.throw(_("You are signed on to {0}. Sign off first.").format(other))
    eq.current_operator = me
    eq.save()
    return {"equipment": eq.name}


@frappe.whitelist()
def sign_off(equipment):
    eq = frappe.get_doc("Equipment", equipment)
    eq.check_permission("write")
    if eq.current_operator != frappe.session.user:
        frappe.throw(_("You are not signed on to {0}.").format(eq.name))
    if frappe.db.exists("Move Order", {"equipment": eq.name, "status": ["in", OPEN]}):
        frappe.throw(_("{0} still has open orders. Finish them, or ask a planner to reassign them.").format(eq.name))
    eq.current_operator = None
    eq.save()
    return {"equipment": eq.name}
