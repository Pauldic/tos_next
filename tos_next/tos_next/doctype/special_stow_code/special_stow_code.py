# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SpecialStowCode(Document):
	def validate(self):
		self.stow_code = (self.stow_code or "").strip().upper()
