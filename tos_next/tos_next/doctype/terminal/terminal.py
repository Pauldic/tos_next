# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Terminal(Document):
	def validate(self):
		if not 1 <= (self.max_tier or 0) <= 6:
			frappe.throw(_("Maximum Tier Height must be between 1 and 6."))
		if self.opening_time and self.closing_time and self.opening_time == self.closing_time:
			frappe.throw(_("Opening and closing time cannot be the same."))
