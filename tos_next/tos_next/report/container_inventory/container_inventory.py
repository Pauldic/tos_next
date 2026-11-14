# Copyright (c) 2026, TOS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from tos_next import inventory


def execute(filters=None):
    return columns(), inventory.rows(filters or {}, (filters or {}).get("search"), limit=5000)


def columns():
    def col(fieldname, label, fieldtype="Data", width=110, options=None):
        c = {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}
        if options:
            c["options"] = options
        return c

    return [
        col("name", "Container Number", "Link", 130, "Container"), col("dwell_days", "Dwell Days", "Int", 80), col("container_type", "ISO/Spec", "Link", 80, "Container Type"),
        col("category", "Category", width=100), col("full_empty", "F/E", width=60), col("transit_state", "Transit State", width=110), col("position", "Position", width=110),
        col("reefer_temp", "Reefer / Temp", width=100), col("imdg_summary", "Hazard (IMDG)", width=100), col("seal_verified", "Seal Verified", "Check", 90),
        col("bill_of_lading", "B/L Reference", width=120), col("shipping_line", "Carrier Line", "Link", 100, "Shipping Line"), col("arrived_on", "Time In", "Datetime", 150),
        col("ib_vessel_id", "IB Vessel ID", width=100), col("ib_vessel_name", "IB Vessel", width=140), col("ib_vessel_voyage", "IB Voyage", width=90), col("ib_vessel_class", "IB Class", width=90),
        col("ob_vessel_id", "OB Vessel ID", width=100), col("ob_vessel_name", "OB Vessel", width=140), col("ob_vessel_voyage", "OB Voyage", width=90), col("ob_vessel_class", "OB Class", width=90),
        col("group_code", "Group Code", width=90),
        col("special_stow_1", "Stow 1", width=70), col("special_stow_2", "Stow 2", width=70), col("special_stow_3", "Stow 3", width=70), col("special_stow_4", "Stow 4", width=70), col("special_stow_5", "Stow 5", width=70),
        col("planned_position", "Planned Position", width=110), col("destination", "Destination", width=110), col("pol", "POL", width=80), col("pod", "POD", width=80),
        col("place_of_delivery", "Place of Delivery", width=130), col("line", "Line", "Link", 90, "Shipping Line"), col("terminal_line", "Terminal Line", "Link", 100, "Shipping Line"),
        col("consignee", "Consignee", width=130), col("is_hazmat", "Hazmat", "Check", 70), col("is_on_hold", "On Hold", "Check", 70), col("storage_paid_date", "Storage Paid", "Date", 100),
        col("reefer_storage_paid", "Reefer Storage Paid", "Date", 120), col("line_storage_paid", "Line Storage Paid", "Date", 120), col("remarks", "Remarks", width=200),
        col("status", "Status", width=100), col("terminal", "Terminal", "Link", 90, "Terminal"),
    ]
