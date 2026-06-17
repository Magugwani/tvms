// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.pages["tvms-changes"].on_page_load = function (wrapper) {
	frappe.tvms_changes_page = new TVMSChangesPage(wrapper);
};

class TVMSChangesPage {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Timetable Changes"),
			single_column: true,
		});
		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.$body = this.wrapper.find(".layout-main-section");

		this.build();
		this.load();
	}

	build() {
		this.page.set_primary_action(__("Refresh"), () => this.load(), "refresh");
		this.page.add_inner_button(__("Open Timetable"), () =>
			frappe.set_route("tvms-program-timetable"),
		);
		this.page.add_inner_button(__("Change Log List"), () =>
			frappe.set_route("List", "Timetable Change Log"),
		);

		this.$body.html(`
			<div class="tvms-changes-page" style="padding: 1rem 0;">
				<div class="tvms-changes-filters" style="
					display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end;
					padding: 12px 16px; background: var(--card-bg);
					border: 1px solid var(--border-color); border-radius: 8px;
					margin-bottom: 16px;
				">
					<div style="flex: 1; min-width: 130px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("From date")}</label>
						<input type="date" class="form-control input-xs" id="tvms-from-date">
					</div>
					<div style="flex: 1; min-width: 130px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("To date")}</label>
						<input type="date" class="form-control input-xs" id="tvms-to-date">
					</div>
					<div style="flex: 1; min-width: 130px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("Action")}</label>
						<select class="form-control input-xs" id="tvms-action">
							<option value="">${__("All actions")}</option>
							<option value="CREATED">${__("Created")}</option>
							<option value="UPDATED">${__("Updated")}</option>
							<option value="PUBLISHED">${__("Published")}</option>
							<option value="UNPUBLISHED">${__("Unpublished")}</option>
							<option value="DELETED">${__("Deleted")}</option>
						</select>
					</div>
					<div style="flex: 1; min-width: 180px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("Changed by")}</label>
						<input type="text" class="form-control input-xs" id="tvms-user" placeholder="${__("Email or full name")}">
					</div>
					<div style="flex: 1; min-width: 130px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("Program")}</label>
						<input type="text" class="form-control input-xs" id="tvms-program" placeholder="${__("Program code")}">
					</div>
					<button class="btn btn-default btn-xs" id="tvms-apply" style="height: 32px;">${__("Apply")}</button>
					<button class="btn btn-default btn-xs" id="tvms-clear" style="height: 32px;">${__("Clear")}</button>
				</div>

				<div class="tvms-changes-summary" style="
					font-size: 13px; color: var(--text-muted);
					margin-bottom: 12px;
				"></div>

				<div class="tvms-changes-list" style="
					background: var(--card-bg);
					border: 1px solid var(--border-color);
					border-radius: 8px;
				"></div>
			</div>

			<style>
				.tvms-change-row {
					padding: 14px 16px;
					border-bottom: 1px solid var(--border-color);
					display: grid;
					grid-template-columns: 130px 110px 1fr 180px;
					gap: 14px;
					align-items: start;
					font-size: 13px;
				}
				.tvms-change-row:last-child { border-bottom: none; }
				.tvms-change-row:hover { background: var(--subtle-fg); }
				.tvms-change-time {
					font-family: var(--font-mono);
					color: var(--text-muted);
					font-size: 12px;
				}
				.tvms-change-action {
					font-size: 11px; font-weight: 500;
					padding: 2px 8px; border-radius: 4px;
					text-transform: uppercase; letter-spacing: 0.04em;
					justify-self: start;
				}
				.tvms-change-action.CREATED   { background: #EAF3DE; color: #27500A; }
				.tvms-change-action.UPDATED   { background: #E6F1FB; color: #185FA5; }
				.tvms-change-action.PUBLISHED { background: #DCF1E8; color: #0F6E56; }
				.tvms-change-action.UNPUBLISHED { background: #FAEEDA; color: #633806; }
				.tvms-change-action.DELETED   { background: #FCEBEB; color: #A32D2D; }
				.tvms-change-body { line-height: 1.5; }
				.tvms-change-entry-link {
					font-family: var(--font-mono);
					font-size: 11px;
					color: var(--text-muted);
				}
				.tvms-change-summary { color: var(--text-color); margin-top: 2px; }
				.tvms-change-reason {
					font-style: italic; color: var(--text-muted);
					margin-top: 4px; font-size: 12px;
				}
				.tvms-change-user {
					font-size: 12px; color: var(--text-muted);
				}
				.tvms-change-user .name { color: var(--text-color); }
				.tvms-changes-empty {
					padding: 40px 20px; text-align: center;
					color: var(--text-muted); font-size: 13px;
				}
			</style>
		`);

		this.wrapper.find("#tvms-apply").on("click", () => this.load());
		this.wrapper.find("#tvms-clear").on("click", () => this.clear_filters());
		this.wrapper.find(".tvms-changes-filters input, .tvms-changes-filters select")
			.on("keydown", (e) => { if (e.key === "Enter") this.load(); });
	}

	get_filters() {
		return {
			from_date:  this.wrapper.find("#tvms-from-date").val() || null,
			to_date:    this.wrapper.find("#tvms-to-date").val() || null,
			action:     this.wrapper.find("#tvms-action").val() || null,
			changed_by: this.wrapper.find("#tvms-user").val() || null,
			program:    this.wrapper.find("#tvms-program").val() || null,
			limit:      200,
		};
	}

	clear_filters() {
		this.wrapper.find(".tvms-changes-filters input").val("");
		this.wrapper.find(".tvms-changes-filters select").val("");
		this.load();
	}

	async load() {
		const $list = this.wrapper.find(".tvms-changes-list");
		const $summary = this.wrapper.find(".tvms-changes-summary");
		$list.html(`<div class="tvms-changes-empty">${__("Loading...")}</div>`);
		$summary.text("");

		try {
			const r = await frappe.xcall(
				"tvms.tvms.doctype.timetable.timetable.search_timetable_changes",
				this.get_filters(),
			);
			this.render(r);
		} catch (e) {
			$list.html(`<div class="tvms-changes-empty">${__("Failed to load changes.")}</div>`);
		}
	}

	render(result) {
		const changes = result.changes || [];
		const $list = this.wrapper.find(".tvms-changes-list");
		const $summary = this.wrapper.find(".tvms-changes-summary");

		$summary.text(__("{0} change(s) found", [changes.length]));

		if (!changes.length) {
			$list.html(`<div class="tvms-changes-empty">${__("No changes match the current filters.")}</div>`);
			return;
		}

		const rows = changes.map(c => {
			const escaped_entry = frappe.utils.escape_html(c.timetable_entry || "");
			const escaped_summary = frappe.utils.escape_html(c.summary || "");
			const escaped_reason = c.reason ? frappe.utils.escape_html(c.reason) : "";
			const escaped_name = frappe.utils.escape_html(c.changed_by_name || c.changed_by || "");
			const escaped_user = frappe.utils.escape_html(c.changed_by || "");

			const reason_block = escaped_reason
				? `<div class="tvms-change-reason">${__("Reason")}: ${escaped_reason}</div>`
				: "";

			return `
				<div class="tvms-change-row" data-name="${frappe.utils.escape_html(c.name)}">
					<div class="tvms-change-time">${frappe.utils.escape_html(c.timestamp || "")}</div>
					<span class="tvms-change-action ${c.action}">${c.action}</span>
					<div class="tvms-change-body">
						<a href="/app/timetable/${escaped_entry}"
						   class="tvms-change-entry-link">${escaped_entry}</a>
						<div class="tvms-change-summary">${escaped_summary}</div>
						${reason_block}
					</div>
					<div class="tvms-change-user">
						<div class="name">${escaped_name}</div>
						<div>${escaped_user}</div>
					</div>
				</div>
			`;
		}).join("");

		$list.html(rows);

		$list.find(".tvms-change-row").on("click", function (e) {
			if ($(e.target).is("a")) return;
			frappe.set_route("Form", "Timetable Change Log", $(this).data("name"));
		});
	}
}