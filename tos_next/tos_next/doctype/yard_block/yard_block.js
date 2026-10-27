frappe.ui.form.on("Yard Block", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Generate Stacks"), () => {
			frappe.confirm(__("Create a stack for every bay and row that does not have one yet?"), () => {
				frm.call({ doc: frm.doc, method: "generate_stacks", freeze: true }).then(() => frm.reload_doc());
			});
		}).addClass("btn-primary");
	},
});
