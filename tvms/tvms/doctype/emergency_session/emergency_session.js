// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.ui.form.on("Emergency session", {
	refresh(frm) {
		frm.clear_custom_buttons();
		_set_status_color(frm);

		// Venue finder button on new/editing forms
		if (frm.doc.start_time && frm.doc.end_time && frm.doc.course) {
			frm.add_custom_button(__("Find Best Venue"), () => _find_venue(frm), __("Venue"));
		}

		if (frm.is_new()) return;

		const status = frm.doc.status;

		if (status === "PENDING") {
			frm.add_custom_button(__("Confirm"), () => _confirm(frm), __("Actions"));
			frm.add_custom_button(__("Cancel Session"), () => _cancel(frm), __("Actions"));
		}

		if (status === "CONFIRMED") {
			frm.add_custom_button(__("Complete"), () => _complete(frm), __("Actions"));
			frm.add_custom_button(__("Cancel Session"), () => _cancel(frm), __("Actions"));
		}
	},

	// Auto-fill expected_students from course
	course(frm) {
		if (frm.doc.course) {
			frappe.call({
				method: "frappe.client.get",
				args: { doctype: "Course", name: frm.doc.course },
				callback: (r) => {
					if (r.message?.expected_students) {
						frm.set_value("expected_students", r.message.expected_students);
					}
				}
			});
		}
	},
});

function _confirm(frm) {
	frappe.confirm(
		__("Confirm this session? The venue will be marked IN-USE."),
		() => {
			frm.call("confirm_session")
				.then(r => {
					if (r.message) {
						frappe.show_alert({ message: __("Session confirmed"), indicator: "green" });
						frm.reload_doc();
					}
				})
				.catch(() => frm.reload_doc());
		}
	);
}

function _cancel(frm) {
	frappe.confirm(
		__("Cancel this session? The venue will be released."),
		() => {
			frm.call("cancel_session")
				.then(() => {
					frappe.show_alert({ message: __("Session cancelled"), indicator: "orange" });
					frm.reload_doc();
				})
				.catch(() => frm.reload_doc());
		}
	);
}

function _complete(frm) {
	frappe.confirm(
		__("Mark this session as completed?"),
		() => {
			frm.call("complete_session")
				.then(r => {
					if (r.message) {
						frappe.show_alert({ message: __("Session completed"), indicator: "blue" });
						frm.reload_doc();
					}
				})
				.catch(() => frm.reload_doc());
		}
	);
}

function _find_venue(frm) {
	const expected = frm.doc.expected_students || 30;
	const start_time = frm.doc.start_time;
	const end_time = frm.doc.end_time;

	if (!start_time || !end_time) {
		frappe.show_alert({ message: __("Set start and end time first"), indicator: "warning" });
		return;
	}

	frappe.call({
		method: "tvms.tvms.doctype.venue.venue.recommend_venue",
		args: {
			expected_students: expected,
			start_time: start_time,
			end_time: end_time,
			required_resources: frm.doc.required_resources,
		},
		callback: (r) => {
			if (!r.message || r.message.length === 0) {
				frappe.show_alert({ message: __("No available venues for this slot"), indicator: "warning" });
				return;
			}

			const venues = r.message.slice(0, 5);
			const d = new frappe.ui.Dialog({
				title: __("Recommended Venues"),
				fields: [
					{
						fieldname: "venue",
						fieldtype: "Link",
						label: __("Select Venue"),
						options: "Venue",
						reqd: 1,
						description: venues.map(v => `${v.venue_name} (cap: ${v.capacity})`).join(", "),
					},
				],
				primary_action_label: __("Select"),
				primary_action(values) {
					frm.set_value("venue", values.venue);
					d.hide();
					frappe.show_alert({ message: __("Venue selected"), indicator: "green" });
				},
			});
			d.show();
		},
	});
}

function _set_status_color(frm) {
	const colors = {
		PENDING:   "orange",
		CONFIRMED: "green",
		CANCELLED: "red",
		COMPLETED: "blue",
		EXPIRED:   "grey",
	};
	const color = colors[frm.doc.status];
	if (color) {
		frm.page.set_indicator(__(frm.doc.status), color);
	}
}
