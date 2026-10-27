frappe.ui.form.on("Appointment", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (["Booked", "Late"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Cancel Appointment"), () => {
				frappe.prompt([{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
					(v) => frm.call({ doc: frm.doc, method: "cancel_appointment", args: v, freeze: true }).then(() => frm.reload_doc()),
					__("Cancel this appointment"), __("Cancel Appointment"));
			});
		}
		const colour = { Booked: "blue", Arrived: "green", "In Progress": "green", Completed: "gray", Late: "orange", "No-show": "red", Cancelled: "gray" }[frm.doc.status];
		if (colour) frm.page.set_indicator(__(frm.doc.status), colour);
	},
	setup(frm) {
		frm.set_query("slot", () => ({ filters: { terminal: frm.doc.terminal, is_closed: 0, slot_date: [">=", frappe.datetime.get_today()] } }));
		frm.set_query("truck", () => ({ filters: { carrier: frm.doc.carrier, is_blocked: 0 } }));
		frm.set_query("driver", () => ({ filters: { carrier: frm.doc.carrier, is_blocked: 0 } }));
	},
});
