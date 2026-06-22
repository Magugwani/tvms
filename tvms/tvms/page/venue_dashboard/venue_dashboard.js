frappe.pages["venue-dashboard"].on_page_load = function (wrapper) {
	frappe.venue_dashboard = new TVMSVenueGrid(wrapper);
};

frappe.pages["venue-dashboard"].on_page_show = function () {
	if (frappe.venue_dashboard) {
		frappe.venue_dashboard.apply_route_options();
		frappe.venue_dashboard.load();
	}
};

class TVMSVenueGrid {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Venue Dashboard"),
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
		this.page.add_inner_button(__("General Timetable"), () => frappe.set_route("tvms-timetable"));

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
				display: grid;
				grid-template-columns: repeat(4, minmax(140px, 1fr));
				gap: 12px;
				margin-bottom: 12px;
			}
			.tvms-stat-card {
				border: 1px solid var(--border-color);
				border-radius: 8px;
				background: var(--card-bg);
				padding: 14px;
				text-align: center;
				cursor: pointer;
			}
			.tvms-stat-card:hover {
				box-shadow: var(--shadow-sm);
			}
			.tvms-stat-card.active {
				border-color: var(--primary);
				box-shadow: 0 0 0 1px var(--primary);
			}
			.tvms-stat-label {
				font-size: 12px;
				color: var(--text-muted);
				margin-bottom: 4px;
			}
			.tvms-stat-value {
				font-size: 22px;
				font-weight: 700;
				color: var(--text-color);
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
				.tvms-venue-summary { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
			}
				.tvms-venue-building-row {
				display: flex;
				align-items: center;
				gap: 6px;
				margin: 4px 0 6px;
				font-size: 13px;
				color: var(--text-color);
				font-weight: 500;
			}
			.tvms-venue-building-row .ti {
				color: var(--text-muted);
				font-size: 14px;
			}
			.tvms-venue-type-tag {
				display: inline-block;
				margin-left: 6px;
				padding: 1px 6px;
				border-radius: 3px;
				background: var(--subtle-fg);
				font-size: 10px;
				color: var(--text-muted);
				text-transform: uppercase;	
				letter-spacing: 0.03em;
			}
			.tvms-gps-indicator {
				color: #40cdf0;
				margin-left: 6px;
				font-size: 12px;
				vertical-align: -1px;
			}
			.tvms-accessibility {
				display: flex;
				align-items: center;
				gap: 4px;
				color: #185FA5;
				font-size: 12px;
			}
			.tvms-accessibility .ti { font-size: 14px; }			
		</style>`).appendTo("head");
	}

	bind_events() {
		this.$body.find("[data-action='apply']").on("click", () => this.load());
		this.$body.find("[data-filter]").on("change", () => this.load());
		this.$body.find("[data-filter='search']").on("keyup", frappe.utils.debounce(() => this.load(), 300));

		frappe.realtime.on("venue_status_update", () => this.load());
				this.$body.on("click", "[data-open-map]", (e) => {
			const venue = $(e.currentTarget).data("open-map");
			frappe.set_route("venue-map");
			// Optional: pass venue name via session so the map can
			// auto-focus on it once loaded
			frappe.utils.set_url_arg("venue", venue);
		});
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
		const summary_filters = Object.assign({}, filters, { status: "" });
		this.$body.find(".tvms-venue-grid").html(`<div class="tvms-empty">${__("Loading venues...")}</div>`);

		const [summary_venues, venues] = await Promise.all([
			frappe.xcall("tvms.tvms.doctype.venue.venue.get_venue_dashboard", summary_filters),
			frappe.xcall("tvms.tvms.doctype.venue.venue.get_venue_dashboard", filters),
		]);
		this.render(venues || [], summary_venues || []);
	}

	render(venues, summary_venues) {
		this.render_summary(summary_venues);
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
		const current_status = this.$body.find("[data-filter='status']").val() || "";
		const cards = [
			{ label: __("Total"), value: venues.length, status: "" },
			{ label: __("Free"), value: counts.FREE || 0, status: "FREE" },
			{ label: __("Booked"), value: counts.BOOKED || 0, status: "BOOKED" },
			{ label: __("In Use"), value: counts["IN-USE"] || 0, status: "IN-USE" },
		];

		this.$body.find(".tvms-venue-summary").html(cards.map((card) => `
			<div class="tvms-stat-card ${current_status === card.status ? "active" : ""}" data-status-filter="${frappe.utils.escape_html(card.status)}">
				<div class="tvms-stat-label">${frappe.utils.escape_html(card.label)}</div>
				<div class="tvms-stat-value">${frappe.utils.escape_html(card.value)}</div>
			</div>
		`).join(""));

		this.$body.find("[data-status-filter]").on("click", (event) => {
			const status = $(event.currentTarget).data("status-filter") || "";
			this.$body.find("[data-filter='status']").val(status);
			this.load();
		});
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

		const floor_display = venue.floor_label
			? frappe.utils.escape_html(venue.floor_label)
			: (venue.floor_number !== undefined && venue.floor_number !== null
				? __("Floor {0}", [venue.floor_number])
				: "");
		const building_floor = [
			venue.building_name ? frappe.utils.escape_html(venue.building_name) : null,
			floor_display || null,
		].filter(Boolean).join(" · ");
 
		const accessibility = (venue.accessibility_features || "").trim();
		const has_gps = venue.has_coordinates || (venue.latitude && venue.longitude);
		const venue_type = venue.venue_type
			? frappe.utils.escape_html(venue.venue_type)
			: "";
 
		return `
			<div class="tvms-venue-card">
				<div class="tvms-venue-card-head">
					<div>
						<div class="tvms-venue-title">${frappe.utils.escape_html(venue.venue_name || venue.name)}</div>
						<div class="tvms-venue-subtitle">
							${frappe.utils.escape_html(venue.venue_code || venue.name || "")}
							${venue_type ? `<span class="tvms-venue-type-tag">${venue_type}</span>` : ""}
							${has_gps ? `<i class="ti ti-map-pin tvms-gps-indicator" title="${__('GPS location available')}"></i>` : ""}
						</div>
					</div>
					<span class="tvms-status-badge ${badge_class}">${frappe.utils.escape_html(status)}</span>
				</div>
 
				${building_floor ? `
					<div class="tvms-venue-building-row">
						<i class="ti ti-building"></i>
						<span>${building_floor}</span>
					</div>
				` : ""}
 
				<div class="tvms-venue-subtitle">${frappe.utils.escape_html(venue.location || __("No location"))}</div>
				<div class="tvms-venue-subtitle">${__("Capacity")}: ${frappe.utils.escape_html(venue.capacity || "0")} ${__("people")}</div>
				<div class="tvms-venue-subtitle">${__("Resources")}: ${frappe.utils.escape_html(venue.resources || __("None"))}</div>
 
				${accessibility ? `
					<div class="tvms-venue-subtitle tvms-accessibility">
						<i class="ti ti-accessible"></i> ${frappe.utils.escape_html(accessibility)}
					</div>
				` : ""}
 
				<div class="tvms-booking-list">
					${bookings || `<div class="tvms-booking-meta">${__("No current or upcoming bookings.")}</div>`}
				</div>
				<div class="mt-3 flex">
					<button class="btn btn-xs btn-default mr-2" data-open-venue="${frappe.utils.escape_html(venue.name)}">${__("Open Venue")}</button>
					<button class="btn btn-xs btn-default mr-2" data-open-timetable="${frappe.utils.escape_html(venue.name)}">${__("Timetable")}</button>
					${has_gps ? `
						<button class="btn btn-xs btn-default" data-open-map="${frappe.utils.escape_html(venue.name)}">
							<i class="ti ti-map"></i> ${__("View on Map")}
						</button>
					` : ""}
				</div>
			</div>
		`;
	}
}
