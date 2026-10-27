# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, now_datetime

from tos_next.realtime import publish

APPROVER_ROLES = {"Gate Supervisor", "Terminal Admin", "System Manager"}
VALID_HOURS = 4          # an approved override can be used for this long
PENDING_HOURS = 4        # a request nobody decides on expires after this long
FINAL = ("Rejected", "Used", "Expired")


class AppointmentOverride(Document):
    """The only way to get around an appointment rule, and every use is recorded.

    - A request needs a category and a real explanation.
    - A supervisor decides it. If the terminal asks for it, not the person who requested it.
    - Approved overrides expire, can be used once, and can never be deleted or edited.
    - Holds, blocked carriers and expired driver licences are never overridable.
    """

    def validate(self):
        if self.is_new():
            self.status = "Pending"
            self.requested_by = frappe.session.user
            self.requested_on = now_datetime()
            if len((self.reason or "").strip()) < 20:
                frappe.throw(_("Please explain the reason in at least 20 characters."))
            if self.override_type == "Over Capacity" and not self.slot:
                frappe.throw(_("Choose the slot for an Over Capacity override."))
            if self.override_type in ("Outside Slot Window", "Details Changed") and not self.appointment:
                frappe.throw(_("Choose the appointment this override changes."))
            if self.override_type == "No Appointment" and not (self.carrier and self.truck):
                frappe.throw(_("Carrier and truck are required for a No Appointment override."))
            return
        before = self.get_doc_before_save()
        if before.status in FINAL:
            frappe.throw(_("This override is {0} and can no longer be changed.").format(before.status))
        # Scope fields are fixed once requested, so an approval cannot be stretched to cover something else.
        for field in ("terminal", "override_type", "reason_category", "reason", "carrier", "truck", "driver",
                      "container", "appointment", "slot"):
            if before.get(field) != self.get(field):
                frappe.throw(_("{0} cannot be changed after the request is made.").format(self.meta.get_label(field)))

    def after_insert(self):
        self.add_comment("Info", _("Override requested by {0}: {1}").format(self.requested_by, self.reason_category))
        publish("override_requested", {"override": self.name, "type": self.override_type}, self.terminal)

    def on_trash(self):
        frappe.throw(_("Overrides are part of the audit trail and cannot be deleted."))

    # ---------- decisions ----------
    def _guard_decider(self, note):
        if not APPROVER_ROLES.intersection(frappe.get_roles()):
            frappe.throw(_("Only a Gate Supervisor or Terminal Admin can decide an override."))
        if self.status != "Pending":
            frappe.throw(_("This override is already {0}.").format(self.status))
        if not (note or "").strip():
            frappe.throw(_("A decision note is required."))
        if frappe.db.get_value("Terminal", self.terminal, "override_needs_second_approver") \
                and frappe.session.user == self.requested_by and "System Manager" not in frappe.get_roles():
            frappe.throw(_("A different person must approve an override you requested."))

    @frappe.whitelist()
    def approve(self, note):
        self._guard_decider(note)
        self.status = "Approved"
        self.approved_by = frappe.session.user
        self.approved_on = now_datetime()
        self.decision_note = note
        self.valid_until = add_to_date(now_datetime(), hours=VALID_HOURS)
        self.save()
        self.add_comment("Info", _("Approved by {0}: {1}").format(frappe.session.user, note))
        publish("override_decided", {"override": self.name, "status": "Approved"}, self.terminal)

    @frappe.whitelist()
    def reject(self, note):
        self._guard_decider(note)
        self.status = "Rejected"
        self.approved_by = frappe.session.user
        self.approved_on = now_datetime()
        self.decision_note = note
        self.save()
        self.add_comment("Info", _("Rejected by {0}: {1}").format(frappe.session.user, note))
        publish("override_decided", {"override": self.name, "status": "Rejected"}, self.terminal)


def get_valid_override(name, allowed_types, terminal, carrier=None, truck=None, slot=None, appointment=None):
    """Return the override if it is approved, unexpired, unused and covers this case. Throws otherwise."""
    if not name:
        frappe.throw(_("An approved Appointment Override is required."))
    o = frappe.db.get_value("Appointment Override", name, "*", as_dict=True)
    if not o:
        frappe.throw(_("Override {0} does not exist.").format(name))
    if o.status != "Approved":
        frappe.throw(_("Override {0} is {1}, not Approved.").format(name, o.status))
    if o.valid_until and get_datetime(o.valid_until) < now_datetime():
        frappe.throw(_("Override {0} has expired.").format(name))
    if o.override_type not in allowed_types:
        frappe.throw(_("Override {0} is for '{1}', which does not apply here.").format(name, o.override_type))
    if o.terminal != terminal:
        frappe.throw(_("Override {0} belongs to another terminal.").format(name))
    for field, value in (("carrier", carrier), ("truck", truck), ("slot", slot), ("appointment", appointment)):
        if o.get(field) and value and o.get(field) != value:
            frappe.throw(_("Override {0} was approved for {1} {2}, not {3}.").format(name, field, o.get(field), value))
    return o


def mark_used(name, doctype, docname):
    frappe.db.set_value("Appointment Override", name, {
        "status": "Used", "used_by_doctype": doctype, "used_by_name": docname, "used_on": now_datetime(),
    }, update_modified=True)
    doc = frappe.get_doc("Appointment Override", name)
    doc.add_comment("Info", _("Used in {0} {1} by {2}").format(doctype, docname, frappe.session.user))
    publish("override_used", {"override": name, "used_by": f"{doctype} {docname}"}, doc.terminal)


def expire_overrides():
    """Scheduler job. Approved overrides past valid_until, and old undecided requests, expire."""
    now = now_datetime()
    for name in frappe.get_all("Appointment Override", filters={"status": "Approved", "valid_until": ["<", now]}, pluck="name"):
        frappe.db.set_value("Appointment Override", name, "status", "Expired")
    cutoff = add_to_date(now, hours=-PENDING_HOURS)
    for name in frappe.get_all("Appointment Override", filters={"status": "Pending", "requested_on": ["<", cutoff]}, pluck="name"):
        frappe.db.set_value("Appointment Override", name, "status", "Expired")
