frappe.ui.form.on("Move Order", {
	refresh(frm) {
		if (frm.is_new()) return;
		const run = (method, args) => frm.call({ doc: frm.doc, method, args: args || {}, freeze: true }).then(() => frm.reload_doc());
		const s = frm.doc.status;

		if (["Queued", "Assigned"].includes(s)) {
			frm.add_custom_button(__("Assign"), () => {
				frappe.prompt([
					{ fieldname: "equipment", fieldtype: "Link", options: "Equipment", label: __("Equipment"), reqd: 1,
					  get_query: () => ({ filters: { terminal: frm.doc.terminal, status: ["in", ["Available", "Working"]] } }) },
					{ fieldname: "assigned_to", fieldtype: "Link", options: "User", label: __("Operator") },
				], (v) => run("assign", v), __("Assign equipment"), __("Assign"));
			});
		}
		if (s === "Assigned") frm.add_custom_button(__("Start"), () => run("start")).addClass("btn-primary");
		if (s === "In Progress") frm.add_custom_button(__("Complete"), () => run("complete")).addClass("btn-primary");
		if (["Queued", "Assigned", "In Progress"].includes(s)) {
			frm.add_custom_button(__("Cancel Order"), () => {
				frappe.prompt([{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
					(v) => run("cancel_order", v), __("Cancel this order"), __("Cancel Order"));
			}, __("More"));
		}
		if (frm.doc.container && !["Completed", "Cancelled"].includes(s)) {
			frm.add_custom_button(__("Clear Containers Above"), () => {
				frappe.call({ method: "tos_next.tos_next.doctype.move_order.move_order.create_reshuffle_orders", args: { container: frm.doc.container }, freeze: true })
					.then((r) => frappe.msgprint(__("Created: {0}", [(r.message || []).join(", ") || __("nothing to clear")])));
			}, __("More"));
		}
	},

	container(frm) {
		if (!frm.doc.container || !frm.is_new()) return;
		frappe.call({ method: "tos_next.tos_next.doctype.move_order.move_order.suggest_target", args: { container: frm.doc.container } })
			.then((r) => { if (r.message && !frm.doc.to_stack) frm.set_value("to_stack", r.message); });
	},
});
