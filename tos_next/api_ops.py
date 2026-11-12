"""Equipment operator endpoints for the mobile 'My moves' screen.
Everything runs under the caller's own permissions. Move Order itself enforces that an operator can only
start and complete orders assigned to them.
Call as /api/method/tos_next.api_ops.<name>.
"""
import frappe
from frappe import _

from tos_next import settings as tos_settings
from tos_next import yard
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
    # Queued jobs nobody has taken yet, that the machine I am signed on to can actually do
    open_jobs = []
    if mine and tos_settings.company("operators_can_take_jobs"):
        eq = mine[0]
        queued = frappe.get_list("Move Order", filters={"terminal": terminal, "status": "Queued"}, fields=ORDER_FIELDS,
                                 order_by="priority desc, creation asc", limit_page_length=30)
        for o in queued:
            if not eq.handles_forty and (frappe.db.get_value("Container", o.container, "slot_span") or 1) == 2:
                continue
            open_jobs.append(o)
    return {"user": me, "equipment": mine, "available": free, "orders": orders, "recent": recent, "open_jobs": open_jobs}


@frappe.whitelist()
def move_action(order, action):
    if action not in ("start", "complete"):
        frappe.throw(_("Unknown action."))
    doc = frappe.get_doc("Move Order", order)
    doc.check_permission("write")
    getattr(doc, action)()
    return frappe.db.get_value("Move Order", order, ORDER_FIELDS, as_dict=True)


@frappe.whitelist()
def claim_order(order):
    """An operator takes a queued job for the machine they are signed on to. Same rules as a planner's assignment."""
    if not tos_settings.company("operators_can_take_jobs"):
        frappe.throw(_("Taking jobs is switched off. A planner assigns the orders."))
    me = frappe.session.user
    doc = frappe.get_doc("Move Order", order)
    doc.check_permission("write")
    eq_name = frappe.db.get_value("Equipment", {"current_operator": me, "terminal": doc.terminal}, "name")
    if not eq_name:
        frappe.throw(_("Sign on to a machine first."))
    eq = frappe.get_doc("Equipment", eq_name)
    if doc.status != "Queued":
        frappe.throw(_("Order {0} is {1}. Someone else may have taken it.").format(doc.name, doc.status))
    if eq.status not in ("Available", "Working"):
        frappe.throw(_("Equipment {0} is {1}.").format(eq.name, eq.status))
    c = frappe.get_cached_doc("Container", doc.container)
    if c.slot_span == 2 and not eq.handles_forty:
        frappe.throw(_("{0} cannot handle 40 ft containers.").format(eq.name))
    if doc.to_stack:
        _names, tier = yard.check_can_place(doc.to_stack, c.container_type)
        if tier > eq.max_lift_tier:
            frappe.throw(_("{0} cannot reach tier {1}.").format(eq.name, tier))
    doc.equipment = eq.name
    doc.assigned_to = me
    doc.status = "Assigned"
    doc.save()
    doc.add_comment("Info", _("Taken by {0} on {1}").format(me, eq.name))
    return frappe.db.get_value("Move Order", doc.name, ORDER_FIELDS, as_dict=True)


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
