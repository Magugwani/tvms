frappe.listview_settings['Emergency session'] = {
	colwidth: {
		name: 15,
		title: 25,
		course: 20,
		venue: 15,
		status: 12,
		start_time: 15,
		end_time: 15,
	},
	add_fields: ["course", "venue", "start_time", "end_time", "status", "created_by"],
	get_indicator: (doc) => {
		const colors = {
			PENDING:   "orange",
			CONFIRMED: "green",
			CANCELLED: "red",
			COMPLETED: "blue",
			EXPIRED:   "grey",
		};
		return [doc.status, colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
