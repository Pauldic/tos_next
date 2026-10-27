# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class ShippingLine(Document):
	def validate(self):
		prefixes = []
		for raw in (self.iso_prefixes or "").splitlines():
			p = raw.strip().upper()
			if not p:
				continue
			if not re.fullmatch(r"[A-Z]{3}U", p):
				frappe.throw(_("Owner prefix {0} must be three letters followed by U.").format(p))
			prefixes.append(p)
		self.iso_prefixes = "\n".join(prefixes)
