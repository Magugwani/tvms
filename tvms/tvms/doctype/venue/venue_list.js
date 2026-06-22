frappe.listview_settings['Venue'] = {
	onload(listview) {
		listview.page.add_inner_button(__('Dashboard View'), () => {
			frappe.set_route('venue-dashboard');
		});
		listview.page.add_actions_menu_item(
				__("Bulk Print QR Stickers"),
				() => _open_bulk_qr_dialog(listview),
		);
	},
	colwidth: {
		name: 12,
		venue_name: 25,
		venue_code: 12,
		location: 20,
		capacity: 10,
		current_status: 12,
	},

	add_fields: ["venue_name", "venue_code", "location", "capacity", "current_status"],
	get_indicator: (doc) => {
		if (doc.current_status === 'IN-USE') {
			return ["IN USE", "red", `current_status,=,IN-USE`];
		}
		if (doc.current_status === 'BOOKED') {
			return ["Booked", "orange", `current_status,=,BOOKED`];
		}
		return ["Free", "green", `current_status,=,FREE`];
	},
	formatters: {
		current_status(val, df, doc) {
			const classes = {
				'IN-USE': 'badge-danger',
				'BOOKED': 'badge-warning',
				'FREE': 'badge-success',
			};
			const badge = `<span class="badge ${classes[val] || 'badge-secondary'}">${val || 'FREE'}</span>`;
			return badge;
		}
	}

};

function _open_bulk_qr_dialog(listview) {
	const checked = listview.get_checked_items();
	if (!checked.length) {
		frappe.show_alert({
			message: __("Select at least one venue first (check the boxes)."),
			indicator: "orange",
		});
		return;
	}
 
	const venue_codes = checked.map(v => v.name);
 
	const d = new frappe.ui.Dialog({
		title: __("Bulk Print QR Stickers"),
		size: "small",
		fields: [
			{
				fieldtype: "HTML",
				options: `
					<p style="font-size: 13px; color: var(--text-muted); margin: 0 0 12px;">
						${__("Generating QR stickers for {0} selected venue(s).", [venue_codes.length])}
					</p>
				`,
			},
			{
				fieldname: "layout",
				fieldtype: "Select",
				label: __("Layout per A4 page"),
				options: [
					{ label: __("4-up (4 per page · medium)"), value: "4up" },
					{ label: __("8-up (8 per page · small)"),  value: "8up" },
					{ label: __("2-up (2 per page · large)"),  value: "2up" },
				].map(o => `${o.value}\n${o.label}`).join("\n") || "4up\n8up\n2up",
				default: "4up",
				reqd: 1,
			},
			{
				fieldtype: "HTML",
				options: `
					<div style="font-size: 12px; color: var(--text-muted); margin-top: 8px; line-height: 1.5;">
						<strong>${__("Tip")}:</strong>
						${__("4-up balances readability and paper usage. Use 8-up only for office-door stickers; 2-up for visible exterior signs.")}
					</div>
				`,
			},
		],
		primary_action_label: __("Generate PDF"),
		primary_action(values) {
			d.set_primary_action(__("Generating..."), null);
 
			// Build form post — use a real form submission so the browser
			// triggers a file download. frappe.call returns JSON, which is
			// the wrong contract here (we want the PDF binary).
			const form = document.createElement("form");
			form.method = "POST";
			form.action = "/api/method/tvms.tvms.doctype.venue.venue.bulk_print_venue_qr";
			form.target = "_blank";
 
			const append = (name, value) => {
				const input = document.createElement("input");
				input.type = "hidden";
				input.name = name;
				input.value = value;
				form.appendChild(input);
			};
 
			append("venue_codes", JSON.stringify(venue_codes));
			append("layout",      values.layout || "4up");
			// CSRF for Frappe API
			append("csrf_token",  frappe.csrf_token);
 
			document.body.appendChild(form);
			form.submit();
			document.body.removeChild(form);
 
			d.hide();
			frappe.show_alert({
				message: __("PDF will download in a new tab — disable popup blocker if it doesn't."),
				indicator: "blue",
			});
		},
	});
 
	d.show();
}