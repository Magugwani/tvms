// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.ui.form.on("Timetable", {
	refresh(frm) {
		_set_status_indicator(frm);

		frm.add_custom_button(__("Static Timetable"), () => {
			frappe.set_route("tvms-timetable");
		}, __("View"));

		if (frappe.user.has_role(["Department Admin", "System Manager", "Administrator"])) {
			frm.add_custom_button(__("Import from FET CSV"), () => _open_import_dialog(), __("Actions"));
		}
	},
});

function _set_status_indicator(frm) {
	const colors = { SCHEDULED: "blue", COMPLETED: "grey" };
	const color = colors[frm.doc.status];
	if (color) frm.page.set_indicator(__(frm.doc.status), color);
}

function _open_import_dialog() {
	const d = new frappe.ui.Dialog({
		title: __("Import Timetable from FET CSV"),
		fields: [
			{
				fieldname: "semester_start",
				fieldtype: "Date",
				label: __("Semester Start (Monday)"),
				reqd: 1,
				description: __("The Monday of the first week of the semester."),
			},
			{
				fieldname: "semester_end",
				fieldtype: "Date",
				label: __("Semester End"),
				reqd: 1,
				description: __("Last day of the semester (inclusive). Each FET activity repeats for every week in this range."),
			},
			{
				fieldname: "academic_year",
				fieldtype: "Data",
				label: __("Academic Year"),
				placeholder: "e.g. 2026/2027",
			},
			{
				fieldname: "semester",
				fieldtype: "Select",
				label: __("Semester"),
				options: "\nSemester 1\nSemester 2\nTrimester 1\nTrimester 2\nTrimester 3",
			},
			{
				fieldname: "overwrite",
				fieldtype: "Check",
				label: __("Overwrite existing entries for this semester range"),
				description: __("Deletes all Timetable rows within the date range before importing."),
			},
			{ fieldtype: "Section Break" },
			{
				fieldtype: "HTML",
				fieldname: "upload_html",
				options: `<div style="margin-bottom:10px">
					<label class="control-label">${__("Upload CSV File from Device")}</label>
					<div style="margin-top:6px;display:flex;align-items:center;gap:10px">
						<button class="btn btn-default btn-sm" id="tvms-upload-csv-btn" type="button">
							<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
								fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
								stroke-linejoin="round" style="vertical-align:middle;margin-right:5px">
								<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
								<polyline points="17 8 12 3 7 8"/>
								<line x1="12" y1="3" x2="12" y2="15"/>
							</svg>
							${__("Choose File")}
						</button>
						<span id="tvms-upload-csv-name" style="font-size:12px;color:var(--text-muted)">
							${__("No file chosen")}
						</span>
					</div>
					<input type="file" id="tvms-upload-csv-input" accept=".csv,.txt" style="display:none">
					<p class="help-box small text-muted" style="margin-top:6px">
						${__("Selecting a file will fill the CSV text area below automatically.")}
					</p>
				</div>`,
			},
			{
				fieldname: "file_content",
				fieldtype: "Code",
				label: __("FET Activities CSV"),
				options: "Plain Text",
				reqd: 1,
				description: __(
					"Paste the contents of your FET-generated activities CSV file here, "
					+ "or use the upload button above. "
					+ "Both semicolon (;) and comma (,) delimiters are supported."
				),
			},
		],
		primary_action_label: __("Import"),
		primary_action(values) {
			if (!values.semester_end || values.semester_end < values.semester_start) {
				frappe.msgprint(__("Semester end must be after semester start."));
				return;
			}
			d.hide();
			_run_import(values);
		},
	});
	d.show();
	_bind_upload_button(d);
}

function _bind_upload_button(d) {
	const $btn   = d.$wrapper.find("#tvms-upload-csv-btn");
	const $input = d.$wrapper.find("#tvms-upload-csv-input");
	const $name  = d.$wrapper.find("#tvms-upload-csv-name");

	$btn.on("click", () => $input.trigger("click"));

	$input.on("change", function () {
		const file = this.files && this.files[0];
		if (!file) return;

		$name.text(file.name);

		const reader = new FileReader();
		reader.onload = (e) => {
			d.set_value("file_content", e.target.result || "");
		};
		reader.onerror = () => {
			frappe.msgprint(__("Could not read the selected file."));
		};
		reader.readAsText(file);
	});
}

function _run_import(values) {
	frappe.show_progress(__("Importing…"), 0, 100, __("Parsing CSV and expanding across all weeks…"));

	frappe.call({
		method: "tvms.tvms.doctype.timetable.timetable.import_from_fet_csv",
		args: {
			file_content:   values.file_content,
			semester_start: values.semester_start,
			semester_end:   values.semester_end,
			academic_year:  values.academic_year || null,
			semester:       values.semester      || null,
			overwrite:      values.overwrite ? 1 : 0,
		},
		callback(r) {
			frappe.hide_progress();
			if (!r.exc && r.message) {
				_show_import_result(r.message);
			}
		},
		error() {
			frappe.hide_progress();
		},
	});
}

function _show_import_result(result) {
	const { batch_id, semester_start, semester_end, num_weeks, total_activities,
		imported, skipped, warnings, errors, error_details, warning_details } = result;

	let body = `
		<table class="table table-bordered" style="margin-top:8px">
			<tr><th>${__("Batch ID")}</th><td>${batch_id}</td></tr>
			<tr><th>${__("Semester")}</th><td>${semester_start} → ${semester_end} (${num_weeks} weeks)</td></tr>
			<tr><th>${__("Total Session Slots")}</th><td>${total_activities}</td></tr>
			<tr><th>${__("Imported")}</th><td class="text-success">${imported}</td></tr>
			<tr><th>${__("Duplicates Skipped")}</th><td class="text-warning">${skipped}</td></tr>
			<tr><th>${__("Warnings")}</th><td class="${warnings > 0 ? "text-warning" : ""}">${warnings}</td></tr>
			<tr><th>${__("Errors")}</th><td class="${errors > 0 ? "text-danger" : ""}">${errors}</td></tr>
		</table>`;

	if (warning_details && warning_details.length) {
		body += `<h5 style="margin-top:12px">${__("Warnings (first 50)")}</h5><ul>`;
		warning_details.forEach(w => {
			body += `<li><strong>${__("Row")} ${w.row}:</strong> ${(w.warnings || []).join("; ")}</li>`;
		});
		body += "</ul>";
	}

	if (error_details && error_details.length) {
		body += `<h5 style="margin-top:12px">${__("Errors (first 50)")}</h5><ul>`;
		error_details.forEach(e => {
			body += `<li><strong>${__("Row")} ${e.row}:</strong> ${e.error}</li>`;
		});
		body += "</ul>";
	}

	frappe.msgprint({
		title: __("Import Complete"),
		message: body,
		indicator: errors > 0 ? "orange" : "green",
		wide: true,
	});

	if (imported > 0 && frappe.views && frappe.views.list_view) {
		frappe.views.list_view.refresh();
	}

	if (imported > 0) {
		frappe.confirm(
			__("Open the static timetable grid now?"),
			() => frappe.set_route("tvms-timetable")
		);
	}
}
