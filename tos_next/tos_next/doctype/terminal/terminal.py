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
		self.apply_profile()
		seen = set()
		for row in self.transaction_types:
			if row.transaction_type in seen:
				frappe.throw(_("{0} is listed twice under Transactions Offered.").format(row.transaction_type))
			seen.add(row.transaction_type)

	def apply_profile(self):
		"""Choosing a profile sets the switches. The switches can be changed by hand afterwards; they are only reset when the profile itself changes."""
		if not self.terminal_profile:
			self.terminal_profile = "Both"
		if self.is_new() or self.has_value_changed("terminal_profile"):
			self.has_marine_side = 0 if self.terminal_profile == "Bonded" else 1
			self.has_bonded_side = 0 if self.terminal_profile == "Marine" else 1
