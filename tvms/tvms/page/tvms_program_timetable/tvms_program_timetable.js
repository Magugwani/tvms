// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.pages["tvms-program-timetable"].on_page_load = function (wrapper) {
	frappe.tvms_program_timetable = new TVMSProgramTimetable(wrapper);
};

const PT_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

class TVMSProgramTimetable {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Timetable by Program & Year"),
			single_column: true,
		});

		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.week_start = this.get_monday(new Date());
		this.include_weekends = 0;
		this.is_admin = frappe.user.has_role(["Department Admin", "System Manager", "Administrator"]);

		this.build();
		this.load();
	}

	// ------------------------------------------------------------------
	// Layout
	// ------------------------------------------------------------------

	build() {
		this.page.set_primary_action(__("Refresh"), () => this.load(), "refresh");
		this.page.add_inner_button(__("Weekly Grid"), () => frappe.set_route("tvms-timetable"));
		this.page.add_inner_button(__("Timetable List"), () => frappe.set_route("List", "Timetable"));

		if (this.is_admin) {
			this.page.set_secondary_action(__("Add Class"), () => this._open_add_class_dialog(), "add");
		}

		this.inject_styles();

		this.$body = $(`
			<div class="tvms-pt-page">
				<div class="tvms-pt-filter-bar">
					<div class="tvms-pt-field">
						<label>${__("Week Start (Monday)")}</label>
						<input type="date" class="form-control" data-filter="week_start">
					</div>
					<div class="tvms-pt-field tvms-pt-checkbox">
						<label>
							<input type="checkbox" data-filter="include_weekends">
							${__("Include weekends")}
						</label>
					</div>
				</div>
				<div class="tvms-pt-summary"></div>
				<div class="tvms-pt-groups"></div>
			</div>
		`).appendTo(this.page.main);

		this.$body.find('[data-filter="week_start"]').val(this.week_start).on("change", (e) => {
			this.week_start = e.target.value;
			this.load();
		});
		this.$body.find('[data-filter="include_weekends"]').on("change", (e) => {
			this.include_weekends = e.target.checked ? 1 : 0;
			this.load();
		});
	}

	inject_styles() {
		if ($("#tvms-pt-styles").length) return;
		$(`<style id="tvms-pt-styles">
			.tvms-pt-page { padding: 4px 2px 24px; }
			.tvms-pt-filter-bar {
				display: flex; gap: 16px; align-items: flex-end;
				flex-wrap: wrap; margin-bottom: 14px;
			}
			.tvms-pt-field label {
				display: block; font-size: 12px; font-weight: 500;
				color: var(--text-muted); margin-bottom: 4px;
			}
			.tvms-pt-field.tvms-pt-checkbox label {
				display: flex; align-items: center; gap: 6px; font-size: 13px;
				margin-bottom: 0; padding-bottom: 6px;
			}
			.tvms-pt-summary {
				font-size: 12px; color: var(--text-muted); margin-bottom: 18px;
			}
			.tvms-pt-group {
				margin-bottom: 32px;
				border: 1px solid var(--border-color);
				border-radius: var(--border-radius-lg, 8px);
				overflow: hidden;
			}
			.tvms-pt-group-header {
				display: flex; align-items: center; justify-content: space-between;
				padding: 10px 14px; background: var(--subtle-fg, var(--fg-color));
				border-bottom: 1px solid var(--border-color);
			}
			.tvms-pt-group-title {
				font-size: 14px; font-weight: 600; margin: 0;
			}
			.tvms-pt-group-meta {
				font-size: 12px; color: var(--text-muted);
			}
			.tvms-pt-grid-wrap { overflow-x: auto; }
			.tvms-pt-grid {
				display: grid;
				min-width: 100%;
			}
			.tvms-pt-grid-head, .tvms-pt-time-cell {
				background: var(--subtle-accent, var(--control-bg));
				font-size: 11px; font-weight: 600; text-align: center;
				padding: 6px 4px; border-bottom: 1px solid var(--border-color);
				border-right: 1px solid var(--border-color);
				display: flex; align-items: center; justify-content: center;
			}
			.tvms-pt-time-cell {
				font-weight: 500; text-align: left; justify-content: flex-start;
				padding-left: 8px; white-space: nowrap;
			}
			.tvms-pt-day-cell {
				border-bottom: 1px solid var(--border-color);
				border-right: 1px solid var(--border-color);
				padding: 4px; min-height: 56px;
				display: flex; flex-direction: column; gap: 4px;
			}
			.tvms-pt-card {
				background: var(--card-bg, var(--fg-color));
				border: 1px solid var(--border-color);
				border-radius: 4px; padding: 4px 6px;
				cursor: pointer; transition: box-shadow .1s;
				font-size: 11px; line-height: 1.35;
			}
			.tvms-pt-card:hover { box-shadow: 0 0 0 1px var(--blue-300); }
			.tvms-pt-card-title { font-weight: 600; }
			.tvms-pt-card-meta { color: var(--text-muted); }
			.tvms-pt-status-dot {
				display: inline-block; width: 7px; height: 7px; border-radius: 50%;
				background: var(--green-500); margin-right: 4px;
			}
			.tvms-pt-status-dot.booked { background: var(--orange-500); }
			.tvms-pt-status-dot.in-use { background: var(--red-500); }
			.tvms-pt-empty {
				padding: 24px; text-align: center; color: var(--text-muted); font-size: 13px;
			}
			.tvms-pt-add-row-btn {
				font-size: 11px; padding: 1px 8px; border-radius: 4px;
			}
		</style>`).appendTo("head");
	}

	// ------------------------------------------------------------------
	// Data loading
	// ------------------------------------------------------------------

	async load() {
		this.$body.find(".tvms-pt-groups").html(`<div class="tvms-pt-empty">${__("Loading...")}</div>`);

		const data = await frappe.xcall(
			"tvms.tvms.doctype.timetable.timetable.get_program_timetable_groups",
			{ week_start: this.week_start, include_weekends: this.include_weekends },
		);

		this.render(data);
	}

	render(data) {
		const groups = data.groups || [];

		this.$body.find(".tvms-pt-summary").text(
			__("Week of {0} — {1} program/year segment(s)", [data.week_start, groups.length])
		);

		if (!groups.length) {
			this.$body.find(".tvms-pt-groups").html(
				`<div class="tvms-pt-empty">${__("No timetable sessions found for this week.")}</div>`
			);
			return;
		}

		const $groups = this.$body.find(".tvms-pt-groups").empty();
		groups.forEach((group) => $groups.append(this.render_group(group)));

		// Wire up clicks
		const self = this;
		$groups.find(".tvms-pt-card").on("click", function () {
			const name = $(this).data("name");
			if (self.is_admin) {
				self._open_edit_class_dialog(name);
			} else {
				frappe.set_route("Form", "Timetable", name);
			}
		});

		if (this.is_admin) {
			$groups.find(".tvms-pt-add-row-btn").on("click", function (e) {
				e.stopPropagation();
				const program = $(this).data("program");
				const year_level = $(this).data("year-level");
				self._open_add_class_dialog({ program, year_level });
			});
		}
	}

	// One group = one "Program - Year" section with its own weekly grid
	render_group(group) {
		const sessions = group.sessions || [];
		const days = this.get_days();
		const slots = this.get_slots(sessions);

		const $section = $(`
			<div class="tvms-pt-group">
				<div class="tvms-pt-group-header">
					<h3 class="tvms-pt-group-title">${frappe.utils.escape_html(group.label)}</h3>
					<div class="tvms-pt-group-meta">
						${sessions.length} ${__("session(s)")}
						${this.is_admin ? `
							<button class="btn btn-default tvms-pt-add-row-btn"
								data-program="${frappe.utils.escape_html(group.program || "")}"
								data-year-level="${frappe.utils.escape_html(group.year_level || "")}">
								+ ${__("Add Class")}
							</button>` : ""}
					</div>
				</div>
				<div class="tvms-pt-grid-wrap"></div>
			</div>
		`);

		const $wrap = $section.find(".tvms-pt-grid-wrap");

		if (!sessions.length) {
			$wrap.html(`<div class="tvms-pt-empty">${__("No sessions scheduled for this segment.")}</div>`);
			return $section;
		}

		const by_cell = {};
		sessions.forEach((s) => {
			const key = `${s.day_of_week}__${s.start_time}`;
			if (!by_cell[key]) by_cell[key] = [];
			by_cell[key].push(s);
		});

		const columns = days.length + 1;
		const html = [];
		html.push(`<div class="tvms-pt-grid-head">${__("Time")}</div>`);
		days.forEach((day) => html.push(`<div class="tvms-pt-grid-head">${day}</div>`));

		slots.forEach((slot) => {
			html.push(`<div class="tvms-pt-time-cell">${this.time_label(slot)}</div>`);
			days.forEach((day) => {
				const cell_sessions = by_cell[`${day}__${slot}`] || [];
				html.push(`<div class="tvms-pt-day-cell">${cell_sessions.map((s) => this.card(s)).join("")}</div>`);
			});
		});

		const $grid = $(`<div class="tvms-pt-grid"></div>`)
			.css("grid-template-columns", `90px repeat(${columns - 1}, minmax(140px, 1fr))`)
			.html(html.join(""));

		$wrap.append($grid);
		return $section;
	}

	card(session) {
		const status_class = session.venue_status === "IN-USE" ? "in-use"
			: session.venue_status === "BOOKED" ? "booked" : "";
		return `
			<div class="tvms-pt-card" data-name="${frappe.utils.escape_html(session.name)}">
				<div class="tvms-pt-card-title">${frappe.utils.escape_html(session.course_name || session.course || __("Untitled"))}</div>
				<div class="tvms-pt-card-meta">
					<span class="tvms-pt-status-dot ${status_class}"></span>
					${frappe.utils.escape_html(session.venue_name || session.venue || __("No venue"))}
				</div>
				<div class="tvms-pt-card-meta">${frappe.utils.escape_html(session.lecturer_name || session.lecturer || "")}</div>
				${session.students_groups ? `<div class="tvms-pt-card-meta">${frappe.utils.escape_html(session.students_groups)}</div>` : ""}
			</div>
		`;
	}

	// ------------------------------------------------------------------
	// Helpers
	// ------------------------------------------------------------------

	get_days() {
		return this.include_weekends ? PT_DAY_NAMES : PT_DAY_NAMES.slice(0, 5);
	}

	get_slots(sessions) {
		const slots = [...new Set(sessions.map((s) => s.start_time).filter(Boolean))];
		return slots.sort();
	}

	time_label(time_str) {
		return String(time_str || "").slice(0, 5);
	}

	get_monday(date) {
		const d = new Date(date);
		const day = d.getDay();
		const diff = day === 0 ? -6 : 1 - day; // shift Sunday back to previous Monday
		d.setDate(d.getDate() + diff);
		return this.format_date(d);
	}

	format_date(date) {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, "0");
		const day = String(date.getDate()).padStart(2, "0");
		return `${year}-${month}-${day}`;
	}

	// ------------------------------------------------------------------
	// FR-1: Add Class — direct creation, no FET CSV required
	// Pre-fills program / year_level when launched from a group header
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
			{ fieldtype: "Section Break", label: __("Program segment") },
			{
				fieldname: "program", fieldtype: "Data",
				label: __("Program"), default: defaults.program,
				description: __("Used to group this class under its program/year section, e.g. 'Bachelor's Degree in Information'"),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "year_level", fieldtype: "Data",
				label: __("Year Level"), default: defaults.year_level,
				placeholder: __("e.g. First Year"),
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "department", fieldtype: "Data",
				label: __("Department"), default: defaults.department,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "students_groups", fieldtype: "Data",
				label: __("Student Group(s)"), default: defaults.students_groups,
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "academic_year", fieldtype: "Data",
				label: __("Academic Year"), default: defaults.academic_year,
				placeholder: "e.g. 2025/2026",
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "semester", fieldtype: "Select",
				label: __("Semester"), default: defaults.semester,
				options: "\nSemester 1\nSemester 2\nTrimester 1\nTrimester 2\nTrimester 3",
			},
		];
	}

	_open_add_class_dialog(defaults = {}) {
		const self = this;
		const fields = this._class_fields({ date: this.week_start, ...defaults });

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

		const title = defaults.program || defaults.year_level
			? __("Add Class") + ` — ${[defaults.program, defaults.year_level].filter(Boolean).join(" / ")}`
			: __("Add Class to Timetable");

		const d = new frappe.ui.Dialog({
			title,
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