# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TransactionType(Document):
	def validate(self):
		self.transaction_name = (self.transaction_name or "").strip()
		if self.direction == "Out":
			self.category = None   # the category of a container that leaves is not changed
		if self.has_value_changed("direction") and not self.is_new() and self.in_use():
			frappe.throw(_("Appointments or gate visits already use {0}, so its gate cannot change. Add a new transaction type instead.").format(self.name))

	def in_use(self):
		return any(frappe.db.exists(dt, {"move_type": self.name}) for dt in ("Appointment Line", "Gate Transaction"))

	def on_trash(self):
		if self.in_use():
			frappe.throw(_("{0} is used by appointments or gate visits. Untick Active instead of deleting it.").format(self.name))
