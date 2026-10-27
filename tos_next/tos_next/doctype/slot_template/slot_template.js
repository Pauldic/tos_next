frappe.ui.form.on("Slot Template", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Generate Slots"), () => {
			frappe.prompt([{ fieldname: "days_ahead", fieldtype: "Int", label: __("Days ahead"), default: 14, reqd: 1 }],
				(v) => frm.call({ doc: frm.doc, method: "generate", args: v, freeze: true }), __("Generate slots"), __("Generate"));
		}).addClass("btn-primary");
	},
});
