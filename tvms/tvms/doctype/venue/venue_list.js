frappe.listview_settings['Venue'] = {
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
		return ["Free", "green", `current_status,=,FREE`];
	},
	formatters: {
		current_status(val, df, doc) {
			const badge = val === 'IN-USE'
				? `<span class="badge badge-danger">${val}</span>`
				: `<span class="badge badge-success">${val || 'FREE'}</span>`;
			return badge;
		}
	}
};
