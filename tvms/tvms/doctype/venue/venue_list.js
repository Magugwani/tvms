frappe.listview_settings['Venue'] = {
	onload(listview) {
		listview.page.add_inner_button(__('Dashboard View'), () => {
			frappe.set_route('venue-dashboard');
		});
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
