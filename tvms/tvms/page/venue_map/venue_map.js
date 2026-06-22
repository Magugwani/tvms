// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.pages["venue-map"].on_page_load = function (wrapper) {
	frappe.venue_map_page = new TVMSVenueMap(wrapper);
};

class TVMSVenueMap {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Venue Map"),
			single_column: true,
		});

		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.$body = this.wrapper.find(".layout-main-section");

		this.map = null;
		this.markers = {};            // venue_name → mapboxgl.Marker
		this.venues = [];             // last-loaded venue list
		this.selected_venue = null;

		// Default centre — Dar es Salaam. Override in TVMS Settings later
		// by adding campus_lat / campus_lng fields and reading them here.
		this.default_center = [39.208328, -6.792354];
		this.default_zoom = 16;

		this.build();
		this.load();
	}

	build() {
		this.page.set_primary_action(__("Refresh"), () => this.load(), "refresh");
		this.page.add_inner_button(__("Venue List"), () =>
			frappe.set_route("List", "Venue"),
		);
		this.page.add_inner_button(__("Venue Dashboard"), () =>
			frappe.set_route("venue-dashboard"),
		);

		this.$body.html(`
			<div class="venue-map-shell">
				<div class="venue-map-filters">
					<div class="vmf-group">
						<input type="text" id="vmf-search"
						       placeholder="${__('Search venue, building, code...')}"
						       class="form-control input-sm">
					</div>
					<div class="vmf-group">
						<select id="vmf-status" class="form-control input-sm">
							<option value="">${__('All statuses')}</option>
							<option value="FREE">${__('Free')}</option>
							<option value="BOOKED">${__('Booked')}</option>
							<option value="IN-USE">${__('In use')}</option>
							<option value="EXPIRED">${__('Expired')}</option>
						</select>
					</div>
					<div class="vmf-legend">
						<span class="vmf-dot" style="background:#27500A"></span> ${__('Free')}
						<span class="vmf-dot" style="background:#633806"></span> ${__('Booked')}
						<span class="vmf-dot" style="background:#A32D2D"></span> ${__('In use')}
						<span class="vmf-dot" style="background:#5F5E5A"></span> ${__('Expired')}
					</div>
					<div class="vmf-count" id="vmf-count"></div>
				</div>

				<div class="venue-map-body">
					<div id="venue-map-container"></div>
					<div class="venue-map-sidepanel" id="venue-side-panel">
						<div class="vsp-empty">
							<i class="ti ti-map-pin" style="font-size: 32px; color: var(--text-muted);"></i>
							<div style="margin-top: 10px;">${__('Click a marker to see venue details')}</div>
						</div>
					</div>
				</div>
			</div>

			<style>
				.venue-map-shell {
					display: flex;
					flex-direction: column;
					height: calc(100vh - 220px);
					min-height: 540px;
					gap: 10px;
					padding: 12px 0;
				}
				.venue-map-filters {
					display: flex;
					gap: 10px;
					align-items: center;
					padding: 8px 12px;
					background: var(--card-bg);
					border: 1px solid var(--border-color);
					border-radius: 8px;
					flex-wrap: wrap;
				}
				.vmf-group input,
				.vmf-group select { min-width: 180px; }
				.vmf-legend {
					display: flex;
					gap: 12px;
					align-items: center;
					font-size: 12px;
					color: var(--text-muted);
					margin-left: auto;
				}
				.vmf-dot {
					display: inline-block;
					width: 10px;
					height: 10px;
					border-radius: 50%;
					margin-right: 4px;
					vertical-align: -1px;
				}
				.vmf-count {
					font-size: 12px;
					color: var(--text-muted);
					margin-left: 10px;
				}

				.venue-map-body {
					flex: 1;
					display: grid;
					grid-template-columns: 1fr 340px;
					gap: 10px;
					min-height: 0;
				}
				#venue-map-container {
					border: 1px solid var(--border-color);
					border-radius: 8px;
					overflow: hidden;
					background: var(--card-bg);
				}
				.venue-map-sidepanel {
					background: var(--card-bg);
					border: 1px solid var(--border-color);
					border-radius: 8px;
					padding: 16px;
					overflow-y: auto;
				}
				.vsp-empty {
					text-align: center;
					color: var(--text-muted);
					padding: 60px 20px;
					font-size: 13px;
				}
				.vsp-header { margin-bottom: 12px; }
				.vsp-title {
					font-size: 16px;
					font-weight: 500;
					color: var(--text-color);
					margin-bottom: 4px;
				}
				.vsp-code {
					font-family: var(--font-mono);
					font-size: 11px;
					color: var(--text-muted);
				}
				.vsp-status-row {
					display: flex;
					align-items: center;
					gap: 8px;
					margin: 10px 0 14px;
				}
				.vsp-status-pill {
					padding: 3px 10px;
					border-radius: 20px;
					font-size: 11px;
					font-weight: 500;
				}
				.vsp-status-FREE   { background: #EAF3DE; color: #27500A; }
				.vsp-status-BOOKED { background: #FAEEDA; color: #633806; }
				.vsp-status-INUSE  { background: #FCEBEB; color: #A32D2D; }
				.vsp-status-EXPIRED { background: #F1EFE8; color: #5F5E5A; }

				.vsp-grid {
					display: grid;
					grid-template-columns: 1fr 1fr;
					gap: 12px 16px;
					margin-bottom: 16px;
				}
				.vsp-field-label {
					font-size: 10px;
					text-transform: uppercase;
					letter-spacing: 0.04em;
					color: var(--text-muted);
					font-weight: 500;
					margin-bottom: 2px;
				}
				.vsp-field-value {
					font-size: 13px;
					color: var(--text-color);
				}
				.vsp-section-title {
					font-size: 11px;
					text-transform: uppercase;
					letter-spacing: 0.04em;
					color: var(--text-muted);
					font-weight: 500;
					margin: 16px 0 8px;
					border-top: 1px solid var(--border-color);
					padding-top: 12px;
				}
				.vsp-resources {
					display: flex;
					flex-wrap: wrap;
					gap: 4px;
					margin-top: 4px;
				}
				.vsp-tag {
					padding: 2px 8px;
					background: var(--subtle-fg);
					border-radius: 4px;
					font-size: 11px;
				}
				.vsp-nav-notes {
					background: #E6F1FB;
					color: #185FA5;
					padding: 10px 12px;
					border-radius: 6px;
					font-size: 12px;
					line-height: 1.5;
					margin-top: 4px;
				}
				.vsp-actions {
					display: flex;
					gap: 6px;
					margin-top: 18px;
				}
				.vsp-actions .btn { font-size: 12px; }

				.vmap-marker {
					padding: 4px 9px;
					border-radius: 6px;
					color: #fff;
					font-size: 11px;
					font-weight: 500;
					cursor: pointer;
					white-space: nowrap;
					box-shadow: 0 1px 3px rgba(0,0,0,0.3);
					border: 2px solid #fff;
				}
				.vmap-marker:hover { transform: scale(1.05); }
				.vmap-popup .mapboxgl-popup-content {
					padding: 10px 14px;
					font-size: 12px;
					border-radius: 6px;
				}

				@media (max-width: 900px) {
					.venue-map-body { grid-template-columns: 1fr; }
					.venue-map-sidepanel { max-height: 280px; }
				}
			</style>
		`);

		this.$search = this.wrapper.find("#vmf-search");
		this.$status = this.wrapper.find("#vmf-status");
		this.$count = this.wrapper.find("#vmf-count");
		this.$panel = this.wrapper.find("#venue-side-panel");

		this.$search.on("input", frappe.utils.debounce(() => this.load(), 350));
		this.$status.on("change", () => this.load());
	}

	async load() {
		if (!this.map) {
			await this._init_mapbox();
		}

		try {
			const search = this.$search.val();
			const status = this.$status.val();

			const resp = await frappe.xcall(
				"tvms.tvms.doctype.venue.venue.get_venues_for_map",
				{ search: search || null, status: status || null },
			);
			this.venues = resp || [];
			this._render_markers();
			this._update_count();
		} catch (e) {
			frappe.msgprint({
				title: __("Could not load venues"),
				message: __("The venue map could not be loaded. Check the browser console for details."),
				indicator: "red",
			});
		}
	}

	async _init_mapbox() {
		// Inject Mapbox GL CSS once
		if (!document.getElementById("mapbox-gl-css")) {
			const link = document.createElement("link");
			link.id = "mapbox-gl-css";
			link.rel = "stylesheet";
			link.href = "https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.css";
			document.head.appendChild(link);
		}

		// Load Mapbox GL JS via CDN if not present
		if (!window.mapboxgl) {
			await this._load_script("https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.js");
		}

		// Get Mapbox token from TVMS Settings
		const tok = await frappe.xcall(
			"tvms.tvms.doctype.tvms_settings.tvms_settings.get_mapbox_token",
		);
		const token = tok?.token;

		if (!token) {
			this._show_token_missing();
			throw new Error("Mapbox token not configured");
		}
		window.mapboxgl.accessToken = token;

		this.map = new window.mapboxgl.Map({
			container: "venue-map-container",
			style: "mapbox://styles/mapbox/streets-v12",
			center: this.default_center,
			zoom: this.default_zoom,
		});

		this.map.addControl(new window.mapboxgl.NavigationControl());
		this.map.addControl(new window.mapboxgl.FullscreenControl());
		this.map.addControl(new window.mapboxgl.GeolocateControl({
			positionOptions: { enableHighAccuracy: true },
			trackUserLocation: false,
			showUserHeading: false,
		}));
	}

	_show_token_missing() {
		this.wrapper.find("#venue-map-container").html(`
			<div style="
				display: flex; flex-direction: column;
				align-items: center; justify-content: center;
				height: 100%; padding: 40px 20px; text-align: center;
				color: var(--text-muted);
			">
				<i class="ti ti-key" style="font-size: 36px; margin-bottom: 12px; color: #BA7517;"></i>
				<div style="font-size: 14px; font-weight: 500; color: var(--text-color); margin-bottom: 6px;">
					${__("Mapbox token not configured")}
				</div>
				<div style="font-size: 12px; max-width: 320px; line-height: 1.5;">
					${__("Open <strong>TVMS Settings</strong> and paste your Mapbox public token in the field.")}
				</div>
				<a href="/app/tvms-settings" class="btn btn-default btn-sm" style="margin-top: 14px;">
					${__("Open TVMS Settings")}
				</a>
			</div>
		`);
	}

	_render_markers() {
		// Clear old markers
		Object.values(this.markers).forEach(m => m.remove());
		this.markers = {};

		const status_color = {
			"FREE":    "#27500A",
			"BOOKED":  "#633806",
			"IN-USE":  "#A32D2D",
			"EXPIRED": "#5F5E5A",
		};

		if (!this.venues.length) {
			return;
		}

		// Calculate bounds to fit all markers
		const bounds = new window.mapboxgl.LngLatBounds();

		for (const venue of this.venues) {
			const status = venue.current_status || "FREE";
			const color = status_color[status] || status_color["FREE"];

			const el = document.createElement("div");
			el.className = "vmap-marker";
			el.style.background = color;
			el.textContent = venue.venue_name || venue.name;
			el.title = `${venue.venue_name} • ${status}`;

			el.addEventListener("click", () => this._select_venue(venue));

			const popup = new window.mapboxgl.Popup({
				offset: 24,
				className: "vmap-popup",
				closeButton: false,
			}).setHTML(`
				<div style="min-width: 180px;">
					<div style="font-weight: 500; margin-bottom: 4px;">
						${frappe.utils.escape_html(venue.venue_name)}
					</div>
					<div style="color: #666; font-size: 11px;">
						${frappe.utils.escape_html(venue.building_name || "")}
						${venue.building_name && venue.floor_label ? " · " : ""}
						${frappe.utils.escape_html(venue.floor_label || "")}
					</div>
					<div style="margin-top: 6px;">
						<span style="
							padding: 2px 6px; border-radius: 3px;
							background: ${color}; color: #fff;
							font-size: 10px;
						">${status}</span>
						<span style="margin-left: 6px; font-size: 11px; color: #666;">
							Cap: ${venue.capacity || "—"}
						</span>
					</div>
				</div>
			`);

			const marker = new window.mapboxgl.Marker({ element: el })
				.setLngLat([venue.longitude, venue.latitude])
				.setPopup(popup)
				.addTo(this.map);

			this.markers[venue.name] = marker;
			bounds.extend([venue.longitude, venue.latitude]);
		}

		// Auto-fit bounds if we have venues
		if (this.venues.length > 0 && !bounds.isEmpty()) {
			this.map.fitBounds(bounds, {
				padding: 60,
				maxZoom: 18,
				duration: 800,
			});
		}
	}

	_select_venue(venue) {
		this.selected_venue = venue;
		this._render_side_panel();

		// Centre map on this venue
		this.map.flyTo({
			center: [venue.longitude, venue.latitude],
			zoom: Math.max(this.map.getZoom(), 18),
			duration: 600,
		});

		// Open popup
		const marker = this.markers[venue.name];
		if (marker) marker.togglePopup();
	}

	_render_side_panel() {
		const v = this.selected_venue;
		if (!v) {
			this.$panel.html(`
				<div class="vsp-empty">
					<i class="ti ti-map-pin" style="font-size: 32px; color: var(--text-muted);"></i>
					<div style="margin-top: 10px;">${__('Click a marker to see venue details')}</div>
				</div>
			`);
			return;
		}

		const status = (v.current_status || "FREE").replace("-", "");

		const resources = (v.resources || "").split(",")
			.map(r => r.trim()).filter(Boolean);
		const accessibility = (v.accessibility_features || "").split(",")
			.map(r => r.trim()).filter(Boolean);

		this.$panel.html(`
			<div class="vsp-header">
				<div class="vsp-title">${frappe.utils.escape_html(v.venue_name)}</div>
				<div class="vsp-code">${frappe.utils.escape_html(v.name)}</div>
			</div>

			<div class="vsp-status-row">
				<span class="vsp-status-pill vsp-status-${status}">${v.current_status}</span>
				<span style="font-size: 11px; color: var(--text-muted);">
					${frappe.utils.escape_html(v.venue_type || __("General"))}
				</span>
			</div>

			<div class="vsp-grid">
				<div>
					<div class="vsp-field-label">${__("Building")}</div>
					<div class="vsp-field-value">${frappe.utils.escape_html(v.building_name || "—")}</div>
				</div>
				<div>
					<div class="vsp-field-label">${__("Floor")}</div>
					<div class="vsp-field-value">${frappe.utils.escape_html(v.floor_label || "—")}</div>
				</div>
				<div>
					<div class="vsp-field-label">${__("Capacity")}</div>
					<div class="vsp-field-value">${v.capacity || "—"} ${__("people")}</div>
				</div>
				<div>
					<div class="vsp-field-label">${__("Location")}</div>
					<div class="vsp-field-value">${frappe.utils.escape_html(v.location || "—")}</div>
				</div>
			</div>

			${resources.length ? `
				<div class="vsp-section-title">${__("Resources")}</div>
				<div class="vsp-resources">
					${resources.map(r => `<span class="vsp-tag">${frappe.utils.escape_html(r)}</span>`).join("")}
				</div>
			` : ""}

			${accessibility.length ? `
				<div class="vsp-section-title">${__("Accessibility")}</div>
				<div class="vsp-resources">
					${accessibility.map(r => `<span class="vsp-tag">${frappe.utils.escape_html(r)}</span>`).join("")}
				</div>
			` : ""}

			${v.navigation_notes ? `
				<div class="vsp-section-title">${__("How to get there")}</div>
				<div class="vsp-nav-notes">${frappe.utils.escape_html(v.navigation_notes)}</div>
			` : ""}

			<div class="vsp-actions">
				<a class="btn btn-default btn-xs" href="/app/venue/${encodeURIComponent(v.name)}"
				   target="_blank">${__("Open record")}</a>
				<button class="btn btn-default btn-xs" id="vsp-navigate"
				        data-lat="${v.latitude}" data-lng="${v.longitude}"
				        data-name="${frappe.utils.escape_html(v.venue_name)}">
					${__("Get directions")}
				</button>
			</div>
		`);

		this.$panel.find("#vsp-navigate").on("click", function () {
			const lat = $(this).data("lat");
			const lng = $(this).data("lng");
			const name = encodeURIComponent($(this).data("name"));
			// Cross-platform deep link — opens whichever maps app the
			// user has set as default on their device.
			window.open(
				`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&travelmode=walking`,
				"_blank",
			);
		});
	}

	_update_count() {
		const total = this.venues.length;
		this.$count.text(
			total === 1 ? __("{0} venue", [total]) : __("{0} venues", [total])
		);
	}

	_load_script(src) {
		return new Promise((resolve, reject) => {
			const s = document.createElement("script");
			s.src = src;
			s.onload = resolve;
			s.onerror = reject;
			document.head.appendChild(s);
		});
	}
}