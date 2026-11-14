frappe.listview_settings["Container"] = {
	add_fields: ["transit_state", "is_hazmat", "is_reefer", "is_on_hold"],
	get_indicator(doc) {
		if (doc.is_on_hold) return [__("On Hold"), "red", "is_on_hold,=,1"];
		const colours = { Expected: "gray", "Awaiting Slot": "orange", Yard: "green", "On Vessel": "blue", "Gated Out": "gray" };
		return [__(doc.transit_state || doc.status), colours[doc.transit_state] || "gray", "transit_state,=," + doc.transit_state];
	},
};
