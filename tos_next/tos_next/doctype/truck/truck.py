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
		if self.chassis_type and not frappe.db.get_value("Chassis Type", self.chassis_type, "is_active"):
			frappe.throw(_("Chassis type {0} is not active.").format(self.chassis_type))

	def chassis(self):
		return frappe.get_cached_doc("Chassis Type", self.chassis_type)

	def can_carry(self, length_ft) -> bool:
		"""One container of this length on this truck's chassis."""
		return self.chassis().fits([length_ft or 40])

	def check_load(self, lengths, what=None):
		"""Throws unless all these containers can be on the truck at the same time."""
		lengths = [int(x) for x in lengths if x]
		if not lengths:
			return
		ch = self.chassis()
		if not ch.fits(lengths):
			frappe.throw(_("Truck {0} cannot take {1}{2}: {3}.").format(
				self.name, " + ".join(f"{x} ft" for x in lengths), f" ({what})" if what else "", ch.explain(lengths)))
