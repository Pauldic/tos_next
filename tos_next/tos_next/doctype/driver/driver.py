# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class Driver(Document):
	def validate(self):
		self.licence_no = (self.licence_no or "").strip().upper()

	def is_licence_valid(self, on_date=None) -> bool:
		"""True if the licence is still valid on the given date (default today)."""
		return getdate(self.licence_expiry) >= getdate(on_date)

	def assert_can_work(self, on_date=None):
		if self.is_blocked:
			frappe.throw(_("Driver {0} is blocked: {1}").format(self.full_name, self.block_reason or ""))
		if not self.is_licence_valid(on_date):
			frappe.throw(_("Driver {0} has an expired licence.").format(self.full_name))
