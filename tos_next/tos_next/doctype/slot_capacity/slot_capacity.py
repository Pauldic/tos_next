# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time


class SlotCapacity(Document):
    def autoname(self):
        self.name = f"{self.terminal}-{self.slot_date}-{get_time(self.start_time).strftime('%H%M')}"

    def validate(self):
        if get_time(self.end_time) <= get_time(self.start_time):
            frappe.throw(_("End time must be after start time."))
        if (self.capacity or 0) < 0:
            frappe.throw(_("Capacity cannot be negative."))
        if (self.capacity or 0) < (self.booked or 0):
            frappe.throw(_("Capacity cannot be lower than the {0} trucks already booked. Cancel or move appointments first.").format(self.booked))

    def on_trash(self):
        if self.booked:
            frappe.throw(_("This slot has appointments and cannot be deleted. Close it instead."))
