# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, date_diff, get_datetime, get_time, now_datetime, time_diff_in_seconds

from tos_next import yard
from tos_next.tos_next.doctype.appointment.appointment import slot_window
from tos_next.tos_next.doctype.appointment_override.appointment_override import get_valid_override, mark_used
from tos_next.tos_next.doctype.container.container import normalise_no
from tos_next.realtime import publish

IN_STEPS = ["Arrival", "OCR and RFID", "Documents", "Damage Scan", "Admitted"]
OUT_STEPS = ["Arrival", "OCR and RFID", "Seal Check", "Documents", "Released"]
EARLY_MINUTES = 30   # earliest a truck may arrive before its slot starts
LATE_MINUTES = 60    # latest a truck may arrive after its slot ends
SUPERVISOR_ROLES = {"Gate Supervisor", "Terminal Admin", "System Manager"}
IN_MOVES = ("Export Drop", "Empty Return")


class GateTransaction(Document):
    # ---------- creation ----------
    def before_insert(self):
        lane = frappe.get_doc("Gate Lane", self.lane)
        if lane.status != "Open":
            frappe.throw(_("Lane {0} is {1}.").format(lane.name, lane.status))
        self.terminal, self.direction = lane.terminal, lane.direction
        for step in (IN_STEPS if lane.direction == "In" else OUT_STEPS):
            self.append("checks", {"step": step, "result": "Pending"})
        self.current_step = 0
        self.status = "Processing"
        self.entered_at = now_datetime()

    def validate(self):
        if self.container_no:
            self.container_no = normalise_no(self.container_no)
        if self.is_new():
            self.check_authorisation()
            self.check_direction_and_container()

    def check_authorisation(self):
        term = frappe.get_cached_doc("Terminal", self.terminal)
        carrier = frappe.get_doc("Carrier", self.carrier)
        if carrier.is_blocked:
            frappe.throw(_("Carrier {0} is blocked: {1}").format(carrier.name, carrier.block_reason or ""))
        truck = frappe.get_doc("Truck", self.truck)
        if truck.is_blocked:
            frappe.throw(_("Truck {0} is blocked: {1}").format(truck.name, truck.block_reason or ""))
        if truck.carrier != self.carrier:
            frappe.throw(_("Truck {0} belongs to {1}, not {2}.").format(truck.name, truck.carrier, self.carrier))
        frappe.get_doc("Driver", self.driver).assert_can_work()   # never overridable

        needs = []
        appt = None
        if self.appointment:
            appt = frappe.get_doc("Appointment", self.appointment)
            if appt.status not in ("Booked", "Late"):
                frappe.throw(_("Appointment {0} is {1}.").format(appt.name, appt.status))
            if appt.direction != self.direction:
                frappe.throw(_("Appointment {0} is for Gate {1}, but this is a Gate {2} lane.").format(appt.name, appt.direction, self.direction))
            if (appt.carrier, appt.truck, appt.driver) != (self.carrier, self.truck, self.driver):
                needs.append("Details Changed")
            start, end = slot_window(frappe.get_cached_doc("Slot Capacity", appt.slot))
            now = now_datetime()
            if now < add_to_date(start, minutes=-EARLY_MINUTES) or now > add_to_date(end, minutes=LATE_MINUTES):
                needs.append("Outside Slot Window")
            self.move_type = appt.move_type
            self.container = self.container or appt.container
            self.booking_ref = self.booking_ref or appt.booking_ref
        elif term.require_appointment:
            needs.append("No Appointment")

        if len(needs) > 1:
            frappe.throw(_("This visit needs more than one override ({0}). Ask a supervisor to approve a new appointment instead.").format(", ".join(needs)))
        if needs:
            o = get_valid_override(self.override, needs, self.terminal, self.carrier, self.truck,
                                   appointment=self.appointment)
            self.flags.override_to_use = o.name
        elif self.override:
            frappe.throw(_("An override was given but this visit does not need one."))

    def check_direction_and_container(self):
        if (self.move_type in IN_MOVES) != (self.direction == "In"):
            frappe.throw(_("{0} cannot be done in a Gate {1} lane.").format(self.move_type, self.direction))
        if self.container:
            c = frappe.get_doc("Container", self.container)
            if self.direction == "Out":
                if c.status != "On Terminal":
                    frappe.throw(_("{0} is not on the terminal.").format(c.name))
                if c.is_on_hold:
                    frappe.throw(_("{0} is on hold. A supervisor must release the hold first.").format(c.name))
            self.container_type = self.container_type or c.container_type
            if not frappe.get_doc("Truck", self.truck).can_carry(c.length_ft or 40):
                frappe.throw(_("Truck {0} cannot carry a {1} ft container.").format(self.truck, c.length_ft))
        elif self.direction == "Out":
            frappe.throw(_("A container is required for Gate Out."))
        if self.move_type == "Export Drop" and not self.booking_ref:
            frappe.throw(_("Booking reference is required for an Export Drop."))

    def after_insert(self):
        frappe.db.set_value("Gate Lane", self.lane, {"status": "Busy", "current_transaction": self.name})
        if self.appointment:
            frappe.db.set_value("Appointment", self.appointment, {"status": "Arrived", "arrived_at": now_datetime()})
            publish("appointment_status", {"appointment": self.appointment, "status": "Arrived"}, self.terminal)
        if self.flags.get("override_to_use"):
            mark_used(self.flags.override_to_use, "Gate Transaction", self.name)
        self.announce()

    def on_trash(self):
        frappe.throw(_("Gate transactions are part of the audit trail. Reject the transaction instead."))

    def announce(self):
        publish("gate_status", {"lane": self.lane, "transaction": self.name, "status": self.status, "step": self.current_step}, self.terminal)

    # ---------- helpers ----------
    def _guard(self, *allowed):
        if self.status not in allowed:
            frappe.throw(_("Transaction {0} is {1}. Allowed: {2}.").format(self.name, self.status, ", ".join(allowed)))

    def _need_supervisor(self):
        if not SUPERVISOR_ROLES.intersection(frappe.get_roles()):
            frappe.throw(_("A Gate Supervisor is required for this."))

    def _stamp(self, row, result, remarks=None):
        row.result = result
        row.checked_by = frappe.session.user
        row.checked_on = now_datetime()
        if remarks:
            row.remarks = remarks

    def _check_step_ready(self, step):
        if step == "OCR and RFID":
            if self.direction == "Out" and not self.container:
                frappe.throw(_("Choose the container before this step."))
            if self.direction == "In" and not (self.container or self.container_no):
                frappe.throw(_("Enter or scan the container number first."))
            if self.ocr_container_no:
                expected = self.container or self.container_no
                if expected and normalise_no(self.ocr_container_no) != normalise_no(expected):
                    frappe.throw(_("The portal read {0} but the visit says {1}. A supervisor can waive this step.").format(self.ocr_container_no, expected))
        if step == "Damage Scan" and self.damage_found and not self.damage_notes:
            frappe.throw(_("Describe the damage before passing this step."))
        if step == "Seal Check" and not self.seal_intact:
            frappe.throw(_("The seal is not intact. Fail the step or ask a supervisor to waive it."))
        if step in ("Damage Scan", "Admitted") and self.direction == "In":
            if not self.container and not (self.container_no and self.container_type):
                frappe.throw(_("A new container needs its number and type before it can be admitted."))

    # ---------- actions ----------
    @frappe.whitelist()
    def record_ocr(self, container_no, confidence=None):
        """Called by the portal integration or a clerk."""
        self._guard("Processing", "On Hold")
        self.ocr_container_no = normalise_no(container_no)
        self.ocr_confidence = confidence
        if self.direction == "In" and not self.container and not self.container_no:
            self.container_no = self.ocr_container_no
        self.save()
        expected = self.container or self.container_no
        if expected and self.ocr_container_no != normalise_no(expected) and self.status == "Processing":
            self.hold(_("OCR read {0}, expected {1}").format(self.ocr_container_no, expected))
        else:
            self.announce()

    @frappe.whitelist()
    def advance(self, remarks=None):
        self._guard("Processing")
        row = self.checks[self.current_step]
        self._check_step_ready(row.step)
        self._stamp(row, "Passed", remarks)
        if self.current_step >= len(self.checks) - 1:
            self.status = "Cleared"
            self.cleared_at = now_datetime()
        else:
            self.current_step += 1
        self.save()
        publish("gate_step", {"transaction": self.name, "lane": self.lane, "step": row.step, "result": "Passed"}, self.terminal)
        self.announce()

    @frappe.whitelist()
    def fail_step(self, remarks):
        self._guard("Processing")
        if not (remarks or "").strip():
            frappe.throw(_("Say why the step failed."))
        row = self.checks[self.current_step]
        self._stamp(row, "Failed", remarks)
        self.status = "On Hold"
        self.hold_reason = remarks
        self.save()
        publish("gate_step", {"transaction": self.name, "lane": self.lane, "step": row.step, "result": "Failed"}, self.terminal)
        self.announce()

    @frappe.whitelist()
    def hold(self, reason):
        self._guard("Processing")
        if not (reason or "").strip():
            frappe.throw(_("Give a reason for the hold."))
        self.status = "On Hold"
        self.hold_reason = reason
        self.save()
        self.add_comment("Info", _("Held by {0}: {1}").format(frappe.session.user, reason))
        self.announce()

    @frappe.whitelist()
    def release_hold(self, note):
        self._need_supervisor()
        self._guard("On Hold")
        if not (note or "").strip():
            frappe.throw(_("A release note is required."))
        row = self.checks[self.current_step]
        if row.result == "Failed":
            row.result = "Pending"
        self.status = "Processing"
        self.hold_reason = None
        self.save()
        self.add_comment("Info", _("Hold released by {0}: {1}").format(frappe.session.user, note))
        self.announce()

    @frappe.whitelist()
    def waive_step(self, note):
        """A supervisor lets the truck past a step that failed or cannot be checked. Recorded on the step."""
        self._need_supervisor()
        self._guard("Processing", "On Hold")
        if not (note or "").strip():
            frappe.throw(_("A reason is required to waive a step."))
        row = self.checks[self.current_step]
        self._stamp(row, "Waived", note)
        self.status = "Processing"
        self.hold_reason = None
        if self.current_step >= len(self.checks) - 1:
            self.status = "Cleared"
            self.cleared_at = now_datetime()
        else:
            self.current_step += 1
        self.save()
        self.add_comment("Info", _("Step '{0}' waived by {1}: {2}").format(row.step, frappe.session.user, note))
        self.announce()

    @frappe.whitelist()
    def reject(self, reason):
        self._guard("Processing", "On Hold")
        if not (reason or "").strip():
            frappe.throw(_("Give a reason for turning the truck away."))
        self.status = "Rejected"
        self.hold_reason = reason
        self.exited_at = now_datetime()
        self.save()
        self._free_lane()
        if self.appointment:
            # the appointment stays Booked so the carrier can come back inside its slot
            frappe.db.set_value("Appointment", self.appointment, "status", "Booked")
        self.add_comment("Info", _("Rejected by {0}: {1}").format(frappe.session.user, reason))
        self.announce()

    @frappe.whitelist()
    def complete(self):
        self._guard("Cleared")
        container = self._admit() if self.direction == "In" else self._release()
        self.container = container
        self.status = "Completed"
        self.exited_at = now_datetime()
        self.turn_minutes = int(time_diff_in_seconds(self.exited_at, self.entered_at) // 60)
        self.save()
        self._free_lane()
        if self.appointment:
            frappe.db.set_value("Appointment", self.appointment, {"status": "Completed", "completed_at": self.exited_at})
            publish("appointment_status", {"appointment": self.appointment, "status": "Completed"}, self.terminal)
        self.announce()

    def _admit(self):
        if self.container:
            c = frappe.get_doc("Container", self.container)
            if c.status == "On Terminal":
                frappe.throw(_("{0} is already on the terminal.").format(c.name))
        else:
            if not (self.container_no and self.container_type):
                frappe.throw(_("A new container needs its number and type."))
            c = frappe.get_doc({
                "doctype": "Container", "container_no": self.container_no, "terminal": self.terminal,
                "container_type": self.container_type, "shipping_line": self.shipping_line,
                "cargo_status": "Export" if self.move_type == "Export Drop" else "Empty",
            })
            c.insert(ignore_permissions=True)
        c.status = "On Terminal"
        c.arrived_on = now_datetime()
        c.terminal = self.terminal
        c.booking_ref = self.booking_ref or c.booking_ref
        c.seal_no = self.seal_no or c.seal_no
        c.gross_weight_kg = self.gross_weight_kg or c.gross_weight_kg
        c.save(ignore_permissions=True)
        yard.log_movement(c, "Gate In", to_stack=None, source_doctype="Gate Transaction", source_name=self.name)
        return c.name

    def _release(self):
        c = frappe.get_doc("Container", self.container)
        if c.is_on_hold:
            frappe.throw(_("{0} is on hold.").format(c.name))
        yard.move_container(c.name, None, "Gate Out", "Gate Transaction", self.name)
        frappe.db.set_value("Container", c.name, "status", "Gated Out")
        return c.name

    def _free_lane(self):
        frappe.db.set_value("Gate Lane", self.lane, {"status": "Open", "current_transaction": None})
