
frappe.ui.form.on("Emergency session", {
	refresh(frm) {
		frm.clear_custom_buttons();
		_set_status_color(frm);
		_show_postponed_banner(frm);
 
		// Venue finder button on new/editing forms
		if (frm.doc.start_time && frm.doc.end_time && frm.doc.course) {
			frm.add_custom_button(__("Find Best Venue"), () => _find_venue(frm), __("Venue"));
		}
 
		if (frm.is_new()) return;
 
		const status = frm.doc.status;
 
		if (status === "PENDING") {
			frm.add_custom_button(__("Confirm"),  () => _confirm(frm),  __("Actions"));
			frm.add_custom_button(__("Postpone"), () => _postpone(frm), __("Actions"));
			frm.add_custom_button(__("Cancel Session"), () => _cancel(frm), __("Actions"));
		}
 
		if (status === "CONFIRMED") {
			frm.add_custom_button(__("Complete"), () => _complete(frm), __("Actions"));
			frm.add_custom_button(__("Postpone"), () => _postpone(frm), __("Actions"));
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
 
// FR-32 — Postpone a session to a new time slot
function _postpone(frm) {
	// Build sensible defaults: +1 hour shift from current times
	const defaults = _suggest_postpone_times(frm.doc.start_time, frm.doc.end_time);
 
	const d = new frappe.ui.Dialog({
		title: __("Postpone Session"),
		fields: [
			{
				fieldtype: "HTML",
				options: `
					<div style="background:#FAEEDA;padding:10px 14px;border-radius:6px;font-size:13px;color:#633806;margin-bottom:8px;">
						<i class="fa fa-info-circle" style="margin-right:6px;"></i>
						${__("Choose a new time slot. The status will stay <strong>{0}</strong>; only the time changes. Recipients will be notified.", [frm.doc.status])}
					</div>
				`,
			},
			{
				fieldname: "current_window",
				fieldtype: "HTML",
				options: `
					<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
						${__("Current slot")}: <strong>${_fmt_dt(frm.doc.start_time)} → ${_fmt_dt(frm.doc.end_time)}</strong>
					</div>
				`,
			},
			{ fieldtype: "Section Break", label: __("New time slot") },
			{
				fieldname:    "new_start_time",
				fieldtype:    "Datetime",
				label:        __("New start time"),
				reqd:         1,
				default:      defaults.new_start,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname:    "new_end_time",
				fieldtype:    "Datetime",
				label:        __("New end time"),
				reqd:         1,
				default:      defaults.new_end,
			},
			{ fieldtype: "Section Break" },
			{
				fieldname:    "reason",
				fieldtype:    "Small Text",
				label:        __("Reason for postponement"),
				description:  __("Shown to lecturers, CRs, and students in the notification."),
			},
		],
		primary_action_label: __("Postpone"),
		primary_action(values) {
			d.set_primary_action(__("Postponing..."), null);
			frm.call("postpone_session", {
				new_start_time: values.new_start_time,
				new_end_time:   values.new_end_time,
				reason:         values.reason || null,
			})
				.then(r => {
					if (r.message) {
						frappe.show_alert({
							message: __("Session postponed to {0}", [_fmt_dt(values.new_start_time)]),
							indicator: "blue",
						});
						d.hide();
						frm.reload_doc();
					}
				})
				.catch(() => {
					// Conflict error already shown by Frappe's server error dialog.
					// Restore the primary action so the user can adjust and retry.
					d.set_primary_action(__("Postpone"), () => d.get_primary_btn().trigger("click"));
				});
		},
	});
 
	d.show();
}
 
function _suggest_postpone_times(current_start, current_end) {
	// Default suggestion: shift the same window forward by 1 day at the same time of day.
	// This is the most common postpone case ("today at 2pm → tomorrow at 2pm").
	if (!current_start || !current_end) {
		return { new_start: null, new_end: null };
	}
	const start = frappe.datetime.str_to_obj(current_start);
	const end   = frappe.datetime.str_to_obj(current_end);
	start.setDate(start.getDate() + 1);
	end.setDate(end.getDate() + 1);
	return {
		new_start: frappe.datetime.obj_to_str(start),
		new_end:   frappe.datetime.obj_to_str(end),
	};
}
 
function _fmt_dt(value) {
	if (!value) return "—";
	return frappe.datetime.str_to_user(value).replace(/:\d{2}$/, "");
}
 
function _show_postponed_banner(frm) {
	if (!frm.doc.postponed) return;
	if (!frm.doc.original_start_time) return;
 
	const original = _fmt_dt(frm.doc.original_start_time);
	const current  = _fmt_dt(frm.doc.start_time);
	const reason   = frappe.utils.escape_html(frm.doc.postpone_reason || __("(no reason supplied)"));
 
	frm.dashboard.clear_headline();
	frm.dashboard.set_headline_alert(
		`<div style="font-size:13px;">
			<i class="fa fa-clock-o" style="margin-right:6px;"></i>
			<strong>${__("Postponed")}.</strong>
			${__("Originally scheduled for {0}, now {1}.", [original, current])}
			<span style="color:var(--text-muted);">— ${__("Reason")}: ${reason}</span>
		</div>`,
		"orange",
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