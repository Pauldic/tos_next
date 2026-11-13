# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from tos_next import layout as yard_layout
from tos_next.realtime import publish

DESIGNERS = ["Terminal Admin", "Yard Planner", "System Manager"]
PUBLISHERS = ["Terminal Admin", "System Manager"]
POLYGON_MIN = {"Polygon": 3, "Polyline": 2}
NEEDS_SIZE = {"Heap", "Road", "Ground", "Building", "Gate", "Car Park", "Truck Park", "Crane", "Weighbridge"}


class YardLayout(Document):
	def validate(self):
		before = self.get_doc_before_save()
		system = self.flags.allow_publish_write
		if self.is_new() and self.status != "Draft" and not system:
			frappe.throw(_("A new layout starts as a Draft."))
		if before and not system:
			if before.status != "Draft":
				frappe.throw(_("A {0} layout cannot be changed. Create a draft from it instead.").format(before.status.lower()))
			if before.status != self.status:
				frappe.throw(_("Use Publish to publish a draft."))
		if self.status == "Archived":
			return
		self.check_items()
		if self.status == "Draft":
			self.one_draft()

	def one_draft(self):
		other = frappe.db.get_value("Yard Layout", {"terminal": self.terminal, "status": "Draft", "name": ["!=", self.name]}, "name")
		if other:
			frappe.throw(_("{0} is already a draft for this terminal. Publish or delete it first.").format(other))

	def check_items(self):
		seen = set()
		for r in self.items:
			where = _("Row {0}").format(r.idx)
			if r.item_type == "Block":
				if not r.yard_block:
					frappe.throw(_("{0}: choose the yard block.").format(where))
				if frappe.db.get_value("Yard Block", r.yard_block, "terminal") != self.terminal:
					frappe.throw(_("{0}: block {1} belongs to another terminal.").format(where, r.yard_block))
				if r.yard_block in seen:
					frappe.throw(_("{0}: block {1} is placed twice.").format(where, r.yard_block))
				seen.add(r.yard_block)
				r.shape = "Rectangle"
				continue
			r.yard_block = None
			if r.shape in POLYGON_MIN:
				try:
					pts = yard_layout.parse_points(r.points)
				except ValueError as e:
					frappe.throw(f"{where}: {e}")
				if len(pts) < POLYGON_MIN[r.shape]:
					frappe.throw(_("{0}: a {1} needs at least {2} points.").format(where, r.shape.lower(), POLYGON_MIN[r.shape]))
			elif r.item_type in NEEDS_SIZE and not ((r.length or 0) > 0 and (r.width or 0) > 0):
				frappe.throw(_("{0}: give the {1} a length and a width.").format(where, r.item_type.lower()))
			if r.item_type == "Label" and not r.label:
				frappe.throw(_("{0}: a label needs its text.").format(where))

	def on_trash(self):
		if self.status != "Draft" and not self.flags.allow_publish_write:
			frappe.throw(_("Published and archived layouts are kept as a record. Only a draft can be deleted."))

	@frappe.whitelist()
	def publish(self):
		"""Make this draft the live layout. The previous live layout is kept as Archived."""
		frappe.only_for(PUBLISHERS)
		if self.status != "Draft":
			frappe.throw(_("Only a draft can be published."))
		self.check_items()
		problems = yard_layout.publish_problems(self)
		if problems:
			frappe.throw("<br>".join(problems), title=_("This layout cannot be published yet"))
		old = yard_layout.published(self.terminal)
		if old:
			old.flags.allow_publish_write = True
			old.status = "Archived"
			old.save(ignore_permissions=True)
		latest = frappe.get_all("Yard Layout", filters={"terminal": self.terminal}, pluck="version", order_by="version desc", limit=1)
		top = latest[0] if latest else 0
		self.flags.allow_publish_write = True
		self.status = "Published"
		self.version = int(top) + 1
		self.published_by = frappe.session.user
		self.published_on = now_datetime()
		self.save(ignore_permissions=True)
		publish("layout_published", {"layout": self.name, "version": self.version}, self.terminal)
		return self.name
