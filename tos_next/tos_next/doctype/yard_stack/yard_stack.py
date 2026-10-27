# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class YardStack(Document):
	def autoname(self):
		self.name = f"{self.yard_block}-{int(self.bay):02d}-{int(self.row_no):02d}"

	def validate(self):
		block = frappe.get_cached_doc("Yard Block", self.yard_block)
		if not 1 <= self.bay <= block.bay_count:
			frappe.throw(_("Bay must be between 1 and {0} for block {1}.").format(block.bay_count, block.name))
		if not 1 <= self.row_no <= block.row_count:
			frappe.throw(_("Row must be between 1 and {0} for block {1}.").format(block.row_count, block.name))
		self.max_tier = block.max_tier
		self.is_forty_anchor = 1 if self.bay % 2 == 1 else 0
		self.pair_stack = f"{self.yard_block}-{self.bay + 1:02d}-{self.row_no:02d}" if self.is_forty_anchor else None
		if (self.tier_count or 0) > self.max_tier:
			frappe.throw(_("Tiers in use cannot exceed the maximum tier height."))

	def on_trash(self):
		if self.tier_count:
			frappe.throw(_("Cannot delete a stack that still holds containers."))
