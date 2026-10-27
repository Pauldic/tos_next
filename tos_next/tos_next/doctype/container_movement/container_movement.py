# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ContainerMovement(Document):
    """Append-only history. Nobody edits or deletes a row, including administrators."""

    def validate(self):
        if not self.is_new():
            frappe.throw(_("Container Movement rows cannot be changed."))
        if self.from_stack and self.from_tier is None:
            frappe.throw(_("From Tier is required with From Stack."))
        if self.to_stack and not self.to_tier:
            frappe.throw(_("To Tier is required with To Stack."))

    def on_trash(self):
        if not frappe.flags.in_uninstall and not frappe.flags.in_test:
            frappe.throw(_("Container Movement rows cannot be deleted."))
