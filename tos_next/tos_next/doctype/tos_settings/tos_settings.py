# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TOSSettings(Document):
	def validate(self):
		if (self.override_valid_hours or 0) < 1:
			frappe.throw(_("An approved override must be valid for at least one hour."))
		if (self.min_override_reason_length or 0) < 1:
			frappe.throw(_("The minimum reason length must be at least 1 character."))
		for field in ("slot_length_m", "row_pitch_m", "tier_height_m", "car_bay_width_m", "truck_bay_width_m"):
			if (self.get(field) or 0) <= 0:
				frappe.throw(_("{0} must be more than zero.").format(_(self.meta.get_label(field))))
		if (self.block_gap_m or 0) < 0:
			frappe.throw(_("The gap between blocks cannot be negative."))
