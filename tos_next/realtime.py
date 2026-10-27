"""Small wrapper so every event goes to the same per-terminal channel.

Clients subscribe with frappe.realtime.doc_subscribe("Terminal", "<terminal>").
Check the room mechanism against the Frappe v16 realtime docs before relying on it.
"""
import frappe


def publish(event: str, payload: dict, terminal: str):
    frappe.publish_realtime(
        event,
        payload,
        doctype="Terminal",
        docname=terminal,
        after_commit=True,
    )
