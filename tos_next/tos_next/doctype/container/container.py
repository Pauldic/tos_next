# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, date_diff

from tos_next.yard import POSITION_FLAG

_VALUES = {}
_n = 10
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    if _n % 11 == 0:
        _n += 1
    _VALUES[_ch] = _n
    _n += 1


def normalise_no(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def iso6346_check_digit(code10: str) -> int:
    total = 0
    for i, ch in enumerate(code10):
        total += (_VALUES[ch] if ch.isalpha() else int(ch)) * (2 ** i)
    return total % 11 % 10


class Container(Document):
    def autoname(self):
        self.container_no = normalise_no(self.container_no)
        self.name = self.container_no

    def validate(self):
        self.container_no = normalise_no(self.container_no)
        self.check_number()
        self.sync_from_type()
        self.check_position_not_edited_by_hand()
        self.check_dates_and_weights()

    def onload(self):
        if self.arrived_on and self.status == "On Terminal":
            self.set_onload("dwell_days", date_diff(now_datetime(), self.arrived_on))

    def check_number(self):
        no = self.container_no
        if not re.fullmatch(r"[A-Z]{3}[UJZ][0-9]{7}", no or ""):
            frappe.throw(_("Container number must be 4 letters (the fourth is U, J or Z) followed by 7 digits."))
        ok = iso6346_check_digit(no[:10]) == int(no[10])
        if not ok:
            msg = _("Check digit of {0} does not match ISO 6346.").format(no)
            # Set "meridian_strict_iso6346": 1 in site_config.json to make this an error.
            if frappe.conf.get("meridian_strict_iso6346"):
                frappe.throw(msg)
            frappe.msgprint(msg, indicator="orange", alert=True)

    def sync_from_type(self):
        if self.container_type:
            t = frappe.get_cached_doc("Container Type", self.container_type)
            self.length_ft = t.length_ft
            self.slot_span = t.slot_span
            if t.max_gross_kg and self.gross_weight_kg and self.gross_weight_kg > t.max_gross_kg:
                frappe.throw(_("Gross weight exceeds the maximum for type {0}.").format(t.name))

    def check_position_not_edited_by_hand(self):
        if self.is_new():
            if self.yard_stack:
                frappe.throw(_("Place a container on a stack with a Move Order, not by editing it."))
            return
        before = self.get_doc_before_save()
        if before and not frappe.flags.get(POSITION_FLAG):
            for f in ("yard_stack", "partner_stack", "tier"):
                if (before.get(f) or None) != (self.get(f) or None):
                    frappe.throw(_("Position can only change through a Move Order or a gate transaction."))
        if self.status != "On Terminal" and self.yard_stack and not frappe.flags.get(POSITION_FLAG):
            frappe.throw(_("Only containers on the terminal can sit in the yard."))

    def check_dates_and_weights(self):
        if self.free_days_until and self.arrived_on and getdate(self.free_days_until) < getdate(self.arrived_on):
            frappe.throw(_("Free days cannot end before the container arrived."))
        if self.vgm_kg and self.gross_weight_kg and self.vgm_kg < 0:
            frappe.throw(_("Verified gross mass cannot be negative."))

    def on_trash(self):
        if self.yard_stack:
            frappe.throw(_("Remove the container from the yard before deleting it."))
        if frappe.db.exists("Container Movement", {"container": self.name}):
            frappe.throw(_("This container has movement history and cannot be deleted."))
