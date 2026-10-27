frappe.ui.form.on("Gate Transaction", {
	refresh(frm) {
		if (frm.is_new()) return;
		const run = (method, args) => frm.call({ doc: frm.doc, method, args: args || {}, freeze: true }).then(() => frm.reload_doc());
		const ask = (label, method, field, title) => frappe.prompt(
			[{ fieldname: field, fieldtype: "Small Text", label: __(label), reqd: 1 }], (v) => run(method, v), __(title), __(title));
		const s = frm.doc.status;
		const step = (frm.doc.checks || [])[frm.doc.current_step];

		if (s === "Processing") {
			frm.add_custom_button(__("Advance: {0}", [step ? __(step.step) : ""]), () => run("advance")).addClass("btn-primary");
			frm.add_custom_button(__("Fail This Step"), () => ask("What failed?", "fail_step", "remarks", "Fail this step"), __("More"));
			frm.add_custom_button(__("Hold"), () => ask("Reason", "hold", "reason", "Hold the truck"), __("More"));
		}
		if (["Processing", "On Hold"].includes(s)) {
			frm.add_custom_button(__("Record OCR Read"), () => {
				frappe.prompt([
					{ fieldname: "container_no", fieldtype: "Data", label: __("Container number"), reqd: 1 },
					{ fieldname: "confidence", fieldtype: "Percent", label: __("Confidence") },
				], (v) => run("record_ocr", v), __("Portal read"), __("Save"));
			}, __("More"));
			frm.add_custom_button(__("Waive Step"), () => ask("Why is it safe to waive?", "waive_step", "note", "Waive this step"), __("Supervisor"));
			frm.add_custom_button(__("Turn Truck Away"), () => ask("Reason", "reject", "reason", "Turn the truck away"), __("Supervisor"));
		}
		if (s === "On Hold") frm.add_custom_button(__("Release Hold"), () => ask("Release note", "release_hold", "note", "Release the hold"), __("Supervisor")).addClass("btn-primary");
		if (s === "Cleared") frm.add_custom_button(__("Complete and Let Truck Through"), () => run("complete")).addClass("btn-primary");

		const colour = { Processing: "blue", "On Hold": "orange", Cleared: "green", Completed: "gray", Rejected: "red" }[s];
		if (colour) frm.page.set_indicator(__(s), colour);
	},
});
