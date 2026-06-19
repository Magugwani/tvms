// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.ui.form.on("Venue", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Venue Dashboard"), () => {
			frappe.set_route("venue-dashboard");
		}, __("References"));

		frm.add_custom_button(__("View Timetable"), () => {
			frappe.route_options = { venue: frm.doc.name };
			frappe.set_route("tvms-timetable");
		}, __("References"));

// "View on Map" button — only if GPS coordinates are set
		if (frm.doc.latitude && frm.doc.longitude && !frm.is_new()) {
			frm.add_custom_button(__("View on Map"), () => {
				frappe.set_route("venue-map");
			}, __("Location"));
 
			frm.add_custom_button(__("Get Directions"), () => {
				const url = `https://www.google.com/maps/dir/?api=1`
				          + `&destination=${frm.doc.latitude},${frm.doc.longitude}`
				          + `&travelmode=walking`;
				window.open(url, "_blank");
			}, __("Location"));
		}
 
		// Show a small status indicator in the form sidebar
		if (frm.doc.latitude && frm.doc.longitude) {
			frm.dashboard.add_indicator(__("GPS coordinates set"), "green");
		} else if (!frm.is_new()) {
			frm.dashboard.add_indicator(__("No GPS coordinates"), "grey");
		}
				// FR-24 — Print QR Sign for door
		if (!frm.is_new()) {
			frm.add_custom_button(__("Print QR Sign"), () => _print_venue_qr(frm), __("Location"));
		}
	},
});

// helper function to print a QR sign for the venue
function _print_venue_qr(frm) {
	frappe.call({
		method: "tvms.tvms.doctype.venue.venue.get_venue_qr",
		args: { venue: frm.doc.name, size: 320 },
		callback: (r) => {
			if (!r.message) return;
			const qr = r.message;
 
			// Open a new window with a printable layout
			const w = window.open("", "_blank", "width=420,height=560");
			w.document.write(`
				<!DOCTYPE html>
				<html>
				<head>
					<title>QR Sign — ${qr.venue_name}</title>
					<style>
						@page { size: A6; margin: 8mm; }
						body {
							font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
							margin: 0;
							padding: 16px;
							color: #2c2c2a;
							text-align: center;
						}
						.qr-card {
							border: 2px solid #2c2c2a;
							border-radius: 12px;
							padding: 20px 16px;
							max-width: 360px;
							margin: 0 auto;
							background: #fff;
						}
						.qr-venue-name {
							font-size: 22px;
							font-weight: 600;
							margin: 0 0 4px;
							letter-spacing: -0.01em;
						}
						.qr-venue-code {
							font-family: ui-monospace, SFMono-Regular, monospace;
							font-size: 13px;
							color: #888780;
							margin-bottom: 18px;
							letter-spacing: 0.04em;
						}
						.qr-img {
							display: block;
							margin: 0 auto;
							max-width: 100%;
							height: auto;
						}
						.qr-instruction {
							margin-top: 14px;
							font-size: 12px;
							color: #5F5E5A;
							line-height: 1.5;
						}
						.qr-url {
							font-family: ui-monospace, SFMono-Regular, monospace;
							font-size: 10px;
							color: #888780;
							margin-top: 10px;
							word-break: break-all;
						}
						.qr-footer {
							margin-top: 16px;
							font-size: 9px;
							color: #888780;
							text-transform: uppercase;
							letter-spacing: 0.1em;
						}
						.no-print {
							margin-top: 20px;
							text-align: center;
						}
						.no-print button {
							padding: 8px 24px;
							font-size: 14px;
							background: #185FA5;
							color: #fff;
							border: 0;
							border-radius: 6px;
							cursor: pointer;
						}
						@media print {
							.no-print { display: none; }
							body { padding: 0; }
						}
					</style>
				</head>
				<body>
					<div class="qr-card">
						<h1 class="qr-venue-name">${qr.venue_name}</h1>
						<div class="qr-venue-code">${qr.venue_code}</div>
						<img src="${qr.qr_png_base64}" class="qr-img" alt="QR code">
						<div class="qr-instruction">
							${__("Scan this code with your phone camera to get directions")}
						</div>
						<div class="qr-url">${qr.target_url}</div>
						<div class="qr-footer">${__("Tanzania Venue Management System")}</div>
					</div>
					<div class="no-print">
						<button onclick="window.print()">${__("Print")}</button>
					</div>
				</body>
				</html>
			`);
			w.document.close();
		},
	});
}