// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.ui.form.on("Venue", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Venue Grid"), () => {
			frappe.set_route("venue-grid");
		}, __("References"));

		frm.add_custom_button(__("View Timetable"), () => {
			frappe.route_options = { venue: frm.doc.name };
			frappe.set_route("tvms-timetable");
		}, __("References"));
	},
});
