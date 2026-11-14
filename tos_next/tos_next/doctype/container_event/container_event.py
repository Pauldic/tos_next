# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ContainerEvent(Document):
	"""A line in a container's history. Written by the system (tos_next.events.log), never edited."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Container events are a record and cannot be changed."))

	def on_trash(self):
		if not frappe.flags.in_install and frappe.session.user != "Administrator":
			frappe.throw(_("Container events are a record and cannot be deleted."))
