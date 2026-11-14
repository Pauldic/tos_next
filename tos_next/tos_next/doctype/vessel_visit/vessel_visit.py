# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class VesselVisit(Document):
	def validate(self):
		if not (self.ib_voyage or self.ob_voyage):
			frappe.throw(_("Give the in-bound voyage, the out-bound voyage, or both."))
		if self.eta and self.etd and self.etd < self.eta:
			frappe.throw(_("The vessel cannot depart before it arrives."))
		if self.ata and self.atd and self.atd < self.ata:
			frappe.throw(_("The actual departure cannot be before the actual arrival."))
		name = frappe.db.get_value("Vessel", self.vessel, "vessel_name") or self.vessel
		voyages = "/".join(v for v in (self.ib_voyage, self.ob_voyage) if v)
		self.visit_title = f"{name} {voyages}"
