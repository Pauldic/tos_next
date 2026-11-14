# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class ContainerHazard(Document):
	def validate(self):
		un = re.sub(r"\D", "", self.un_number or "")
		if len(un) != 4:
			frappe.throw(_("Row {0}: a UN number has 4 digits, for example 1203.").format(self.idx))
		self.un_number = un
