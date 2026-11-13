"""Gives every terminal that has active blocks a first published yard layout, set out the way the 3D yard used to
set blocks out by itself, so the view does not change on the day this is installed."""
import frappe

from tos_next import layout as yard_layout


def execute():
    g = yard_layout.geometry()
    for terminal in frappe.get_all("Terminal", pluck="name"):
        if frappe.db.exists("Yard Layout", {"terminal": terminal, "status": "Published"}):
            continue
        blocks = yard_layout.active_blocks(terminal)
        if not blocks:
            continue
        doc = frappe.get_doc({
            "doctype": "Yard Layout", "terminal": terminal, "layout_name": "Original layout", "status": "Published", "version": 1,
            "items": yard_layout.auto_items(blocks, g),
        })
        doc.flags.allow_publish_write = True
        doc.insert(ignore_permissions=True)
