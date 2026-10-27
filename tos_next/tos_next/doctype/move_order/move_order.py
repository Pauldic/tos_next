# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from tos_next import yard
from tos_next.realtime import publish

NEEDS_TARGET = {"Yard Shift", "Reshuffle", "From Gate In", "From Vessel"}
OPEN = ("Queued", "Assigned", "In Progress")
PLANNER_ROLES = {"Yard Planner", "Terminal Admin", "System Manager"}


class MoveOrder(Document):
    def validate(self):
        if self.is_new():
            self.requested_by = frappe.session.user
            self.check_creatable()

    # ---------- creation rules ----------
    def check_creatable(self):
        c = frappe.get_doc("Container", self.container)
        self.terminal = c.terminal
        self.from_stack, self.from_tier = c.yard_stack, c.tier

        if c.status != "On Terminal":
            frappe.throw(_("{0} is not on the terminal.").format(c.name))
        if c.is_on_hold:
            frappe.throw(_("{0} is on hold and cannot be moved.").format(c.name))
        other = frappe.db.exists("Move Order", {"container": c.name, "status": ["in", OPEN], "name": ["!=", self.name]})
        if other:
            frappe.throw(_("{0} already has an open order: {1}.").format(c.name, other))

        if self.move_type == "From Gate In":
            if c.yard_stack:
                frappe.throw(_("{0} is already in the yard.").format(c.name))
        elif not c.yard_stack:
            frappe.throw(_("{0} is not in the yard.").format(c.name))
        else:
            blockers = [
                b for b in yard.get_blockers(c)
                if not frappe.db.exists("Move Order", {"container": b, "move_type": "Reshuffle", "status": ["in", OPEN]})
            ]
            if blockers:
                frappe.throw(_("{0} has {1} container(s) above it: {2}. Create reshuffle orders for them first.")
                             .format(c.name, len(blockers), ", ".join(blockers)))

        if self.move_type in NEEDS_TARGET:
            if not self.to_stack:
                frappe.throw(_("Choose a destination stack."))
            if self.to_stack in (c.yard_stack, c.partner_stack):
                frappe.throw(_("The destination is the container's current stack."))
            yard.check_can_place(self.to_stack, c.container_type)  # dry run, no lock
        else:
            self.to_stack = None

    # ---------- workflow ----------
    def _guard_status(self, *allowed):
        if self.status not in allowed:
            frappe.throw(_("Order {0} is {1}. Allowed: {2}.").format(self.name, self.status, ", ".join(allowed)))

    def _guard_operator(self):
        if PLANNER_ROLES.intersection(frappe.get_roles()):
            return
        if self.assigned_to != frappe.session.user:
            frappe.throw(_("This order is assigned to {0}.").format(self.assigned_to or _("nobody")))

    @frappe.whitelist()
    def assign(self, equipment, assigned_to=None):
        frappe.only_for(list(PLANNER_ROLES))
        self._guard_status("Queued", "Assigned")
        eq = frappe.get_doc("Equipment", equipment)
        if eq.status not in ("Available", "Working"):
            frappe.throw(_("Equipment {0} is {1}.").format(eq.name, eq.status))
        c = frappe.get_cached_doc("Container", self.container)
        if c.slot_span == 2 and not eq.handles_forty:
            frappe.throw(_("{0} cannot handle 40 ft containers.").format(eq.name))
        if self.to_stack:
            names, tier = yard.check_can_place(self.to_stack, c.container_type)
            if tier > eq.max_lift_tier:
                frappe.throw(_("{0} cannot reach tier {1}.").format(eq.name, tier))
        self.equipment = equipment
        self.assigned_to = assigned_to or eq.current_operator
        self.status = "Assigned"
        self.save()

    @frappe.whitelist()
    def start(self):
        self._guard_status("Assigned")
        self._guard_operator()
        self.status = "In Progress"
        self.started_at = now_datetime()
        self.save()
        frappe.db.set_value("Equipment", self.equipment, "status", "Working")
        publish("yard_move_started", {
            "order": self.name, "container": self.container, "from": self.from_stack,
            "to": self.to_stack, "equipment": self.equipment,
        }, self.terminal)

    @frappe.whitelist()
    def complete(self):
        self._guard_status("In Progress")
        self._guard_operator()
        c = yard.move_container(
            self.container, self.to_stack if self.move_type in NEEDS_TARGET else None,
            "Yard Move" if self.move_type != "To Vessel" else "Vessel Load",
            "Move Order", self.name, self.equipment)
        self.to_tier = c.tier
        self.status = "Completed"
        self.completed_at = now_datetime()
        self.save()
        if self.equipment:
            frappe.db.set_value("Equipment", self.equipment, "status", "Available")
        publish("yard_move_done", {
            "order": self.name, "container": self.container, "stack": c.yard_stack,
            "partner_stack": c.partner_stack, "tier": c.tier, "from": self.from_stack,
        }, self.terminal)

    @frappe.whitelist()
    def cancel_order(self, reason):
        if not reason:
            frappe.throw(_("A reason is required."))
        if self.status == "In Progress" and not {"Terminal Admin", "Gate Supervisor", "System Manager"}.intersection(frappe.get_roles()):
            frappe.throw(_("Only a supervisor can cancel an order that has started."))
        self._guard_status("Queued", "Assigned", "In Progress")
        if self.equipment and self.status == "In Progress":
            frappe.db.set_value("Equipment", self.equipment, "status", "Available")
        self.status = "Cancelled"
        self.cancel_reason = reason
        self.save()


@frappe.whitelist()
def suggest_target(container):
    """Used by the Create move order button."""
    frappe.has_permission("Move Order", "create", throw=True)
    return yard.suggest_target(container)


@frappe.whitelist()
def create_reshuffle_orders(container):
    """Create orders to clear every container above `container`, top first."""
    frappe.has_permission("Move Order", "create", throw=True)
    c = frappe.get_doc("Container", container)
    created = []
    for b in yard.get_blockers(c):
        target = yard.suggest_target(b)
        if not target:
            frappe.throw(_("No free stack found for {0}.").format(b))
        doc = frappe.get_doc({
            "doctype": "Move Order", "container": b, "move_type": "Reshuffle",
            "to_stack": target, "priority": "High",
            "notes": _("Clears the way for {0}").format(container),
        })
        # Blockers above each other are cleared top first, so each one is free when its turn comes.
        doc.insert()
        created.append(doc.name)
    return created
