# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class YardBlock(Document):
	def validate(self):
		if (self.bay_count or 0) < 2 or self.bay_count % 2:
			frappe.throw(_("Bays must be an even number of at least 2, so every 40 ft container has two adjacent 20 ft slots."))
		if (self.row_count or 0) < 1:
			frappe.throw(_("Rows must be at least 1."))
		terminal_max = frappe.db.get_value("Terminal", self.terminal, "max_tier") or 6
		if not 1 <= (self.max_tier or 0) <= terminal_max:
			frappe.throw(_("Maximum Tier Height must be between 1 and {0} (the terminal limit).").format(terminal_max))
		if not self.is_new() and self.stacks_generated:
			before = self.get_doc_before_save()
			if before and (before.bay_count != self.bay_count or before.row_count != self.row_count):
				frappe.throw(_("Bays and rows cannot change after stacks are generated. Block the unused stacks instead."))

	@frappe.whitelist()
	def generate_stacks(self):
		"""Create one Yard Stack per bay and row. Safe to run again: existing stacks are skipped."""
		frappe.only_for(["Terminal Admin", "Yard Planner", "System Manager"])
		created = 0
		for bay in range(1, self.bay_count + 1):
			for row in range(1, self.row_count + 1):
				name = f"{self.name}-{bay:02d}-{row:02d}"
				if frappe.db.exists("Yard Stack", name):
					continue
				frappe.get_doc({
					"doctype": "Yard Stack",
					"yard_block": self.name,
					"bay": bay,
					"row_no": row,
				}).insert(ignore_permissions=True)
				created += 1
		self.db_set("stacks_generated", 1)
		frappe.msgprint(_("{0} stacks created.").format(created), alert=True)
		return created
