# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class Truck(Document):
	def validate(self):
		self.plate_no = re.sub(r"\s+", " ", (self.plate_no or "").strip().upper())
		if not self.plate_no:
			frappe.throw(_("Plate Number is required."))
		if self.carrier and frappe.db.get_value("Carrier", self.carrier, "is_blocked"):
			frappe.throw(_("Carrier {0} is blocked.").format(self.carrier))

	def can_carry(self, length_ft: int) -> bool:
		limit = {"20 ft only": 20, "Up to 40 ft": 40, "Up to 45 ft": 45}.get(self.max_container_length, 40)
		return int(length_ft) <= limit
