frappe.ui.form.on("Container", {
	refresh(frm) {
		const bits = [];
		const dwell = frm.doc.__onload && frm.doc.__onload.dwell_days;
		if (dwell !== undefined && dwell !== null) bits.push(__("{0} days on the terminal", [dwell]));
		if (frm.doc.is_hazmat) bits.push(__("Hazmat: IMDG {0}", [frm.doc.imdg_summary || ""]));
		if (frm.doc.is_reefer) bits.push(frm.doc.reefer_plugged ? __("Reefer, plugged in") : __("Reefer, not plugged in"));
		if (frm.doc.is_on_hold) bits.push(__("On hold"));
		if (bits.length) frm.dashboard.set_headline(bits.join(" · "));
		if (!frm.is_new()) frm.add_custom_button(__("History"), () => frappe.set_route("List", "Container Event", { container: frm.doc.name }));
		if (frm.doc.yard_stack) frm.add_custom_button(__("Show in 3D yard"), () => window.open(`/tos/yard?container=${encodeURIComponent(frm.doc.name)}`, "_blank"));
	},
});
