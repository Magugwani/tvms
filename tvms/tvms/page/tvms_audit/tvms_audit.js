frappe.pages['tvms-audit'].on_page_load = function(wrapper) {
	frappe.tvms_audit_page = new TVMSAuditPage(wrapper);
};
 
class TVMSAuditPage {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("TVMS Audit"),
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
		this.page.add_inner_button(__("Audit List"), () =>
			frappe.set_route("List", "TVMS Audit Log"),
		);
		this.page.add_inner_button(__("Timetable Changes"), () =>
			frappe.set_route("tvms-changes"),
		);
 
		this.$body.html(`
			<div class="tvms-audit-page" style="padding: 1rem 0;">
				<div class="tvms-audit-filters" style="
					display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end;
					padding: 12px 16px; background: var(--card-bg);
					border: 1px solid var(--border-color); border-radius: 8px;
					margin-bottom: 16px;
				">
					<div style="flex: 1; min-width: 130px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("From date")}</label>
						<input type="date" class="form-control input-xs" id="tvms-audit-from">
					</div>
					<div style="flex: 1; min-width: 130px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("To date")}</label>
						<input type="date" class="form-control input-xs" id="tvms-audit-to">
					</div>
					<div style="flex: 1; min-width: 170px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("Event type")}</label>
						<select class="form-control input-xs" id="tvms-audit-event">
							<option value="">${__("All events")}</option>
							<optgroup label="${__("Session")}">
								<option value="SESSION_CREATED">${__("Created")}</option>
								<option value="SESSION_CONFIRMED">${__("Confirmed")}</option>
								<option value="SESSION_CANCELLED">${__("Cancelled")}</option>
								<option value="SESSION_COMPLETED">${__("Completed")}</option>
								<option value="SESSION_EXPIRED">${__("Expired")}</option>
								<option value="SESSION_POSTPONED">${__("Postponed")}</option>
							</optgroup>
							<optgroup label="${__("Notification")}">
								<option value="NOTIFICATION_SENT">${__("Sent")}</option>
								<option value="NOTIFICATION_READ">${__("Read")}</option>
								<option value="NOTIFICATION_FORWARDED">${__("Forwarded")}</option>
							</optgroup>
						</select>
					</div>
					<div style="flex: 1; min-width: 180px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("Actor")}</label>
						<input type="text" class="form-control input-xs" id="tvms-audit-actor" placeholder="${__("User email")}">
					</div>
					<div style="flex: 1; min-width: 160px;">
						<label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">${__("Subject name")}</label>
						<input type="text" class="form-control input-xs" id="tvms-audit-subject" placeholder="${__("e.g. EMS-0042")}">
					</div>
					<button class="btn btn-default btn-xs" id="tvms-audit-apply" style="height: 32px;">${__("Apply")}</button>
					<button class="btn btn-default btn-xs" id="tvms-audit-clear" style="height: 32px;">${__("Clear")}</button>
				</div>
 
				<div class="tvms-audit-summary" style="
					font-size: 13px; color: var(--text-muted); margin-bottom: 12px;
				"></div>
 
				<div class="tvms-audit-list" style="
					background: var(--card-bg);
					border: 1px solid var(--border-color);
					border-radius: 8px;
				"></div>
			</div>
 
			<style>
				.tvms-audit-row {
					padding: 14px 16px;
					border-bottom: 1px solid var(--border-color);
					display: grid;
					grid-template-columns: 130px 130px 1fr 180px;
					gap: 14px;
					align-items: start;
					font-size: 13px;
					cursor: pointer;
				}
				.tvms-audit-row:last-child { border-bottom: none; }
				.tvms-audit-row:hover { background: var(--subtle-fg); }
				.tvms-audit-time {
					font-family: var(--font-mono);
					color: var(--text-muted);
					font-size: 12px;
				}
				.tvms-audit-event {
					font-size: 10px; font-weight: 500;
					padding: 2px 8px; border-radius: 4px;
					text-transform: uppercase; letter-spacing: 0.04em;
					justify-self: start; white-space: nowrap;
				}
				.tvms-audit-event.SESSION_CREATED { background: #EAF3DE; color: #27500A; }
				.tvms-audit-event.SESSION_CONFIRMED { background: #DCF1E8; color: #0F6E56; }
				.tvms-audit-event.SESSION_CANCELLED { background: #FCEBEB; color: #A32D2D; }
				.tvms-audit-event.SESSION_COMPLETED { background: #E6F1FB; color: #185FA5; }
				.tvms-audit-event.SESSION_EXPIRED { background: #F1EFE8; color: #5F5E5A; }
				.tvms-audit-event.SESSION_POSTPONED { background: #FAEEDA; color: #633806; }
				.tvms-audit-event.NOTIFICATION_SENT { background: #EEEDFE; color: #3C3489; }
				.tvms-audit-event.NOTIFICATION_READ { background: #E1F5EE; color: #085041; }
				.tvms-audit-event.NOTIFICATION_FORWARDED { background: #FBEAF0; color: #72243E; }
				.tvms-audit-event.VENUE_STATUS_CHANGED { background: #FAECE7; color: #712B13; }
				.tvms-audit-event.OTHER { background: #F1EFE8; color: #5F5E5A; }
				.tvms-audit-body { line-height: 1.5; }
				.tvms-audit-subject-link {
					font-family: var(--font-mono);
					font-size: 11px;
					color: var(--text-muted);
				}
				.tvms-audit-summary-text { color: var(--text-color); margin-top: 2px; }
				.tvms-audit-recipient {
					color: var(--text-muted);
					font-size: 12px; margin-top: 4px;
				}
				.tvms-audit-actor {
					font-size: 12px; color: var(--text-muted);
				}
				.tvms-audit-actor .name { color: var(--text-color); }
				.tvms-audit-empty {
					padding: 40px 20px; text-align: center;
					color: var(--text-muted); font-size: 13px;
				}
			</style>
		`);
 
		this.wrapper.find("#tvms-audit-apply").on("click", () => this.load());
		this.wrapper.find("#tvms-audit-clear").on("click", () => this.clear_filters());
		this.wrapper.find(".tvms-audit-filters input, .tvms-audit-filters select")
			.on("keydown", (e) => { if (e.key === "Enter") this.load(); });
	}
 
	get_filters() {
		return {
			from_date:    this.wrapper.find("#tvms-audit-from").val() || null,
			to_date:      this.wrapper.find("#tvms-audit-to").val() || null,
			event_type:   this.wrapper.find("#tvms-audit-event").val() || null,
			actor:        this.wrapper.find("#tvms-audit-actor").val() || null,
			subject_name: this.wrapper.find("#tvms-audit-subject").val() || null,
			limit:        200,
		};
	}
 
	clear_filters() {
		this.wrapper.find(".tvms-audit-filters input").val("");
		this.wrapper.find(".tvms-audit-filters select").val("");
		this.load();
	}
 
	async load() {
		const $list = this.wrapper.find(".tvms-audit-list");
		const $summary = this.wrapper.find(".tvms-audit-summary");
		$list.html(`<div class="tvms-audit-empty">${__("Loading...")}</div>`);
		$summary.text("");
 
		try {
			const r = await frappe.xcall(
				"tvms.tvms.doctype.tvms_audit_log.tvms_audit_log.search_audit_log",
				this.get_filters(),
			);
			this.render(r);
		} catch (e) {
			$list.html(`<div class="tvms-audit-empty">${__("Failed to load audit log.")}</div>`);
		}
	}
 
	render(result) {
		const events = result.events || [];
		const $list = this.wrapper.find(".tvms-audit-list");
		const $summary = this.wrapper.find(".tvms-audit-summary");
 
		$summary.text(__("{0} event(s) found", [events.length]));
 
		if (!events.length) {
			$list.html(`<div class="tvms-audit-empty">${__("No audit events match the current filters.")}</div>`);
			return;
		}
 
		const rows = events.map(e => {
			const subj = frappe.utils.escape_html(e.subject_name || "");
			const subj_label = frappe.utils.escape_html(e.subject_label || e.subject_name || "");
			const summary = frappe.utils.escape_html(e.summary || "");
			const actor_name = frappe.utils.escape_html(e.actor_name || e.actor || "—");
			const actor_user = frappe.utils.escape_html(e.actor || "");
			const recipient_block = e.recipient
				? `<div class="tvms-audit-recipient">
					<i class="fa fa-arrow-right" style="margin-right:4px;"></i>
					${frappe.utils.escape_html(e.recipient_name || e.recipient)}
					${e.channel ? `<span style="margin-left:8px;font-size:11px;">[${frappe.utils.escape_html(e.channel)}]</span>` : ""}
				   </div>`
				: "";
 
			const subject_link = subj
				? `<a class="tvms-audit-subject-link" data-route='${this._route_for(e.subject_type, subj)}'>${subj}</a>`
				: `<span class="tvms-audit-subject-link">—</span>`;
 
			return `
				<div class="tvms-audit-row" data-name="${frappe.utils.escape_html(e.name)}">
					<div class="tvms-audit-time">${frappe.utils.escape_html(e.timestamp || "")}</div>
					<span class="tvms-audit-event ${e.event_type}">${e.event_type.replace(/_/g, " ")}</span>
					<div class="tvms-audit-body">
						${subject_link}
						<div class="tvms-audit-summary-text">${summary}</div>
						${recipient_block}
					</div>
					<div class="tvms-audit-actor">
						<div class="name">${actor_name}</div>
						<div>${actor_user}</div>
					</div>
				</div>
			`;
		}).join("");
 
		$list.html(rows);
 
		$list.find(".tvms-audit-subject-link[data-route]").on("click", function (e) {
			e.stopPropagation();
			const route = $(this).data("route");
			if (route) frappe.set_route(...route.split("/"));
		});
 
		$list.find(".tvms-audit-row").on("click", function () {
			frappe.set_route("Form", "TVMS Audit Log", $(this).data("name"));
		});
	}
 
	_route_for(subject_type, subject_name) {
		if (!subject_type || !subject_name) return "";
		const slug_map = {
			"Emergency session": "emergency-session",
			"Tvms Notifications": "tvms-notifications",
			"Venue": "venue",
			"Timetable": "timetable",
		};
		const slug = slug_map[subject_type];
		return slug ? `Form/${slug}/${subject_name}` : "";
	}
}