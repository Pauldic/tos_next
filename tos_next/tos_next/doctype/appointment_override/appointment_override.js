frappe.ui.form.on("Appointment Override", {
	refresh(frm) {
		if (frm.is_new()) return;
		const decide = (method, title) => frappe.prompt(
			[{ fieldname: "note", fieldtype: "Small Text", label: __("Decision note"), reqd: 1 }],
			(v) => frm.call({ doc: frm.doc, method, args: v, freeze: true }).then(() => frm.reload_doc()), title, __(title));
		if (frm.doc.status === "Pending") {
			frm.add_custom_button(__("Approve"), () => decide("approve", __("Approve")), __("Decision")).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => decide("reject", __("Reject")), __("Decision"));
		}
		const colour = { Pending: "orange", Approved: "green", Rejected: "red", Used: "gray", Expired: "gray" }[frm.doc.status];
		if (colour) frm.page.set_indicator(__(frm.doc.status), colour);
		if (["Rejected", "Used", "Expired"].includes(frm.doc.status)) frm.disable_form();
	},
});
