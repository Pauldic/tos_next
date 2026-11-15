# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe import _
from tos_next import transactions
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, get_time, getdate, now_datetime

from tos_next.tos_next.doctype.appointment_override.appointment_override import get_valid_override, mark_used
from tos_next.realtime import publish
from tos_next.settings import get as setting

ACTIVE = ("Booked", "Arrived", "In Progress", "Late")
VISIT_TYPES = {"In": "Receive", "Out": "Deliver", "Both": "Receive and Deliver"}
LINE_KEYS = ("move_type", "container", "container_length", "booking_ref")


def line_direction(move_type):
    return transactions.direction(move_type)


def moving_same_slot(doc, slot):
    return not doc.is_new() and doc.get_doc_before_save() and doc.get_doc_before_save().slot == slot.name


def slot_window(slot):
    start = get_datetime(f"{slot.slot_date} {get_time(slot.start_time)}")
    end = get_datetime(f"{slot.slot_date} {get_time(slot.end_time)}")
    return start, end


class Appointment(Document):
    def validate(self):
        self.lines_from_header()
        self.check_lines_editable()
        self.check_lines()
        slot = frappe.get_doc("Slot Capacity", self.slot)
        self.terminal = slot.terminal
        self.slot_date, self.start_time, self.end_time = slot.slot_date, slot.start_time, slot.end_time
        for line in self.lines:
            transactions.assert_offered(line.move_type, self.terminal)
        self.check_parties(slot)
        self.check_chassis()
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
            if self.direction == "Both":
                frappe.throw(_("Slot {0} only accepts Gate {1} jobs. A visit that receives and delivers needs a slot open to both.").format(slot.name, allowed))
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

    # ---------- jobs (lines) ----------
    def lines_from_header(self):
        """Older callers (and the Desk form of an old record) give one job in move_type / container / booking_ref."""
        if not self.get("lines") and self.move_type:
            self.append("lines", {"move_type": self.move_type, "container": self.container or None, "booking_ref": self.booking_ref or None})

    def check_lines_editable(self):
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if not before or before.status in ("Booked", "Late"):
            return
        sig = lambda d: [tuple(l.get(k) for k in LINE_KEYS) for l in d.get("lines")]
        if sig(before) != sig(self):
            frappe.throw(_("The jobs of an appointment cannot be changed once the truck has arrived."))

    def check_lines(self):
        if not self.get("lines"):
            frappe.throw(_("Add at least one job: a Receive or a Deliver."))
        seen = set()
        for i, line in enumerate(self.lines, 1):
            where = _("Job {0}").format(i)
            tt = transactions.get(line.move_type)
            pending = line.status in (None, "", "Pending")
            if line.container and not frappe.db.exists("Container", line.container):
                if tt.direction == "Out":
                    frappe.throw(_("{0}: container {1} is not in the system.").format(where, line.container))
                line.container = None   # a container the terminal has not seen yet is created at the gate
            if line.container:
                c = frappe.get_doc("Container", line.container)
                line.container_length = c.length_ft or line.container_length
                if line.container in seen:
                    frappe.throw(_("{0}: {1} is listed twice on this appointment.").format(where, line.container))
                seen.add(line.container)
                if pending:
                    transactions.check_container_fits(tt, c, where)
                    other = frappe.db.sql("""select a.name from `tabAppointment Line` l join `tabAppointment` a on a.name = l.parent
                        where l.container = %s and l.status = 'Pending' and a.status in %s and a.name != %s limit 1""", (c.name, ACTIVE, self.name or ""))
                    if other:
                        frappe.throw(_("{0}: {1} already has an appointment: {2}.").format(where, c.name, other[0][0]))
            if not line.container_length or int(line.container_length) < 1:
                frappe.throw(_("{0}: give the size (ft) of the container, or choose the container.").format(where))
            line.container_length = int(line.container_length)
            if tt.requires_booking and not line.booking_ref:
                frappe.throw(_("{0}: {1} needs a booking reference.").format(where, tt.name))
            if tt.requires_container and not line.container:
                frappe.throw(_("{0}: choose the container for {1}.").format(where, tt.name))
            if not line.status:
                line.status = "Pending"
        dirs = {transactions.direction(l.move_type) for l in self.lines}
        self.direction = "Both" if len(dirs) > 1 else dirs.pop()
        self.visit_type = VISIT_TYPES[self.direction]
        first = self.lines[0]
        self.move_type, self.container, self.booking_ref = first.move_type, first.container, first.booking_ref

    def check_chassis(self):
        """What is on the truck at one time must fit its chassis: first everything it drops off, then everything it
        picks up. A truck that brought one 40 ft can leave with one 40, one 20 or two 20 if its chassis allows it."""
        truck = frappe.get_cached_doc("Truck", self.truck)
        if not truck.chassis_type:
            frappe.throw(_("Truck {0} has no chassis type. Set it on the truck first.").format(truck.name))
        live = [l for l in self.lines if l.status in (None, "", "Pending")]
        truck.check_load([l.container_length for l in live if transactions.is_in(l.move_type)], _("receive"))
        truck.check_load([l.container_length for l in live if not transactions.is_in(l.move_type)], _("deliver"))

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
        for line in self.lines:
            if line.status == "Pending":
                line.status = "Cancelled"
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
        grace = graces.setdefault(r.terminal, setting("late_grace_minutes", r.terminal))
        if now >= end:
            frappe.db.set_value("Appointment", r.name, "status", "No-show")
            frappe.db.sql("update `tabSlot Capacity` set booked = greatest(booked - 1, 0) where name = %s", r.slot)
            publish("appointment_status", {"appointment": r.name, "status": "No-show"}, r.terminal)
        elif r.status == "Booked" and now >= add_to_date(start, minutes=grace):
            frappe.db.set_value("Appointment", r.name, "status", "Late")
            publish("appointment_status", {"appointment": r.name, "status": "Late"}, r.terminal)
