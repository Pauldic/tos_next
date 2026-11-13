frappe.listview_settings["Yard Layout"] = {
	add_fields: ["status", "version"],
	get_indicator(doc) {
		const colours = { Draft: "orange", Published: "green", Archived: "gray" };
		return [__(doc.status), colours[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(list) {
		list.page.add_inner_button(__("Create Draft"), () => {
			frappe.prompt(
				{ fieldname: "terminal", fieldtype: "Link", options: "Terminal", label: __("Terminal"), reqd: 1 },
				(v) => frappe.call({ method: "tos_next.api_layout.create_draft", args: { terminal: v.terminal } }).then((r) => frappe.set_route("Form", "Yard Layout", r.message)),
				__("Create a draft layout")
			);
		});
	},
};
