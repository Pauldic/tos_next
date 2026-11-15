# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ChassisType(Document):
	def validate(self):
		if min(self.max_container_length_ft or 0, self.max_containers or 0, self.max_total_length_ft or 0) < 1:
			frappe.throw(_("Longest container, most containers and total length must all be at least 1."))
		if self.max_total_length_ft < self.max_container_length_ft:
			frappe.throw(_("Total length cannot be shorter than the longest single container."))

	def on_trash(self):
		if frappe.db.exists("Truck", {"chassis_type": self.name}):
			frappe.throw(_("Trucks still use this chassis type. Change them first, or untick Active."))

	def fits(self, lengths):
		"""True when containers of these lengths (ft) can ride this chassis together."""
		lengths = [int(x) for x in lengths]
		return (len(lengths) <= self.max_containers and sum(lengths) <= self.max_total_length_ft
				and all(x <= self.max_container_length_ft for x in lengths))

	def explain(self, lengths):
		lengths = [int(x) for x in lengths]
		too_long = [x for x in lengths if x > self.max_container_length_ft]
		if too_long:
			return _("a {0} ft container does not fit a {1} chassis (longest {2} ft)").format(too_long[0], self.name, self.max_container_length_ft)
		if len(lengths) > self.max_containers:
			return _("a {0} chassis carries at most {1} container(s) at once, not {2}").format(self.name, self.max_containers, len(lengths))
		return _("{0} ft of containers is more than the {1} ft a {2} chassis carries").format(sum(lengths), self.max_total_length_ft, self.name)
