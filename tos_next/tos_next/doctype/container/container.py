# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, date_diff, getdate, now_datetime

from tos_next import events
from tos_next.settings import company
from tos_next.yard import POSITION_FLAG

_VALUES = {}
_n = 10
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    if _n % 11 == 0:
        _n += 1
    _VALUES[_ch] = _n
    _n += 1

# Fields whose changes are written to the container's event log, grouped by the kind of event they make.
LOGGED = {
    "Status Change": ["status", "transit_state"],
    "Seal": ["seal_no", "seal_verified"],
    "Vessel": ["ib_visit", "ob_visit"],
    "Cargo Details": ["category", "full_empty", "container_type", "shipping_line", "line", "terminal_line", "group_code", "consignee", "gross_weight_kg", "vgm_kg", "booking_ref", "bill_of_lading"],
    "Planning": ["planned_position", "pol", "pod", "destination", "place_of_delivery", "special_stow_1", "special_stow_2", "special_stow_3", "special_stow_4", "special_stow_5"],
    "Reefer": ["reefer_set_temp_c", "reefer_plugged"],
    "Hazard": ["imdg_summary"],
    "Commercial": ["free_days_until", "storage_paid_date", "reefer_storage_paid", "line_storage_paid"],
    "Remarks": ["remarks"],
}


def normalise_no(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def iso6346_check_digit(code10: str) -> int:
    total = 0
    for i, ch in enumerate(code10):
        total += (_VALUES[ch] if ch.isalpha() else int(ch)) * (2 ** i)
    return total % 11 % 10


def transit_for(status, yard_stack):
    """Where a container is in its journey through the terminal, from its status and whether it sits on a stack."""
    if status == "On Terminal":
        return "Yard" if yard_stack else "Awaiting Slot"
    return {"Expected": "Expected", "Loaded on Vessel": "On Vessel", "Gated Out": "Gated Out"}.get(status, status)


def position_text(yard_stack, partner_stack, tier):
    """Block, bay, row and tier on one line, for example A-03-02-1. A 40 ft container shows both bays: A-03/04-02-1."""
    if not yard_stack:
        return None
    s = frappe.db.get_value("Yard Stack", yard_stack, ["yard_block", "bay", "row_no"], as_dict=True)
    if not s:
        return None
    code = frappe.db.get_value("Yard Block", s.yard_block, "block_code") or s.yard_block
    bay = f"{s.bay:02d}"
    if partner_stack:
        p = frappe.db.get_value("Yard Stack", partner_stack, "bay")
        if p:
            bay = "/".join(f"{b:02d}" for b in sorted((s.bay, p)))
    return f"{code}-{bay}-{s.row_no:02d}-{tier or 0}"


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
        self.check_reefer()
        self.sync_hazards()
        self.work_out_position_and_state()

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
            # TOS Settings -> "Reject Wrong Container Check Digits" turns this warning into an error.
            if company("strict_iso6346"):
                frappe.throw(msg)
            frappe.msgprint(msg, indicator="orange", alert=True)

    def sync_from_type(self):
        if self.container_type:
            t = frappe.get_cached_doc("Container Type", self.container_type)
            self.length_ft = t.length_ft
            self.slot_span = t.slot_span
            self.is_reefer = 1 if t.is_reefer else 0
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
                if before.get(f) != self.get(f):
                    frappe.throw(_("Position can only change through a Move Order or a gate transaction."))
        if self.status != "On Terminal" and self.yard_stack and not frappe.flags.get(POSITION_FLAG):
            frappe.throw(_("Only containers on the terminal can sit in the yard."))

    def check_dates_and_weights(self):
        if self.free_days_until and self.arrived_on and getdate(self.free_days_until) < getdate(self.arrived_on):
            frappe.throw(_("Free days cannot end before the container arrived."))
        if self.vgm_kg and self.gross_weight_kg and self.vgm_kg < 0:
            frappe.throw(_("Verified gross mass cannot be negative."))
        if self.ib_visit and self.ob_visit and self.ib_visit != self.ob_visit:
            ib, ob = (frappe.db.get_value("Vessel Visit", v, ["eta", "etd"], as_dict=True) for v in (self.ib_visit, self.ob_visit))
            if ib and ob and ib.eta and ob.etd and ob.etd < ib.eta:
                frappe.throw(_("The out-bound vessel leaves before the in-bound vessel arrives."))

    def check_reefer(self):
        if not self.is_reefer:
            if self.reefer_plugged or self.reefer_set_temp_c is not None and self.reefer_set_temp_c != 0:
                frappe.throw(_("{0} is not a reefer type, so it has no set temperature or power connection.").format(self.container_type or self.name))
            return
        if self.reefer_plugged and not self.reefer_plugged_on:
            self.reefer_plugged_on = now_datetime()
        if not self.reefer_plugged:
            self.reefer_plugged_on = None
        if self.reefer_set_temp_c is not None and not -40 <= self.reefer_set_temp_c <= 40:
            frappe.throw(_("A reefer set temperature must be between -40 and 40 °C."))

    def sync_hazards(self):
        classes = []
        for row in self.hazards or []:
            if row.imdg_class not in classes:
                classes.append(row.imdg_class)
        self.is_hazmat = 1 if self.hazards else 0
        self.imdg_summary = ", ".join(classes) or None

    def work_out_position_and_state(self):
        self.transit_state = transit_for(self.status, self.yard_stack)
        self.position = position_text(self.yard_stack, self.partner_stack, self.tier)
        if self.seal_verified and not self.seal_verified_on:
            self.seal_verified_on = now_datetime()
            self.seal_verified_by = frappe.session.user
        if not self.seal_verified:
            self.seal_verified_on = self.seal_verified_by = None

    def on_update(self):
        before = self.get_doc_before_save()
        if not before:
            events.log(self.name, "Created", _("Container created ({0}, {1}).").format(self.category, self.full_empty), self.terminal)
            return
        for event_type, fields in LOGGED.items():
            changes = []
            for f in fields:
                old, new = before.get(f), self.get(f)
                if cstr(old) != cstr(new):
                    changes.append(f"{_(self.meta.get_label(f))}: {cstr(old) or '–'} → {cstr(new) or '–'}")
            if changes:
                events.log(self.name, event_type, "; ".join(changes), self.terminal)

    def on_trash(self):
        if self.yard_stack:
            frappe.throw(_("Remove the container from the yard before deleting it."))
        if frappe.db.exists("Container Movement", {"container": self.name}):
            frappe.throw(_("This container has movement history and cannot be deleted."))
