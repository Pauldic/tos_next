# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, get_time, getdate, now_datetime

from tos_next.tos_next.doctype.appointment_override.appointment_override import get_valid_override, mark_used
from tos_next.realtime import publish

IN_MOVES = ("Export Drop", "Empty Return")
ACTIVE = ("Booked", "Arrived", "In Progress", "Late")


def moving_same_slot(doc, slot):
    return not doc.is_new() and doc.get_doc_before_save() and doc.get_doc_before_save().slot == slot.name


def slot_window(slot):
    start = get_datetime(f"{slot.slot_date} {get_time(slot.start_time)}")
    end = get_datetime(f"{slot.slot_date} {get_time(slot.end_time)}")
    return start, end


class Appointment(Document):
    def validate(self):
        self.direction = "In" if self.move_type in IN_MOVES else "Out"
        slot = frappe.get_doc("Slot Capacity", self.slot)
        self.terminal = slot.terminal
        self.slot_date, self.start_time, self.end_time = slot.slot_date, slot.start_time, slot.end_time
        self.check_parties(slot)
        self.check_container()
        if self.is_new():
            self.qr_token = secrets.token_urlsafe(12)
            self.check_slot(slot)
        else:
            before = self.get_doc_before_save()
            if before.slot != self.slot and before.status not in ("Booked", "Late"):
                frappe.throw(_("Only a booked appointment can move to another slot."))
            if before.slot != self.slot:
                self.check_slot(frappe.get_doc("Slot Capacity", self.slot), moving=True)

    # ---------- rules ----------
    def check_slot(self, slot, moving=False):
        if slot.is_closed:
            frappe.throw(_("Slot {0} is closed: {1}").format(slot.name, slot.closed_reason or ""))
        allowed = {"All": None, "Gate In": "In", "Gate Out": "Out"}[slot.move_types]
        if allowed and allowed != self.direction:
            frappe.throw(_("Slot {0} only accepts Gate {1} moves.").format(slot.name, allowed))
        start, end = slot_window(slot)
        needs = []
        if end < now_datetime():
            needs.append("Outside Slot Window")
        # lock the row so two bookings cannot both take the last place
        row = frappe.db.get_value("Slot Capacity", slot.name, ["booked", "capacity"], as_dict=True, for_update=True)
        if row.booked >= row.capacity and not moving_same_slot(self, slot):
            needs.append("Over Capacity")
        if len(needs) > 1:
            frappe.throw(_("Slot {0} has already ended and is full. Choose another slot.").format(slot.name))
        if needs:
            o = get_valid_override(self.override, needs, slot.terminal, self.carrier, self.truck, slot.name)
            self.flags.override_to_use = o.name

    def check_parties(self, slot):
        carrier = frappe.get_cached_doc("Carrier", self.carrier)
        if carrier.is_blocked:
            frappe.throw(_("Carrier {0} is blocked: {1}").format(carrier.name, carrier.block_reason or ""))
        truck = frappe.get_doc("Truck", self.truck)
        if truck.carrier != self.carrier:
            frappe.throw(_("Truck {0} belongs to {1}, not {2}.").format(truck.name, truck.carrier, self.carrier))
        if truck.is_blocked:
            frappe.throw(_("Truck {0} is blocked: {1}").format(truck.name, truck.block_reason or ""))
        driver = frappe.get_doc("Driver", self.driver)
        if driver.carrier != self.carrier:
            frappe.throw(_("Driver {0} works for {1}, not {2}.").format(driver.name, driver.carrier, self.carrier))
        driver.assert_can_work(slot.slot_date)
        if self.is_new() and carrier.daily_appointment_limit:
            booked_today = frappe.db.count("Appointment", {"carrier": self.carrier, "slot_date": slot.slot_date, "status": ["in", ACTIVE]})
            if booked_today >= carrier.daily_appointment_limit:
                frappe.throw(_("{0} has reached its limit of {1} appointments on {2}.").format(carrier.name, carrier.daily_appointment_limit, slot.slot_date))

    def check_container(self):
        if not self.container:
            return
        c = frappe.get_doc("Container", self.container)
        if self.move_type in ("Import Pickup", "Empty Pickup"):
            if c.status != "On Terminal":
                frappe.throw(_("{0} is not on the terminal.").format(c.name))
            if c.is_on_hold:
                frappe.throw(_("{0} is on hold and cannot be picked up.").format(c.name))
        truck = frappe.get_cached_doc("Truck", self.truck)
        if not truck.can_carry(c.length_ft or 40):
            frappe.throw(_("Truck {0} cannot carry a {1} ft container.").format(truck.name, c.length_ft))
        other = frappe.db.exists("Appointment", {"container": c.name, "status": ["in", ACTIVE], "name": ["!=", self.name]})
        if other:
            frappe.throw(_("{0} already has an appointment: {1}.").format(c.name, other))

    # ---------- capacity bookkeeping ----------
    def after_insert(self):
        frappe.db.sql("update `tabSlot Capacity` set booked = booked + 1 where name = %s", self.slot)
        if self.flags.get("override_to_use"):
            mark_used(self.flags.override_to_use, "Appointment", self.name)
        self.publish_capacity()

    def on_update(self):
        before = self.get_doc_before_save()
        if before and before.slot != self.slot and self.status in ACTIVE:
            frappe.db.sql("update `tabSlot Capacity` set booked = greatest(booked - 1, 0) where name = %s", before.slot)
            frappe.db.sql("update `tabSlot Capacity` set booked = booked + 1 where name = %s", self.slot)
            if self.flags.get("override_to_use"):
                mark_used(self.flags.override_to_use, "Appointment", self.name)
            self.publish_capacity()

    def publish_capacity(self):
        row = frappe.db.get_value("Slot Capacity", self.slot, ["booked", "capacity"], as_dict=True)
        publish("slot_booked", {"slot": self.slot, "booked": row.booked, "capacity": row.capacity}, self.terminal)

    def _release_capacity(self):
        frappe.db.sql("update `tabSlot Capacity` set booked = greatest(booked - 1, 0) where name = %s", self.slot)
        self.publish_capacity()

    def on_trash(self):
        if self.status in ("Arrived", "In Progress", "Completed"):
            frappe.throw(_("An appointment that was used cannot be deleted."))
        if self.status in ACTIVE:
            self._release_capacity()

    # ---------- actions ----------
    @frappe.whitelist()
    def cancel_appointment(self, reason):
        if not reason:
            frappe.throw(_("A reason is required."))
        if self.status not in ("Booked", "Late"):
            frappe.throw(_("Only a booked or late appointment can be cancelled."))
        self.status = "Cancelled"
        self.cancel_reason = reason
        self.save()
        self._release_capacity()


def mark_late_and_no_show():
    """Scheduler job, every 5 minutes."""
    now = now_datetime()
    rows = frappe.get_all("Appointment", filters={"status": ["in", ["Booked", "Late"]], "slot_date": ["<=", getdate(now)]},
                          fields=["name", "status", "slot", "terminal"])
    graces = {}
    for r in rows:
        slot = frappe.get_cached_doc("Slot Capacity", r.slot)
        start, end = slot_window(slot)
        grace = graces.setdefault(r.terminal, frappe.db.get_value("Terminal", r.terminal, "late_grace_minutes") or 15)
        if now >= end:
            frappe.db.set_value("Appointment", r.name, "status", "No-show")
            frappe.db.sql("update `tabSlot Capacity` set booked = greatest(booked - 1, 0) where name = %s", r.slot)
            publish("appointment_status", {"appointment": r.name, "status": "No-show"}, r.terminal)
        elif r.status == "Booked" and now >= add_to_date(start, minutes=grace):
            frappe.db.set_value("Appointment", r.name, "status", "Late")
            publish("appointment_status", {"appointment": r.name, "status": "Late"}, r.terminal)
