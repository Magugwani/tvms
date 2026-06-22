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
			this.page.add_inner_button(__("Publish Timetable"), () => this._open_publish_dialog());
			this.page.add_inner_button(__("Unpublish (back to draft)"), () => this._open_unpublish_dialog());
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
				<div class="tvms-pt-publish-summary"></div>
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
			.tvms-pt-page-banner {
				background: #fff;
				border-bottom: 2px solid var(--border-color);
				padding: 16px 20px;
				margin-bottom: 20px;
				position: sticky;
				top: 0;
				z-index: 10;
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 16px;
			}

			.tvms-pt-institutional {
				flex: 1;
			}

			.tvms-pt-institution-name {
				font-size: 14px;
				font-weight: 700;
				color: #1a1a1a;
				letter-spacing: 0.05em;
				text-align: center;
			}

			.tvms-pt-my-jump {
				white-space: nowrap;
			}

			.tvms-pt-title-block {
				text-align: center;
				padding: 16px 12px 12px;
				background: linear-gradient(to bottom, #f8f9fa 0%, #ffffff 100%);
				border-bottom: 1px solid var(--border-color);
				margin-bottom: 0;
			}

			.tvms-pt-title-line1 {
				font-size: 13px;
				font-weight: 700;
				letter-spacing: 0.08em;
				color: #1a1a1a;
				margin-bottom: 6px;
			}

			.tvms-pt-title-line2 {
				font-size: 14px;
				font-weight: 700;
				color: #1976d2;
				letter-spacing: 0.05em;
				margin-bottom: 4px;
			}

			.tvms-pt-title-line3 {
				font-size: 12px;
				font-weight: 600;
				color: #555;
				letter-spacing: 0.1em;
			}

			.tvms-pt-group {
				border: 1px solid var(--border-color);
				border-radius: 6px;
				margin-bottom: 24px;
				background: #fff;
				overflow: hidden;
				scroll-margin-top: 80px;
			}

			.tvms-pt-group.tvms-pt-mine {
				border: 2px solid #1976d2;
				box-shadow: 0 0 0 1px rgba(25, 118, 210, 0.1);
			}

			.tvms-pt-group.tvms-pt-highlight {
				animation: tvms-pt-pulse 2.5s ease-out;
			}

			@keyframes tvms-pt-pulse {
				0%   { box-shadow: 0 0 0 0 rgba(25, 118, 210, 0.4); }
				50%  { box-shadow: 0 0 0 12px rgba(25, 118, 210, 0); }
				100% { box-shadow: 0 0 0 0 rgba(25, 118, 210, 0); }
			}

			.tvms-pt-group-meta {
				padding: 10px 16px;
				background: #fafafa;
				border-bottom: 1px solid var(--border-color);
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 12px;
				font-size: 12px;
				color: #666;
			}

			.tvms-pt-mine-badge {
				display: inline-block;
				padding: 3px 10px;
				background: #1976d2;
				color: #fff;
				border-radius: 12px;
				font-size: 11px;
				font-weight: 600;
				text-transform: uppercase;
				letter-spacing: 0.05em;
				margin-right: auto;
				margin-left: 8px;
			}
			.tvms-pt-grid-head.tvms-pt-day-head {
				background: var(--fg-color);
				color: var(--text-color);
				font-weight: 600;
				text-align: center;
				padding: 8px 4px;
				border-right: 1px solid var(--border-color);
				border-bottom: 2px solid var(--border-color);
				position: sticky;
				left: 0;
				z-index: 2;
			}
			
			.tvms-pt-grid-head.tvms-pt-time-head {
				background: var(--bg-light-gray);
				font-weight: 600;
				text-align: center;
				padding: 8px 4px;
				border-right: 1px solid var(--border-color);
				border-bottom: 2px solid var(--border-color);
				font-size: 10px;
				white-space: nowrap;
			}
			
			.tvms-pt-day-label {
				background: var(--bg-light-gray);
				font-weight: 600;
				text-align: center;
				padding: 12px 8px;
				border-right: 2px solid var(--border-color);
				border-bottom: 1px solid var(--border-color);
				position: sticky;
				left: 0;
				z-index: 1;
			}
			
			.tvms-pt-empty-cell {
				background: #fff;
				color: #c0c0c0;
				text-align: center;
				padding: 10px 4px;
				border-right: 1px solid var(--border-color);
				border-bottom: 1px solid var(--border-color);
				font-size: 11px;
			}
			
			.tvms-pt-empty-cell.tvms-pt-closed {
				background: #f5f5f5;
				color: #999;
			}
			
			.tvms-pt-session-cell {
				background: #fff;
				border-right: 1px solid var(--border-color);
				border-bottom: 1px solid var(--border-color);
				padding: 6px;
				overflow: hidden;
			}
			
			.tvms-pt-card-course {
				font-weight: 600;
				font-size: 11px;
				line-height: 1.3;
				margin-bottom: 4px;
				color: #1976d2;
			}
			
			.tvms-pt-card-lecturer {
				font-size: 10px;
				color: #555;
				line-height: 1.3;
				margin-bottom: 3px;
				text-transform: uppercase;
				letter-spacing: 0.02em;
			}
			
			.tvms-pt-card-venue {
				font-size: 10px;
				color: #777;
				line-height: 1.3;
			}
			
			.tvms-pt-card-students {
				font-size: 10px;
				color: #999;
				line-height: 1.3;
				font-style: italic;
				margin-top: 2px;
			}
			
			.tvms-pt-status-dot {
				display: inline-block;
				width: 6px;
				height: 6px;
				border-radius: 50%;
				background: #4caf50;
				margin-right: 4px;
			}
			
			.tvms-pt-status-dot.in-use { background: #f44336; }
			.tvms-pt-status-dot.booked { background: #ff9800; }
			
			.tvms-pt-card.is-draft {
				background: #fff8e1;
				border-left: 3px solid #ffa726;
			}
			
			.tvms-pt-publish-status {
				display: inline-block;
				font-size: 9px;
				padding: 1px 4px;
				border-radius: 2px;
				margin-left: 4px;
				text-transform: uppercase;
				letter-spacing: 0.05em;
				vertical-align: middle;
			}
			
			.tvms-pt-publish-status.draft { background: #ffa726; color: #fff; }
			.tvms-pt-publish-status.published { background: #66bb6a; color: #fff; }
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
			.tvms-pt-publish-banner {
				display: flex; align-items: center; justify-content: space-between;
				gap: 12px; padding: 10px 14px; border-radius: var(--border-radius-md, 6px);
				background: var(--alert-bg-warning, rgba(255, 193, 7, 0.1));
				border: 1px solid var(--alert-border-warning, rgba(255, 193, 7, 0.4));
				margin-bottom: 14px; font-size: 13px;
			}
			.tvms-pt-publish-banner.all-published {
				background: var(--alert-bg-success, rgba(40, 167, 69, 0.1));
				border-color: var(--alert-border-success, rgba(40, 167, 69, 0.4));
			}
			.tvms-pt-publish-banner-body { display: flex; align-items: center; gap: 10px; }
			.tvms-pt-publish-counts { font-weight: 500; }
			.tvms-pt-publish-counts .pt-count-draft { color: var(--text-warning, #997404); }
			.tvms-pt-publish-counts .pt-count-pub { color: var(--text-success, #156430); }
			.tvms-pt-publish-banner-actions { display: flex; gap: 6px; }
			.tvms-pt-publish-status {
				display: inline-flex; align-items: center; gap: 4px;
				font-size: 9px; font-weight: 600; text-transform: uppercase;
				letter-spacing: 0.04em; padding: 1px 5px; border-radius: 3px;
				margin-left: 4px; vertical-align: 1px;
			}
			.tvms-pt-publish-status.draft {
				background: rgba(255, 193, 7, 0.15); color: var(--text-warning, #997404);
			}
			.tvms-pt-publish-status.published {
				background: rgba(40, 167, 69, 0.15); color: var(--text-success, #156430);
			}
			.tvms-pt-card.is-draft {
				border-style: dashed;
				opacity: 0.85;
			}
		</style>`).appendTo("head");
	}

	// ------------------------------------------------------------------
	// Data loading
	// ------------------------------------------------------------------

	async load() {
		this.$body.find(".tvms-pt-groups").html(`<div class="tvms-pt-empty">${__("Loading...")}</div>`);

		// Admins see every entry (DRAFT + PUBLISHED) via the legacy API.
		// Non-admins see only PUBLISHED entries via the new official API.
		const method = this.is_admin
			? "tvms.tvms.doctype.timetable.timetable.get_program_timetable_groups"
			: "tvms.tvms.doctype.timetable.timetable.get_published_week_timetable";

		const args = this.is_admin
			? { week_start: this.week_start, include_weekends: this.include_weekends }
			: { week_start: this.week_start };

		const data = await frappe.xcall(method, args);
		// Refresh publish status banner (admins only)
		if (this.is_admin) {
			this._refresh_publish_banner();
		}
		const header = await frappe.xcall(
			"tvms.tvms.doctype.timetable.timetable.get_institutional_header"
		);
		this.institutional_header = header || {};

		try {
			this.my_segment = await frappe.xcall(
				"tvms.tvms.doctype.timetable.timetable.get_my_program_segment"
			);
		} catch (e) {
			this.my_segment = {};
		}
				const data = await frappe.xcall(
			"tvms.tvms.doctype.timetable.timetable.get_program_timetable_groups",
			{
				week_start: this.week_start,
				include_weekends: this.include_weekends ? 1 : 0,
				program: this.filter_program || null,
				year_level: this.filter_year || null,
			}
		);

		this.render(data);
	}

	async _refresh_publish_banner() {
		try {
			const summary = await frappe.xcall(
				"tvms.tvms.doctype.timetable.timetable.get_publish_status_summary"
			);
			this._render_publish_banner(summary);
		} catch (e) {
			// If the API isn't deployed yet, hide the banner silently
			this.$body.find(".tvms-pt-publish-summary").empty();
		}
	}

	_render_publish_banner(summary) {
		const $banner = this.$body.find(".tvms-pt-publish-summary");
		const total = summary.total || 0;
		const draft = summary.draft || 0;
		const published = summary.published || 0;

		if (!total) {
			$banner.empty();
			return;
		}

		const all_published = draft === 0 && published > 0;
		const cls = all_published ? "all-published" : "";
		const message = all_published
			? __("All timetable entries are published as official.")
			: __("{0} draft entry(ies) not yet published.", [draft]);

		$banner.html(`
			<div class="tvms-pt-publish-banner ${cls}">
				<div class="tvms-pt-publish-banner-body">
					<span>${message}</span>
					<span class="tvms-pt-publish-counts">
						<span class="pt-count-draft">${draft} ${__("draft")}</span> ·
						<span class="pt-count-pub">${published} ${__("published")}</span>
					</span>
				</div>
				<div class="tvms-pt-publish-banner-actions">
					${draft > 0 ? `<button class="btn btn-primary btn-xs" data-action="publish-all">${__("Publish All")}</button>` : ""}
				</div>
			</div>
		`);

		$banner.find('[data-action="publish-all"]').on("click", () => this._open_publish_dialog());
	}

	render(data) {
		const groups = data.groups || [];
				// render institutional banner above everything
		this._render_institutional_banner();

		// render my-program jump button if user has a known segment
		this._render_my_segment_jump();

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
		if (!groups.length) {
			this.$body.find(".tvms-pt-groups").html(`
				<div class="tvms-pt-empty">
					${__("No timetable entries match the current filters.")}
				</div>
			`);
			return;
		}

		const $groups = this.$body.find(".tvms-pt-groups").empty();
		groups.forEach((group) => $groups.append(this.render_group(group)));
	}
		_render_institutional_banner() {
		const h = this.institutional_header || {};
		if (!h.institution) return;

		// Build the page-top banner. We render it once at the top of
		// the layout, not inside .tvms-pt-groups (which gets rebuilt
		// on every refresh).
		let $banner = this.wrapper.find(".tvms-pt-page-banner");
		if (!$banner.length) {
			$banner = $(`<div class="tvms-pt-page-banner"></div>`);
			this.$body.prepend($banner);
		}

		const sem_text = h.semester
			? `${h.semester}${h.academic_year ? ` (${h.academic_year})` : ""}`
			: "";

		$banner.html(`
			<div class="tvms-pt-institutional">
				<div class="tvms-pt-institution-name">
					${frappe.utils.escape_html(h.institution)}${sem_text ? `&nbsp;&nbsp;-&nbsp;&nbsp;${frappe.utils.escape_html(sem_text)}` : ""}
				</div>
			</div>
		`);
	}
		_render_my_segment_jump() {
		const seg = this.my_segment || {};
		if (!seg.program) return;

		// Build a "Jump to my timetable" button in the page toolbar
		let $btn = this.wrapper.find(".tvms-pt-my-jump");
		if (!$btn.length) {
			$btn = $(`
				<button class="btn btn-sm btn-primary tvms-pt-my-jump">
					<i class="ti ti-arrow-down"></i>
					${__("Jump to My Timetable")}
				</button>
			`);
			this.wrapper.find(".tvms-pt-page-banner").append($btn);
		}

		$btn.off("click").on("click", () => {
			const key = `${seg.program}||${seg.year_level}`;
			const $target = this.wrapper.find(`.tvms-pt-group[data-key="${key}"]`);
			if ($target.length) {
				// Smooth scroll, then briefly highlight
				$target[0].scrollIntoView({ behavior: "smooth", block: "start" });
				$target.addClass("tvms-pt-highlight");
				setTimeout(() => $target.removeClass("tvms-pt-highlight"), 2500);
			}
		});
	}

	// One group = one "Program - Year" section with its own weekly grid
	render_group(group) {
		const sessions = group.sessions || [];
		const days = this.get_days();
		const time_slots = this.get_hourly_slots();   // 07:00 → 21:00 fixed
 
				//  build the printed-format title block
		const title_block = this._build_title_block(group);

		// Highlight if this is the user's own program segment
		const is_mine = this.my_segment &&
			this.my_segment.program === group.program &&
			this.my_segment.year_level === group.year_level;
		const mine_class = is_mine ? " tvms-pt-mine" : "";

		const $section = $(`
			<div class="tvms-pt-group${mine_class}" data-key="${frappe.utils.escape_html(group.key)}">
				${title_block}
				<div class="tvms-pt-group-meta">
					${sessions.length} ${__("session(s)")}
					${is_mine ? `<span class="tvms-pt-mine-badge">${__("Your timetable")}</span>` : ""}
					${this.is_admin ? `
						<button class="btn btn-default tvms-pt-add-row-btn"
							data-program="${frappe.utils.escape_html(group.program || "")}"
							data-year-level="${frappe.utils.escape_html(group.year_level || "")}">
							+ ${__("Add Class")}
						</button>` : ""}
				</div>
				<div class="tvms-pt-grid-wrap"></div>
			</div>
		`);
 
		const $wrap = $section.find(".tvms-pt-grid-wrap");
 
		// Build a lookup: day → array of sessions for that day, sorted by start_time
		const by_day = {};
		days.forEach((d) => { by_day[d] = []; });
		sessions.forEach((s) => {
			if (by_day[s.day_of_week]) by_day[s.day_of_week].push(s);
		});
		Object.keys(by_day).forEach((d) => {
			by_day[d].sort((a, b) => (a.start_time || "").localeCompare(b.start_time || ""));
		});

		const html = [];
		html.push(`<div class="tvms-pt-grid-head tvms-pt-day-head">${__("Day")}</div>`);
		time_slots.forEach((slot) => {
			html.push(`<div class="tvms-pt-grid-head tvms-pt-time-head">${this.time_range_label(slot)}</div>`);
		});

		days.forEach((day) => {
			const day_sessions = by_day[day] || [];
			const is_closed = day === "Sunday";

			html.push(`<div class="tvms-pt-day-label">${day}</div>`);

			if (is_closed) {
				time_slots.forEach(() => {
					html.push(`<div class="tvms-pt-empty-cell tvms-pt-closed">-x-</div>`);
				});
				return;
			}

			const slot_owner = new Array(time_slots.length).fill(null);
			const slot_starts = new Array(time_slots.length).fill(false);

			day_sessions.forEach((s) => {
				const start_idx = time_slots.indexOf(String(s.start_time || "").slice(0, 5) + ":00");
				if (start_idx < 0) return;
				const start_h = parseInt(String(s.start_time || "00:00").slice(0, 2), 10);
				const end_h = parseInt(String(s.end_time || "00:00").slice(0, 2), 10);
				const end_m = parseInt(String(s.end_time || "00:00").slice(3, 5), 10);
				const span = Math.max(1, (end_h - start_h) + (end_m > 0 ? 1 : 0));
				for (let i = 0; i < span && (start_idx + i) < time_slots.length; i++) {
					slot_owner[start_idx + i] = s;
				}
				slot_starts[start_idx] = true;
			});

			for (let i = 0; i < time_slots.length; i++) {
				const session = slot_owner[i];
				if (!session) {
					html.push(`<div class="tvms-pt-empty-cell">---</div>`);
					continue;
				}
				if (!slot_starts[i]) continue;
				const start_h = parseInt(String(session.start_time || "00:00").slice(0, 2), 10);
				const end_h = parseInt(String(session.end_time || "00:00").slice(0, 2), 10);
				const end_m = parseInt(String(session.end_time || "00:00").slice(3, 5), 10);
				const span = Math.max(1, (end_h - start_h) + (end_m > 0 ? 1 : 0));
				html.push(`<div class="tvms-pt-session-cell" style="grid-column: span ${span};">${this.card(session)}</div>`);
			}
		});
		

		const $grid = $(`<div class="tvms-pt-grid tvms-pt-grid-excel"></div>`)
			.css("grid-template-columns", `90px repeat(${time_slots.length}, minmax(110px, 1fr))`)
			.html(html.join(""));

		$wrap.append($grid);
		return $section;
	}
	// Renders the 3-line printed-format title above each grid

	_build_title_block(group) {
		const h = this.institutional_header || {};
		const semester = group.semester || h.semester || "";
		const ay = group.academic_year || h.academic_year || "";
		const sem_year = semester
			? `${semester}${ay ? ` (${ay})` : ""}`
			: "";

		// Line 1: Institution + Semester + Academic Year
		const line1 = h.institution && sem_year
			? `${h.institution}&nbsp;&nbsp;-&nbsp;&nbsp;${sem_year.toUpperCase()}`
			: h.institution || sem_year.toUpperCase() || "";

		// Line 2: Program name + level + code
		// Format: "BACHELOR'S DEGREE IN INFORMATION TECHNOLOGY LEVEL-8 BIT"
		const program_parts = [];
		if (group.program_name) program_parts.push(group.program_name);
		if (group.year_number) program_parts.push(`LEVEL-${group.year_number}`);
		if (group.program_code) program_parts.push(group.program_code);
		const line2 = program_parts.join(" ").toUpperCase();

		// Line 3: Stream (only if set)
		const line3 = group.stream ? group.stream.toUpperCase() : "";

		return `
			<div class="tvms-pt-title-block">
				${line1 ? `<div class="tvms-pt-title-line1">${frappe.utils.escape_html_all(line1)}</div>` : ""}
				${line2 ? `<div class="tvms-pt-title-line2">${frappe.utils.escape_html(line2)}</div>` : ""}
				${line3 ? `<div class="tvms-pt-title-line3">${frappe.utils.escape_html(line3)}</div>` : ""}
			</div>
		`;
	}

 
 
// ─── REPLACE card() — Excel-style content layout ───────────
 
	card(session) {
		const status_class = session.venue_status === "IN-USE" ? "in-use"
			: session.venue_status === "BOOKED" ? "booked" : "";
 
		const pub = (session.publish_status || "").toUpperCase();
		const is_draft = pub === "DRAFT";
		const badge = this.is_admin && pub
			? `<span class="tvms-pt-publish-status ${is_draft ? "draft" : "published"}">${
				is_draft ? __("Draft") : __("Live")
			}</span>`
			: "";
		const draft_cls = this.is_admin && is_draft ? " is-draft" : "";
 
		// Course display = code + name (Excel format: "AEU 08208E Project Management")
		const course_line = session.course && session.course_name
			? `${frappe.utils.escape_html(session.course)} ${frappe.utils.escape_html(session.course_name)}`
			: frappe.utils.escape_html(session.course || session.course_name || __("Untitled"));
 
		// Venue display with capacity (Excel format: "LWF 04 - B 15 (Capacity: 240)")
		const venue_text = session.venue_name || session.venue || __("No venue");
		const venue_line = session.venue_capacity
			? `${frappe.utils.escape_html(venue_text)} (Capacity: ${session.venue_capacity})`
			: frappe.utils.escape_html(venue_text);
 
		return `
			<div class="tvms-pt-card${draft_cls}" data-name="${frappe.utils.escape_html(session.name)}">
				<div class="tvms-pt-card-course">
					${course_line}
					${badge}
				</div>
				<div class="tvms-pt-card-lecturer">
					${frappe.utils.escape_html(session.lecturer_name || session.lecturer || "")}
				</div>
				<div class="tvms-pt-card-venue">
					<span class="tvms-pt-status-dot ${status_class}"></span>
					${venue_line}
				</div>
				${session.students_groups ? `
					<div class="tvms-pt-card-students">
						${frappe.utils.escape_html(session.students_groups)}
					</div>` : ""}
			</div>
		`;
	}
 
 
// ─── ADD: new helper functions (near get_slots / get_days) ──
 
	// Generate every hourly slot from 07:00 to 21:00
	// Returns ["07:00:00", "08:00:00", ..., "20:00:00"]
	get_hourly_slots() {
		const slots = [];
		for (let h = 7; h < 21; h++) {
			slots.push(`${String(h).padStart(2, "0")}:00:00`);
		}
		return slots;
	}
 
	// Format slot for display: "07:00:00" → "07:00 - 08:00"
	time_range_label(slot) {
		const start = String(slot).slice(0, 5);
		const start_h = parseInt(slot.slice(0, 2), 10);
		const end_h = start_h + 1;
		const end = `${String(end_h).padStart(2, "0")}:00`;
		return `${start} - ${end}`;
	}

	// ------------------------------------------------------------------
	// Helpers
	// ------------------------------------------------------------------

	get_days() {
		return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
	}
		// Generate every hourly slot from 07:00 to 21:00
	// Returns ["07:00:00", "08:00:00", ..., "20:00:00"]
	get_hourly_slots() {
		const slots = [];
		for (let h = 7; h < 21; h++) {
			slots.push(`${String(h).padStart(2, "0")}:00:00`);
		}
		return slots;
	}
 
	// Format slot for display: "07:00:00" → "07:00 - 08:00"
	time_range_label(slot) {
		const start = String(slot).slice(0, 5);
		const start_h = parseInt(slot.slice(0, 2), 10);
		const end_h = start_h + 1;
		const end = `${String(end_h).padStart(2, "0")}:00`;
		return `${start} - ${end}`;
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
		const self = this;
		return [
			{ fieldtype: "Section Break", label: __("Program segment") },
			{
				fieldname: "program", fieldtype: "Link", options: "Program",
				label: __("Program"), reqd: 1, default: defaults.program,
				onchange: function () {
					// When program changes, refresh course filter and year options
					const program = this.get_value();
					const year_field = this.layout.get_field("year_level");
					const course_field = this.layout.get_field("course");
					if (program && year_field) {
						frappe.xcall(
							"tvms.tvms.doctype.program.program.get_program_years",
							{ program },
						).then((years) => {
							year_field.df.options = ["", ...years].join("\n");
							year_field.refresh();
						});
					}
					if (course_field) {
						course_field.get_query = () => ({
							filters: {
								program: program || undefined,
								status: "Active",
							},
						});
					}
				},
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "year_level", fieldtype: "Select",
				label: __("Year Level"), reqd: 1, default: defaults.year_level,
				options: "\n1\n2\n3\n4\n5\n6",
				onchange: function () {
					// When year changes, also re-narrow the course list
					const program = this.layout.get_value("program");
					const year = this.get_value();
					const course_field = this.layout.get_field("course");
					if (course_field) {
						course_field.get_query = () => ({
							filters: {
								program: program || undefined,
								year: year || undefined,
								status: "Active",
							},
						});
					}
				},
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "course", fieldtype: "Link", options: "Course",
				label: __("Course"), reqd: 1, default: defaults.course,
				get_query: () => ({
					filters: {
						program: defaults.program || undefined,
						year: defaults.year_level || undefined,
						status: "Active",
					},
				}),
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
			{ fieldtype: "Section Break", label: __("Schedule") },
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
			{ fieldtype: "Section Break", label: __("Department & students") },
			{
				fieldname: "department", fieldtype: "Link", options: "Departments",
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
			{ fieldtype: "Section Break", label: __("Status & visibility") },
			{
				fieldname: "status", fieldtype: "Select",
				label: __("Status"), default: entry.status,
				options: "SCHEDULED\nCOMPLETED",
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "publish_status", fieldtype: "Select",
				label: __("Publish Status"), default: entry.publish_status || "DRAFT",
				options: "DRAFT\nPUBLISHED",
				description: __(
					"DRAFT = visible to admins only. " +
					"PUBLISHED = visible to all lecturers, CRs, and students."
				),
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

	// ------------------------------------------------------------------
	// Publish workflow — turn DRAFT entries into the official timetable
	// ------------------------------------------------------------------

	_open_publish_dialog() {
		const self = this;
		const filters = this.get_filters();

		const d = new frappe.ui.Dialog({
			title: __("Publish Timetable"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<div style="font-size:13px;color:var(--text-muted);margin-bottom:8px;">
						${__("Choose what to publish. Leave a filter blank to publish across all values.")}
					</div>`,
				},
				{
					fieldname: "program", fieldtype: "Link", options: "Program",
					label: __("Program"), default: filters.program,
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "year_level", fieldtype: "Select",
					label: __("Year Level"),
					options: "\n1\n2\n3\n4\n5\n6",
					default: filters.year_level,
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "semester", fieldtype: "Select",
					label: __("Semester"),
					options: "\nSemester 1\nSemester 2\nTrimester 1\nTrimester 2\nTrimester 3",
					default: filters.semester,
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "academic_year", fieldtype: "Data",
					label: __("Academic Year"),
					default: filters.academic_year,
					placeholder: __("e.g. 2026/2027"),
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "HTML",
					options: `<div style="background:var(--bg-yellow);padding:8px 12px;border-radius:6px;font-size:13px;">
						<i class="fa fa-info-circle"></i> ${__("Published entries become visible to all lecturers, CRs, and students.")}
					</div>`,
				},
			],
			primary_action_label: __("Publish"),
			primary_action: async (values) => {
				const args = Object.fromEntries(
					Object.entries(values).filter(([_, v]) => v),
				);
				d.set_primary_action(__("Publishing..."), null);
				try {
					const r = await frappe.xcall(
						"tvms.tvms.doctype.timetable.timetable.publish_timetable",
						args,
					);
					frappe.show_alert({
						message: r.published
							? __("Published {0} timetable entr{1}", [r.published, r.published === 1 ? "y" : "ies"])
							: __("No draft entries matched."),
						indicator: r.published ? "green" : "blue",
					});
					d.hide();
					self.load();
				} catch (e) {
					d.set_primary_action(__("Publish"), () => d.get_primary_btn().trigger("click"));
				}
			},
		});

		d.show();
	}

	_open_unpublish_dialog() {
		const self = this;
		const filters = this.get_filters();

		const d = new frappe.ui.Dialog({
			title: __("Unpublish (move back to draft)"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<div style="background:var(--bg-red);padding:8px 12px;border-radius:6px;font-size:13px;margin-bottom:12px;">
						<i class="fa fa-exclamation-triangle"></i> ${__(
							"This makes the timetable invisible to non-admin users. " +
							"Use only when preparing a major schedule change."
						)}
					</div>`,
				},
				{
					fieldname: "program", fieldtype: "Link", options: "Program",
					label: __("Program"), default: filters.program,
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "year_level", fieldtype: "Select",
					label: __("Year Level"),
					options: "\n1\n2\n3\n4\n5\n6",
					default: filters.year_level,
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "semester", fieldtype: "Select",
					label: __("Semester"),
					options: "\nSemester 1\nSemester 2\nTrimester 1\nTrimester 2\nTrimester 3",
					default: filters.semester,
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "academic_year", fieldtype: "Data",
					label: __("Academic Year"),
					default: filters.academic_year,
				},
			],
			primary_action_label: __("Unpublish"),
			primary_action: async (values) => {
				const args = Object.fromEntries(
					Object.entries(values).filter(([_, v]) => v),
				);
				frappe.confirm(
					__("Move matching published entries back to draft?"),
					async () => {
						d.set_primary_action(__("Unpublishing..."), null);
						try {
							const r = await frappe.xcall(
								"tvms.tvms.doctype.timetable.timetable.unpublish_timetable",
								args,
							);
							frappe.show_alert({
								message: r.unpublished
									? __("Moved {0} entr{1} back to draft", [r.unpublished, r.unpublished === 1 ? "y" : "ies"])
									: __("No published entries matched."),
								indicator: r.unpublished ? "orange" : "blue",
							});
							d.hide();
							self.load();
						} catch (e) {
							d.set_primary_action(__("Unpublish"), () => d.get_primary_btn().trigger("click"));
						}
					},
				);
			},
		});

		d.show();
	}
}