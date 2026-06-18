// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.ui.form.on("Venue", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Venue Dashboard"), () => {
			frappe.set_route("venue-dashboard");
		}, __("References"));

		frm.add_custom_button(__("View Timetable"), () => {
			frappe.route_options = { venue: frm.doc.name };
			frappe.set_route("tvms-timetable");
		}, __("References"));
	},

	refresh(frm) {
		// "View on Map" button — only if GPS coordinates are set
		if (frm.doc.latitude && frm.doc.longitude && !frm.is_new()) {
			frm.add_custom_button(__("View on Map"), () => {
				frappe.set_route("venue-map");
			}, __("Location"));
 
			frm.add_custom_button(__("Get Directions"), () => {
				const url = `https://www.google.com/maps/dir/?api=1`
				          + `&destination=${frm.doc.latitude},${frm.doc.longitude}`
				          + `&travelmode=walking`;
				window.open(url, "_blank");
			}, __("Location"));
		}
 
		// Show a small status indicator in the form sidebar
		if (frm.doc.latitude && frm.doc.longitude) {
			frm.dashboard.add_indicator(__("GPS coordinates set"), "green");
		} else if (!frm.is_new()) {
			frm.dashboard.add_indicator(__("No GPS coordinates"), "grey");
		}
	},
});
