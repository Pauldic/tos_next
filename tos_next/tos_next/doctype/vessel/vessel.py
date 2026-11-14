# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class Vessel(Document):
	def validate(self):
		self.vessel_code = (self.vessel_code or "").strip().upper()
		if self.imo_no and not re.fullmatch(r"(IMO)?\s*\d{7}", self.imo_no.strip().upper()):
			frappe.throw(_("An IMO number has 7 digits, for example 9321483."))
		if self.loa_m is not None and self.loa_m < 0:
			frappe.throw(_("Length overall cannot be negative."))
