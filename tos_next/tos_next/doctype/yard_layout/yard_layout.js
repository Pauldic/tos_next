frappe.ui.form.on("Yard Layout", {
	refresh(frm) {
		const draft = frm.doc.status === "Draft" && !frm.is_new();
		if (draft && frappe.user_roles.some((r) => ["Terminal Admin", "System Manager"].includes(r))) {
			frm.add_custom_button(__("Publish"), () => {
				frappe.confirm(
					__("Publish this layout? It replaces the live yard layout for {0}. The previous layout is kept as Archived.", [frm.doc.terminal]),
					() => frm.call("publish").then(() => frm.reload_doc())
				);
			}).addClass("btn-primary");
		}
		if (frm.doc.status !== "Draft") {
			frm.dashboard.set_headline(__("{0} layouts cannot be edited. Create a draft from the layouts list to make changes.", [__(frm.doc.status)]));
		}
	},
});
