# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

TEU_BY_LENGTH = {"20": 1.0, "40": 2.0, "45": 2.25}


class ContainerType(Document):
	def validate(self):
		self.iso_type = (self.iso_type or "").strip().upper()
		self.slot_span = 1 if self.length_ft == "20" else 2
		self.teu = TEU_BY_LENGTH.get(self.length_ft, 1.0)
		if self.tare_kg and self.max_gross_kg and self.tare_kg >= self.max_gross_kg:
			frappe.throw(_("Tare weight must be lower than the maximum gross weight."))
