# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_time, getdate, nowdate

DAY_FIELDS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class SlotTemplate(Document):
    def validate(self):
        if not any(self.get(d) for d in DAY_FIELDS):
            frappe.throw(_("Choose at least one day."))
        spans = []
        for line in self.lines:
            start, end = get_time(line.from_time), get_time(line.to_time)
            if end <= start:
                frappe.throw(_("Row {0}: end time must be after start time.").format(line.idx))
            if (line.capacity_trucks or 0) < 1:
                frappe.throw(_("Row {0}: capacity must be at least 1.").format(line.idx))
            spans.append((start, end, line.idx, line.move_types))
        spans.sort()
        for a, b in zip(spans, spans[1:]):
            if b[0] < a[1] and (a[3] == "All" or b[3] == "All" or a[3] == b[3]):
                frappe.throw(_("Rows {0} and {1} overlap.").format(a[2], b[2]))

    @frappe.whitelist()
    def generate(self, days_ahead=14):
        frappe.only_for(["Appointment Planner", "Terminal Admin", "System Manager"])
        n = generate_slots(template=self.name, days_ahead=int(days_ahead))
        frappe.msgprint(_("{0} slots created.").format(n), alert=True)
        return n


def generate_slots(template=None, days_ahead=14):
    """Create Slot Capacity rows from templates. Safe to run daily: existing slots are left alone."""
    filters = {"is_active": 1}
    if template:
        filters["name"] = template
    created = 0
    for tname in frappe.get_all("Slot Template", filters=filters, pluck="name"):
        t = frappe.get_doc("Slot Template", tname)
        for offset in range(days_ahead + 1):
            day = getdate(add_days(nowdate(), offset))
            if not t.get(DAY_FIELDS[day.weekday()]):
                continue
            for line in t.lines:
                start = get_time(line.from_time)
                name = f"{t.terminal}-{day}-{start.strftime('%H%M')}"
                if frappe.db.exists("Slot Capacity", name):
                    continue
                frappe.get_doc({
                    "doctype": "Slot Capacity", "terminal": t.terminal, "slot_date": day,
                    "start_time": line.from_time, "end_time": line.to_time,
                    "capacity": line.capacity_trucks, "move_types": line.move_types, "template": t.name,
                }).insert(ignore_permissions=True)
                created += 1
    return created
