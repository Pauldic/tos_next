# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from tos_next.realtime import publish
from tos_next.yard import log_movement

RELEASE_ROLES = {"Gate Supervisor", "Terminal Admin", "System Manager"}


class ContainerHold(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if self.is_new():
            self.status = "Active"
            self.placed_by = frappe.session.user
            self.placed_on = now_datetime()
            return
        if before.status == "Released":
            frappe.throw(_("A released hold cannot be changed. Place a new hold instead."))
        if before.status == "Active" and self.status == "Released":
            if not RELEASE_ROLES.intersection(frappe.get_roles()):
                frappe.throw(_("Only a Gate Supervisor or Terminal Admin can release a hold."))
            self.released_by = frappe.session.user
            self.released_on = now_datetime()

    def after_insert(self):
        self.refresh_container("Hold")

    def on_update(self):
        before = self.get_doc_before_save()
        if before and before.status == "Active" and self.status == "Released":
            self.refresh_container("Release")

    def on_trash(self):
        frappe.throw(_("Holds are part of the audit trail and cannot be deleted. Release the hold instead."))

    def refresh_container(self, movement_type):
        active = frappe.db.count("Container Hold", {"container": self.container, "status": "Active"})
        frappe.db.set_value("Container", self.container, "is_on_hold", 1 if active else 0, update_modified=False)
        c = frappe.get_doc("Container", self.container)
        log_movement(c, movement_type, c.yard_stack, c.tier, c.yard_stack, c.tier,
                     "Container Hold", self.name)
        publish("hold_changed", {"container": c.name, "is_on_hold": bool(active), "hold": self.name}, c.terminal)
