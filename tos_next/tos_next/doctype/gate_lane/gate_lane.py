# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from tos_next.realtime import publish


class GateLane(Document):
    def validate(self):
        self.lane_code = (self.lane_code or "").strip().upper()
        before = self.get_doc_before_save()
        if before and before.status != self.status:
            if self.status == "Open" and self.current_transaction:
                frappe.throw(_("A truck is still in this lane. Complete or reject its transaction first."))
            if self.status in ("Closed", "Fault") and self.current_transaction:
                frappe.throw(_("A truck is in this lane. Finish or reject it before closing the lane."))

    def on_update(self):
        publish("gate_status", {"lane": self.name, "status": self.status, "transaction": self.current_transaction}, self.terminal)

    def on_trash(self):
        if frappe.db.exists("Gate Transaction", {"lane": self.name}):
            frappe.throw(_("This lane has transactions. Close it instead of deleting it."))
