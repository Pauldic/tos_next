frappe.query_reports["Container Inventory"] = {
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "position" && data && data.position) {
			return `<a href="/tos/yard?container=${encodeURIComponent(data.name)}" title="${__("Show in the 3D yard")}">${frappe.utils.escape_html(data.position)}</a>`;
		}
		return value;
	},
	filters: [
		{ fieldname: "terminal", label: __("Terminal"), fieldtype: "Link", options: "Terminal" },
		{ fieldname: "search", label: __("Search"), fieldtype: "Data" },
		{ fieldname: "transit_state", label: __("Transit State"), fieldtype: "Select", options: "\nExpected\nAwaiting Slot\nYard\nOn Vessel\nGated Out" },
		{ fieldname: "category", label: __("Category"), fieldtype: "Select", options: "\nImport\nExport\nTransshipment\nStorage" },
		{ fieldname: "full_empty", label: __("F/E"), fieldtype: "Select", options: "\nFCL\nLCL\nMT" },
		{ fieldname: "shipping_line", label: __("Carrier Line"), fieldtype: "Link", options: "Shipping Line" },
		{ fieldname: "is_hazmat", label: __("Hazmat only"), fieldtype: "Check" },
		{ fieldname: "is_reefer", label: __("Reefers only"), fieldtype: "Check" },
		{ fieldname: "is_on_hold", label: __("On hold only"), fieldtype: "Check" },
	],
};
