frappe.pages["tvms-timetable"].on_page_load = function (wrapper) {
	frappe.tvms_timetable = new TVMSStaticTimetable(wrapper);
};

frappe.pages["tvms-timetable"].on_page_show = function () {
	if (frappe.tvms_timetable) {
		frappe.tvms_timetable.apply_route_options();
		frappe.tvms_timetable.load();
	}
};

class TVMSStaticTimetable {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Static Timetable"),
			single_column: true,
		});

		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.filters = {};
		this.options = {};
		this.week_start = this.get_monday(new Date());
		this.include_weekends = 0;

		this.build();
		this.load_options().then(() => {
			this.apply_route_options();
			this.load();
		});
	}

	build() {
		this.page.set_primary_action(__("Refresh"), () => this.load(), "refresh");
		this.page.add_inner_button(__("Timetable List"), () => frappe.set_route("List", "Timetable"));
		this.page.add_inner_button(__("By Program & Year"), () => frappe.set_route("tvms-program-timetable"));

		if (frappe.user.has_role(["Department Admin", "System Manager", "Administrator"])) {
			this.page.set_secondary_action(__("Add Class"), () => this._open_add_class_dialog(), "add");
		}

		this.$body = $(`
			<div class="tvms-timetable-page">
				<div class="tvms-filter-bar">
					<div class="tvms-filter-row">
						<div class="tvms-field">
							<label>${__("Week Start")}</label>
							<input type="date" data-filter="week_start" class="form-control">
						</div>
						<div class="tvms-field">
							<label>${__("Lecturer")}</label>
							<select data-filter="lecturer" class="form-control"></select>
						</div>
						<div class="tvms-field">
							<label>${__("Venue")}</label>
							<select data-filter="venue" class="form-control"></select>
						</div>
						<div class="tvms-field">
							<label>${__("Course")}</label>
							<select data-filter="course" class="form-control"></select>
						</div>
						<div class="tvms-field">
							<label>${__("Program")}</label>
							<select data-filter="program" class="form-control"></select>
						</div>
						<div class="tvms-field">
							<label>${__("Semester")}</label>
							<select data-filter="semester" class="form-control"></select>
						</div>
						<div class="tvms-field">
							<label>${__("Academic Year")}</label>
							<select data-filter="academic_year" class="form-control"></select>
						</div>
						<label class="tvms-weekend-toggle">
							<input type="checkbox" data-filter="include_weekends">
							<span>${__("Show weekend")}</span>
						</label>
						<button class="btn btn-primary btn-sm" data-action="apply">${__("Apply")}</button>
					</div>
				</div>
				<div class="tvms-summary"></div>
				<div class="tvms-grid-wrap">
					<div class="tvms-grid"></div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.inject_styles();
		this.bind_events();
		this.set_week_input();
	}

	inject_styles() {
		if ($("#tvms-static-timetable-styles").length) return;

		$(`<style id="tvms-static-timetable-styles">
			.tvms-timetable-page { padding-bottom: 24px; }
			.tvms-filter-bar {
				background: var(--card-bg);
				border: 1px solid var(--border-color);
				border-radius: 8px;
				padding: 12px;
				margin-bottom: 14px;
			}
			.tvms-filter-row {
				display: grid;
				grid-template-columns: repeat(4, minmax(150px, 1fr));
				gap: 10px;
				align-items: end;
			}
			.tvms-field label {
				display: block;
				font-size: 12px;
				font-weight: 600;
				color: var(--text-muted);
				margin-bottom: 4px;
			}
			.tvms-weekend-toggle {
				display: flex;
				align-items: center;
				gap: 6px;
				min-height: 30px;
				margin: 0;
				color: var(--text-muted);
				font-weight: 500;
			}
			.tvms-summary {
				display: flex;
				flex-wrap: wrap;
				gap: 8px;
				margin-bottom: 12px;
			}
			.tvms-pill {
				border: 1px solid var(--border-color);
				border-radius: 999px;
				background: var(--fg-color);
				padding: 5px 10px;
				font-size: 12px;
				color: var(--text-muted);
			}
			.tvms-grid-wrap {
				overflow-x: auto;
				border: 1px solid var(--border-color);
				border-radius: 8px;
				background: var(--card-bg);
			}
			.tvms-grid {
				display: grid;
				min-width: 940px;
			}
			.tvms-grid-head,
			.tvms-time-cell,
			.tvms-day-cell {
				border-right: 1px solid var(--border-color);
				border-bottom: 1px solid var(--border-color);
			}
			.tvms-grid-head {
				position: sticky;
				top: 0;
				z-index: 1;
				background: var(--subtle-fg);
				padding: 10px;
				font-size: 12px;
				font-weight: 700;
				color: var(--text-muted);
				text-align: center;
			}
			.tvms-time-cell {
				background: var(--subtle-fg);
				padding: 10px;
				font-size: 12px;
				font-weight: 700;
				color: var(--text-muted);
			}
			.tvms-day-cell {
				min-height: 110px;
				padding: 8px;
			}
			.tvms-session-card {
				border: 1px solid var(--border-color);
				border-left: 4px solid var(--blue-500);
				border-radius: 8px;
				background: var(--fg-color);
				padding: 8px;
				margin-bottom: 8px;
				cursor: pointer;
			}
			.tvms-session-card:hover {
				box-shadow: var(--shadow-sm);
			}
			.tvms-session-title {
				font-weight: 700;
				color: var(--text-color);
				margin-bottom: 4px;
			}
			.tvms-session-meta {
				font-size: 12px;
				color: var(--text-muted);
				line-height: 1.5;
			}
			.tvms-venue-line {
				display: flex;
				align-items: center;
				gap: 6px;
				flex-wrap: wrap;
			}
			.tvms-status-dot {
				width: 7px;
				height: 7px;
				border-radius: 50%;
				display: inline-block;
				background: var(--green-500);
			}
			.tvms-status-dot.booked { background: var(--orange-500); }
			.tvms-status-dot.in-use { background: var(--red-500); }
			.tvms-empty {
				padding: 36px;
				text-align: center;
				color: var(--text-muted);
			}
			@media (max-width: 900px) {
				.tvms-filter-row { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
			}
		</style>`).appendTo("head");
	}

	bind_events() {
		this.$body.find("[data-action='apply']").on("click", () => this.load());
		this.$body.find("[data-filter]").on("change", () => this.load());
	}

	async load_options() {
		this.options = await frappe.xcall("tvms.tvms.doctype.timetable.timetable.get_filter_options");
		this.fill_select("lecturer", this.options.lecturers || [], __("All Lecturers"), "name", "full_name");
		this.fill_select("venue", this.options.venues || [], __("All Venues"), "name", "venue_name");
		this.fill_select("course", this.options.courses || [], __("All Courses"), "name", "course_name");
		this.fill_select("program", (this.options.programs || []).map((p) => ({ value: p, label: p })), __("All Programs"), "value", "label");
		this.fill_select("semester", (this.options.semesters || []).map((s) => ({ value: s, label: s })), __("All Semesters"), "value", "label");
		this.fill_select("academic_year", (this.options.academic_years || []).map((y) => ({ value: y, label: y })), __("All Years"), "value", "label");
	}

	fill_select(fieldname, rows, empty_label, value_key, label_key) {
		const $select = this.$body.find(`[data-filter='${fieldname}']`);
		$select.empty().append(`<option value="">${frappe.utils.escape_html(empty_label)}</option>`);
		rows.forEach((row) => {
			const value = row[value_key] || "";
			const label = row[label_key] || value;
			$select.append(`<option value="${frappe.utils.escape_html(value)}">${frappe.utils.escape_html(label)}</option>`);
		});
	}

	apply_route_options() {
		if (!frappe.route_options) return;

		Object.keys(frappe.route_options).forEach((key) => {
			const value = frappe.route_options[key];
			const $field = this.$body.find(`[data-filter='${key}']`);
			if ($field.length) $field.val(value);
		});
		frappe.route_options = null;
	}

	set_week_input() {
		this.$body.find("[data-filter='week_start']").val(this.format_date(this.week_start));
	}

	get_filters() {
		const values = {};
		this.$body.find("[data-filter]").each(function () {
			const $field = $(this);
			const key = $field.data("filter");
			if ($field.attr("type") === "checkbox") {
				values[key] = $field.is(":checked") ? 1 : 0;
			} else {
				values[key] = $field.val();
			}
		});

		values.week_start = values.week_start || this.format_date(this.week_start);
		return values;
	}

	async load() {
		const filters = this.get_filters();
		this.$body.find(".tvms-grid").html(`<div class="tvms-empty">${__("Loading timetable...")}</div>`);

		try {
			const sessions = await frappe.xcall("tvms.tvms.doctype.timetable.timetable.get_week_timetable", filters);
			this.render(filters, sessions || []);
		} catch (error) {
			this.$body.find(".tvms-grid").html(`<div class="tvms-empty text-danger">${__("Unable to load timetable")}</div>`);
			throw error;
		}
	}

	render(filters, sessions) {
		const days = this.get_days(filters.week_start, filters.include_weekends ? 7 : 5);
		const slots = this.get_slots(sessions);
		this.render_summary(filters, sessions);

		if (!sessions.length) {
			this.$body.find(".tvms-grid").html(`<div class="tvms-empty">${__("No timetable sessions found for the selected filters.")}</div>`);
			return;
		}

		const by_cell = {};
		sessions.forEach((session) => {
			const key = `${session.date}__${session.start_time}`;
			if (!by_cell[key]) by_cell[key] = [];
			by_cell[key].push(session);
		});

		const columns = days.length + 1;
		const html = [];
		html.push(`<div class="tvms-grid-head">${__("Time")}</div>`);
		days.forEach((day) => {
			html.push(`<div class="tvms-grid-head">${frappe.utils.escape_html(day.label)}<br>${frappe.utils.escape_html(day.display)}</div>`);
		});

		slots.forEach((slot) => {
			html.push(`<div class="tvms-time-cell">${frappe.utils.escape_html(this.time_label(slot))}</div>`);
			days.forEach((day) => {
				const cell_sessions = by_cell[`${day.date}__${slot}`] || [];
				html.push(`<div class="tvms-day-cell">${cell_sessions.map((session) => this.card(session)).join("")}</div>`);
			});
		});

		this.$body.find(".tvms-grid").css("grid-template-columns", `110px repeat(${columns - 1}, minmax(165px, 1fr))`).html(html.join(""));

		const is_admin = frappe.user.has_role(["Department Admin", "System Manager", "Administrator"]);
		const self = this;
		this.$body.find(".tvms-session-card").on("click", function () {
			const name = $(this).data("name");
			if (is_admin) {
				self._open_edit_class_dialog(name);
			} else {
				frappe.set_route("Form", "Timetable", name);
			}
		});
	}

	render_summary(filters, sessions) {
		const venues = new Set(sessions.map((s) => s.venue).filter(Boolean));
		const courses = new Set(sessions.map((s) => s.course).filter(Boolean));
		const week_end = this.format_date(this.add_days(this.parse_date(filters.week_start), filters.include_weekends ? 6 : 4));
		this.$body.find(".tvms-summary").html(`
			<span class="tvms-pill">${__("Week")}: ${frappe.utils.escape_html(filters.week_start)} - ${frappe.utils.escape_html(week_end)}</span>
			<span class="tvms-pill">${__("Sessions")}: ${sessions.length}</span>
			<span class="tvms-pill">${__("Venues Referenced")}: ${venues.size}</span>
			<span class="tvms-pill">${__("Courses")}: ${courses.size}</span>
		`);
	}

	card(session) {
		const status_class = session.venue_status === "IN-USE" ? "in-use" : session.venue_status === "BOOKED" ? "booked" : "";
		return `
			<div class="tvms-session-card" data-name="${frappe.utils.escape_html(session.name)}">
				<div class="tvms-session-title">${frappe.utils.escape_html(session.course_name || session.course || __("Untitled Course"))}</div>
				<div class="tvms-session-meta">${frappe.utils.escape_html(this.time_label(session.start_time, session.end_time))}</div>
				<div class="tvms-session-meta tvms-venue-line">
					<span class="tvms-status-dot ${status_class}"></span>
					<span>${frappe.utils.escape_html(session.venue_name || session.venue || __("No Venue"))}</span>
				</div>
				<div class="tvms-session-meta">${frappe.utils.escape_html(session.lecturer_name || session.lecturer || __("No Lecturer"))}</div>
				${session.student_groups ? `<div class="tvms-session-meta">${frappe.utils.escape_html(session.student_groups)}</div>` : ""}
			</div>
		`;
	}

	get_slots(sessions) {
		const slots = [...new Set(sessions.map((session) => session.start_time).filter(Boolean))];
		return slots.sort();
	}

	get_days(week_start, count) {
		const start = this.parse_date(week_start);
		const labels = [__("Monday"), __("Tuesday"), __("Wednesday"), __("Thursday"), __("Friday"), __("Saturday"), __("Sunday")];
		return Array.from({ length: count }, (_, index) => {
			const date = this.add_days(start, index);
			return {
				date: this.format_date(date),
				label: labels[index],
				display: frappe.datetime.str_to_user(this.format_date(date)),
			};
		});
	}

	get_monday(date) {
		const monday = new Date(date);
		const day = monday.getDay();
		const diff = day === 0 ? -6 : 1 - day;
		monday.setDate(monday.getDate() + diff);
		return monday;
	}

	parse_date(value) {
		const parts = value.split("-").map((part) => parseInt(part, 10));
		return new Date(parts[0], parts[1] - 1, parts[2]);
	}

	add_days(date, days) {
		const next = new Date(date);
		next.setDate(next.getDate() + days);
		return next;
	}

	format_date(date) {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, "0");
		const day = String(date.getDate()).padStart(2, "0");
		return `${year}-${month}-${day}`;
	}

	time_label(start, end) {
		const clean = (value) => String(value || "").slice(0, 5);
		return end ? `${clean(start)} - ${clean(end)}` : clean(start);
	}

	// ------------------------------------------------------------------
	// FR-1: Add Class — direct creation, no FET CSV required
	// ------------------------------------------------------------------

	_class_fields(defaults = {}) {
		return [
			{
				fieldname: "course", fieldtype: "Link", options: "Course",
				label: __("Course"), reqd: 1, default: defaults.course,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "venue", fieldtype: "Link", options: "Venue",
				label: __("Venue"), default: defaults.venue,
			},
			{
				fieldname: "lecturer", fieldtype: "Link", options: "User",
				label: __("Lecturer"), default: defaults.lecturer,
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "date", fieldtype: "Date",
				label: __("Date"), reqd: 1, default: defaults.date || frappe.datetime.get_today(),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "start_time", fieldtype: "Time",
				label: __("Start Time"), reqd: 1, default: defaults.start_time,
			},
			{
				fieldname: "end_time", fieldtype: "Time",
				label: __("End Time"), reqd: 1, default: defaults.end_time,
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "program", fieldtype: "Data",
				label: __("Program"), default: defaults.program,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "department", fieldtype: "Data",
				label: __("Department"), default: defaults.department,
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "academic_year", fieldtype: "Data",
				label: __("Academic Year"), default: defaults.academic_year,
				placeholder: "e.g. 2026/2027",
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "semester", fieldtype: "Select",
				label: __("Semester"), default: defaults.semester,
				options: "\nSemester 1\nSemester 2\nTrimester 1\nTrimester 2\nTrimester 3",
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "year_level", fieldtype: "Data",
				label: __("Year Level"), default: defaults.year_level,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "students_groups", fieldtype: "Data",
				label: __("Student Group(s)"), default: defaults.students_groups,
			},
		];
	}

	_open_add_class_dialog() {
		const self = this;
		const fields = this._class_fields({ date: this.week_start });

		fields.push(
			{ fieldtype: "Section Break", label: __("Repeat") },
			{
				fieldname: "repeat_weekly_until", fieldtype: "Date",
				label: __("Repeat weekly until"),
				description: __(
					"Optional. Creates the same class every week on the same weekday, " +
					"up to and including this date — no CSV needed."
				),
			},
		);

		const d = new frappe.ui.Dialog({
			title: __("Add Class to Timetable"),
			fields,
			primary_action_label: __("Create"),
			primary_action: async (values) => {
				d.set_primary_action(__("Creating..."), null);
				try {
					const r = await frappe.xcall(
						"tvms.tvms.doctype.timetable.timetable.create_timetable_entry",
						values,
					);
					frappe.show_alert({
						message: __("Created {0} timetable entr{1}", [
							r.count, r.count === 1 ? "y" : "ies",
						]),
						indicator: "green",
					});
					d.hide();
					self.load();
				} catch (e) {
					d.set_primary_action(__("Create"), () => d.get_primary_btn().trigger("click"));
				}
			},
		});

		d.show();
	}

	// ------------------------------------------------------------------
	// FR-2 / FR-3: Edit and delete an existing class directly from the grid
	// ------------------------------------------------------------------

	async _open_edit_class_dialog(name) {
		const self = this;
		let entry;
		try {
			entry = await frappe.xcall(
				"tvms.tvms.doctype.timetable.timetable.get_timetable_entry",
				{ name },
			);
		} catch (e) {
			return;
		}

		const fields = this._class_fields(entry);
		fields.push(
			{ fieldtype: "Section Break" },
			{
				fieldname: "status", fieldtype: "Select",
				label: __("Status"), default: entry.status,
				options: "SCHEDULED\nCOMPLETED",
			},
		);

		const d = new frappe.ui.Dialog({
			title: __("Edit Class") + ` — ${name}`,
			fields,
			primary_action_label: __("Save"),
			primary_action: async (values) => {
				d.set_primary_action(__("Saving..."), null);
				try {
					await frappe.xcall(
						"tvms.tvms.doctype.timetable.timetable.update_timetable_entry",
						{ name, ...values },
					);
					frappe.show_alert({ message: __("Timetable entry updated"), indicator: "green" });
					d.hide();
					self.load();
				} catch (e) {
					d.set_primary_action(__("Save"), () => d.get_primary_btn().trigger("click"));
				}
			},
			secondary_action_label: __("Delete"),
			secondary_action: () => {
				frappe.confirm(
					__("Delete this timetable entry? This cannot be undone."),
					async () => {
						await frappe.xcall(
							"tvms.tvms.doctype.timetable.timetable.delete_timetable_entry",
							{ name },
						);
						frappe.show_alert({ message: __("Timetable entry deleted"), indicator: "orange" });
						d.hide();
						self.load();
					},
				);
			},
		});

		d.show();
	}
}