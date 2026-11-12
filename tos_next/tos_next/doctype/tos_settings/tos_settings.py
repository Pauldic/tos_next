# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TOSSettings(Document):
	def validate(self):
		if (self.override_valid_hours or 0) < 1:
			frappe.throw(_("An approved override must be valid for at least one hour."))
		if (self.min_override_reason_length or 0) < 1:
			frappe.throw(_("The minimum reason length must be at least 1 character."))
