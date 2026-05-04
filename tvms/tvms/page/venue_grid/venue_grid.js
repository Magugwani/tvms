frappe.pages["venue-grid"].on_page_load = function (wrapper) {
	frappe.venue_grid = new TVMSVenueGrid(wrapper);
};

frappe.pages["venue-grid"].on_page_show = function () {
	if (frappe.venue_grid) {
		frappe.venue_grid.apply_route_options();
		frappe.venue_grid.load();
	}
};

class TVMSVenueGrid {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Venue Grid"),
			single_column: true,
		});

		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.build();
		this.apply_route_options();
		this.load();
	}

	build() {
		this.page.set_primary_action(__("Refresh"), () => this.load(), "refresh");
		this.page.add_inner_button(__("Venue List"), () => frappe.set_route("List", "Venue"));
		this.page.add_inner_button(__("Static Timetable"), () => frappe.set_route("tvms-timetable"));

		this.$body = $(`
			<div class="tvms-venue-grid-page">
				<div class="tvms-venue-filter-bar">
					<input class="form-control" data-filter="search" placeholder="${__("Search venue, code, or location")}">
					<select class="form-control" data-filter="status">
						<option value="">${__("All Statuses")}</option>
						<option value="FREE">${__("Free")}</option>
						<option value="BOOKED">${__("Booked")}</option>
						<option value="IN-USE">${__("In Use")}</option>
						<option value="EXPIRED">${__("Expired")}</option>
					</select>
					<input class="form-control" type="date" data-filter="date">
					<button class="btn btn-primary btn-sm" data-action="apply">${__("Apply")}</button>
				</div>
				<div class="tvms-venue-summary"></div>
				<div class="tvms-venue-grid"></div>
			</div>
		`).appendTo(this.page.main);

		this.inject_styles();
		this.bind_events();
	}

	inject_styles() {
		if ($("#tvms-venue-grid-styles").length) return;

		$(`<style id="tvms-venue-grid-styles">
			.tvms-venue-grid-page { padding-bottom: 24px; }
			.tvms-venue-filter-bar {
				display: grid;
				grid-template-columns: minmax(220px, 1fr) 160px 160px auto;
				gap: 10px;
				align-items: center;
				background: var(--card-bg);
				border: 1px solid var(--border-color);
				border-radius: 8px;
				padding: 12px;
				margin-bottom: 12px;
			}
			.tvms-venue-summary {
				display: flex;
				flex-wrap: wrap;
				gap: 8px;
				margin-bottom: 12px;
			}
			.tvms-venue-pill {
				border: 1px solid var(--border-color);
				border-radius: 999px;
				background: var(--fg-color);
				padding: 5px 10px;
				font-size: 12px;
				color: var(--text-muted);
			}
			.tvms-venue-grid {
				display: grid;
				grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
				gap: 12px;
			}
			.tvms-venue-card {
				background: var(--card-bg);
				border: 1px solid var(--border-color);
				border-radius: 8px;
				padding: 12px;
				min-height: 190px;
			}
			.tvms-venue-card:hover { box-shadow: var(--shadow-sm); }
			.tvms-venue-card-head {
				display: flex;
				justify-content: space-between;
				gap: 10px;
				margin-bottom: 8px;
			}
			.tvms-venue-title {
				font-weight: 700;
				color: var(--text-color);
				font-size: 15px;
			}
			.tvms-venue-subtitle,
			.tvms-booking-meta {
				color: var(--text-muted);
				font-size: 12px;
				line-height: 1.5;
			}
			.tvms-status-badge {
				border-radius: 999px;
				padding: 4px 9px;
				font-size: 11px;
				font-weight: 700;
				height: fit-content;
				white-space: nowrap;
			}
			.tvms-status-free { background: var(--green-100); color: var(--green-700); }
			.tvms-status-booked { background: var(--orange-100); color: var(--orange-700); }
			.tvms-status-in-use { background: var(--red-100); color: var(--red-700); }
			.tvms-status-expired { background: var(--gray-100); color: var(--gray-700); }
			.tvms-booking-list {
				border-top: 1px solid var(--border-color);
				margin-top: 10px;
				padding-top: 10px;
			}
			.tvms-booking {
				border-left: 3px solid var(--blue-500);
				padding: 4px 0 6px 8px;
				margin-bottom: 8px;
			}
			.tvms-booking-title {
				font-weight: 600;
				color: var(--text-color);
				font-size: 13px;
			}
			.tvms-empty {
				grid-column: 1 / -1;
				text-align: center;
				color: var(--text-muted);
				padding: 40px;
				border: 1px solid var(--border-color);
				border-radius: 8px;
				background: var(--card-bg);
			}
			@media (max-width: 780px) {
				.tvms-venue-filter-bar { grid-template-columns: 1fr; }
			}
		</style>`).appendTo("head");
	}

	bind_events() {
		this.$body.find("[data-action='apply']").on("click", () => this.load());
		this.$body.find("[data-filter]").on("change", () => this.load());
		this.$body.find("[data-filter='search']").on("keyup", frappe.utils.debounce(() => this.load(), 300));

		frappe.realtime.on("venue_status_update", () => this.load());
	}

	apply_route_options() {
		if (!frappe.route_options) return;
		Object.entries(frappe.route_options).forEach(([key, value]) => {
			const $field = this.$body.find(`[data-filter='${key}']`);
			if ($field.length) $field.val(value);
		});
		frappe.route_options = null;
	}

	get_filters() {
		const filters = {};
		this.$body.find("[data-filter]").each(function () {
			const $field = $(this);
			filters[$field.data("filter")] = $field.val();
		});
		return filters;
	}

	async load() {
		const filters = this.get_filters();
		this.$body.find(".tvms-venue-grid").html(`<div class="tvms-empty">${__("Loading venues...")}</div>`);

		const venues = await frappe.xcall("tvms.tvms.doctype.venue.venue.get_venue_grid", filters);
		this.render(venues || []);
	}

	render(venues) {
		this.render_summary(venues);
		if (!venues.length) {
			this.$body.find(".tvms-venue-grid").html(`<div class="tvms-empty">${__("No venues found for the selected filters.")}</div>`);
			return;
		}

		this.$body.find(".tvms-venue-grid").html(venues.map((venue) => this.card(venue)).join(""));
		this.$body.find("[data-open-venue]").on("click", function () {
			frappe.set_route("Form", "Venue", $(this).data("open-venue"));
		});
		this.$body.find("[data-open-timetable]").on("click", function () {
			frappe.route_options = { venue: $(this).data("open-timetable") };
			frappe.set_route("tvms-timetable");
		});
	}

	render_summary(venues) {
		const counts = venues.reduce((acc, venue) => {
			const status = venue.current_status || "FREE";
			acc[status] = (acc[status] || 0) + 1;
			return acc;
		}, {});

		this.$body.find(".tvms-venue-summary").html(`
			<span class="tvms-venue-pill">${__("Venues")}: ${venues.length}</span>
			<span class="tvms-venue-pill">${__("Free")}: ${counts.FREE || 0}</span>
			<span class="tvms-venue-pill">${__("Booked")}: ${counts.BOOKED || 0}</span>
			<span class="tvms-venue-pill">${__("In Use")}: ${counts["IN-USE"] || 0}</span>
		`);
	}

	card(venue) {
		const status = venue.current_status || "FREE";
		const badge_class = {
			"FREE": "tvms-status-free",
			"BOOKED": "tvms-status-booked",
			"IN-USE": "tvms-status-in-use",
			"EXPIRED": "tvms-status-expired",
		}[status] || "tvms-status-free";

		const bookings = (venue.bookings || []).map((booking) => `
			<div class="tvms-booking">
				<div class="tvms-booking-title">${frappe.utils.escape_html(booking.title || booking.course_name || booking.name)}</div>
				<div class="tvms-booking-meta">${frappe.utils.escape_html(booking.start_time || "")} - ${frappe.utils.escape_html(booking.end_time || "")}</div>
				<div class="tvms-booking-meta">${frappe.utils.escape_html(booking.source || "")} · ${frappe.utils.escape_html(booking.status || "")}</div>
			</div>
		`).join("");

		return `
			<div class="tvms-venue-card">
				<div class="tvms-venue-card-head">
					<div>
						<div class="tvms-venue-title">${frappe.utils.escape_html(venue.venue_name || venue.name)}</div>
						<div class="tvms-venue-subtitle">${frappe.utils.escape_html(venue.venue_code || venue.name || "")}</div>
					</div>
					<span class="tvms-status-badge ${badge_class}">${frappe.utils.escape_html(status)}</span>
				</div>
				<div class="tvms-venue-subtitle">${frappe.utils.escape_html(venue.location || __("No location"))}</div>
				<div class="tvms-venue-subtitle">${__("Capacity")}: ${frappe.utils.escape_html(venue.capacity || "0")}</div>
				<div class="tvms-venue-subtitle">${__("Resources")}: ${frappe.utils.escape_html(venue.resources || __("None"))}</div>
				<div class="tvms-booking-list">
					${bookings || `<div class="tvms-booking-meta">${__("No current or upcoming bookings.")}</div>`}
				</div>
				<div class="mt-3 flex">
					<button class="btn btn-xs btn-default mr-2" data-open-venue="${frappe.utils.escape_html(venue.name)}">${__("Open Venue")}</button>
					<button class="btn btn-xs btn-default" data-open-timetable="${frappe.utils.escape_html(venue.name)}">${__("Timetable")}</button>
				</div>
			</div>
		`;
	}
}
