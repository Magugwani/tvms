// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.pages["tvms-enrollment"].on_page_load = function (wrapper) {
	frappe.tvms_enrollment_page = new TVMSEnrollmentPage(wrapper);
};

class TVMSEnrollmentPage {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("TVMS Enrollment"),
			single_column: true,
		});

		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.$body = this.wrapper.find(".layout-main-section");

		this.current_tab    = "import";
		this.import_kind    = "student";   // "student" or "lecturer"
		this.csv_content    = null;
		this.csv_filename   = null;
		this.preview_result = null;

		this.individual_kind = "student";

		this.build();
		this.show_tab("import");
	}

	build() {
		this.page.set_primary_action(__("Import History"), () =>
			frappe.set_route("List", "TVMS Enrollment Batch"), "history"
		);

		this.$body.html(`
			<div class="tve-page">
				<div class="tve-tabs">
					<button class="tve-tab active" data-tab="import">
						<i class="fa fa-upload"></i> ${__("Bulk Import")}
					</button>
					<button class="tve-tab" data-tab="individual">
						<i class="fa fa-user-plus"></i> ${__("Add Individual")}
					</button>
					<button class="tve-tab" data-tab="manage">
						<i class="fa fa-users"></i> ${__("Manage Users")}
					</button>
				</div>

				<div class="tve-tab-content" data-content="import"></div>
				<div class="tve-tab-content" data-content="individual" style="display:none;"></div>
				<div class="tve-tab-content" data-content="manage" style="display:none;"></div>
			</div>

			<style>
				.tve-page { padding: 12px 0; }

				.tve-tabs {
					display: flex; gap: 4px;
					border-bottom: 1px solid var(--border-color);
					margin-bottom: 20px;
				}
				.tve-tab {
					background: transparent; border: 0;
					padding: 10px 16px; font-size: 13px;
					color: var(--text-muted); cursor: pointer;
					border-bottom: 2px solid transparent;
					transition: all 0.15s;
				}
				.tve-tab:hover { color: var(--text-color); }
				.tve-tab.active {
					color: var(--text-color); font-weight: 500;
					border-bottom-color: #1976d2;
				}
				.tve-tab .fa { margin-right: 6px; }

				.tve-card {
					background: var(--card-bg);
					border: 1px solid var(--border-color);
					border-radius: 8px;
					padding: 20px; margin-bottom: 16px;
				}

				.tve-section-title {
					font-size: 14px; font-weight: 500;
					margin-bottom: 12px; color: var(--text-color);
				}

				.tve-template-row {
					display: flex; gap: 10px; flex-wrap: wrap;
					margin-bottom: 14px;
				}

				.tve-kind-switcher {
					display: inline-flex;
					border: 1px solid var(--border-color);
					border-radius: 6px; overflow: hidden;
					margin-bottom: 16px;
				}
				.tve-kind-btn {
					padding: 8px 18px; background: transparent;
					border: 0; cursor: pointer; font-size: 13px;
					color: var(--text-muted);
				}
				.tve-kind-btn.active {
					background: #1976d2; color: #fff;
				}

				.tve-upload-area {
					border: 2px dashed var(--border-color);
					border-radius: 8px;
					padding: 40px 20px;
					text-align: center;
					transition: background 0.15s;
					cursor: pointer;
				}
				.tve-upload-area:hover { background: var(--subtle-fg); }
				.tve-upload-area.has-file {
					border-style: solid;
					border-color: #1976d2;
					background: #E6F1FB;
				}
				.tve-upload-icon {
					font-size: 32px; color: var(--text-muted);
					margin-bottom: 8px;
				}
				.tve-upload-hint {
					font-size: 12px; color: var(--text-muted);
					margin-top: 6px;
				}
				.tve-filename {
					font-family: var(--font-mono);
					font-size: 13px; margin-top: 8px;
				}

				.tve-options { margin: 16px 0; }
				.tve-checkbox {
					display: block; margin-bottom: 8px;
					font-size: 13px; cursor: pointer;
				}
				.tve-checkbox input { margin-right: 8px; vertical-align: -2px; }
				.tve-warn {
					font-size: 11px; color: #A32D2D;
					margin-left: 24px; line-height: 1.4;
				}

				.tve-preview-summary {
					display: grid;
					grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
					gap: 10px; margin: 16px 0;
				}
				.tve-stat {
					padding: 12px;
					border: 1px solid var(--border-color);
					border-radius: 6px;
					text-align: center;
				}
				.tve-stat-num {
					font-size: 22px; font-weight: 500;
					line-height: 1; margin-bottom: 3px;
				}
				.tve-stat-label {
					font-size: 11px; color: var(--text-muted);
					text-transform: uppercase; letter-spacing: 0.04em;
				}
				.tve-stat.success .tve-stat-num { color: #27500A; }
				.tve-stat.danger  .tve-stat-num { color: #A32D2D; }

				.tve-preview-table {
					width: 100%; font-size: 12px;
					border-collapse: collapse; margin-top: 8px;
				}
				.tve-preview-table th {
					background: var(--subtle-fg);
					padding: 8px 10px; text-align: left;
					font-size: 11px; text-transform: uppercase;
					letter-spacing: 0.04em; color: var(--text-muted);
					font-weight: 500;
				}
				.tve-preview-table td {
					padding: 8px 10px;
					border-bottom: 1px solid var(--border-color);
				}
				.tve-preview-table .action-CREATE {
					color: #27500A; font-weight: 500;
				}
				.tve-preview-table .action-UPDATE {
					color: #BA7517; font-weight: 500;
				}

				.tve-errors {
					margin-top: 14px;
					max-height: 200px; overflow-y: auto;
					border: 1px solid #FCEBEB;
					border-radius: 6px;
					background: #FDF6F6;
				}
				.tve-error-row {
					padding: 8px 12px;
					font-size: 12px;
					border-bottom: 1px solid #FCEBEB;
					color: #791F1F;
				}
				.tve-error-row .row-num {
					display: inline-block;
					min-width: 50px;
					font-family: var(--font-mono);
					color: #A32D2D;
				}
				.tve-error-row .field {
					font-weight: 500;
					margin-right: 8px;
				}

				.tve-action-row {
					margin-top: 16px;
					display: flex; gap: 10px;
					align-items: center;
				}
				.tve-progress {
					display: none;
					margin: 16px 0;
					padding: 12px 16px;
					background: #E6F1FB;
					border-radius: 6px;
					font-size: 13px;
					color: #185FA5;
				}
				.tve-progress.show { display: block; }
				.tve-progress .spinner {
					display: inline-block;
					width: 14px; height: 14px;
					border: 2px solid #B5D4F4;
					border-top-color: #185FA5;
					border-radius: 50%;
					animation: tve-spin 0.8s linear infinite;
					vertical-align: -3px;
					margin-right: 8px;
				}
				@keyframes tve-spin {
					to { transform: rotate(360deg); }
				}

				.tve-result {
					margin-top: 16px;
					padding: 14px 18px;
					border-radius: 6px;
					font-size: 13px;
				}
				.tve-result.success { background: #EAF3DE; color: #27500A; }
				.tve-result.partial { background: #FAEEDA; color: #633806; }
				.tve-result.failed  { background: #FCEBEB; color: #791F1F; }
				.tve-result-summary {
					font-weight: 500; margin-bottom: 6px;
				}

				/* Individual form */
				.tve-form-row {
					display: grid;
					grid-template-columns: 1fr 1fr;
					gap: 14px;
					margin-bottom: 12px;
				}
				.tve-form-field { display: flex; flex-direction: column; }
				.tve-form-field label {
					font-size: 11px; color: var(--text-muted);
					margin-bottom: 4px; text-transform: uppercase;
					letter-spacing: 0.04em; font-weight: 500;
				}
				.tve-form-field label .req { color: #A32D2D; }
				.tve-form-field input,
				.tve-form-field select {
					padding: 7px 9px;
					border: 1px solid var(--border-color);
					border-radius: 4px;
					background: #fff;
					font-size: 13px;
				}
				.tve-year-preview {
					background: #E1F5EE; color: #085041;
					padding: 8px 12px; border-radius: 4px;
					font-size: 12px; margin: 8px 0;
				}

				/* Manage users */
				.tve-filters-row {
					display: flex; gap: 10px; flex-wrap: wrap;
					margin-bottom: 14px;
				}
				.tve-filters-row > * { min-width: 140px; }
				.tve-users-table {
					width: 100%; border-collapse: collapse;
					font-size: 13px;
				}
				.tve-users-table th {
					background: var(--subtle-fg);
					padding: 10px 12px; text-align: left;
					font-size: 11px; text-transform: uppercase;
					font-weight: 500; color: var(--text-muted);
					letter-spacing: 0.04em;
				}
				.tve-users-table td {
					padding: 10px 12px;
					border-bottom: 1px solid var(--border-color);
					vertical-align: top;
				}
				.tve-users-table tr {
					cursor: pointer;
				}
				.tve-users-table tr:hover { background: var(--subtle-fg); }
				.tve-name { font-weight: 500; }
				.tve-email-small {
					font-size: 11px; color: var(--text-muted);
				}
				.tve-role-badge {
					display: inline-block; padding: 2px 8px;
					border-radius: 3px; font-size: 10px;
					font-weight: 500; text-transform: uppercase;
					letter-spacing: 0.04em;
					margin-right: 4px;
				}
				.tve-role-Student { background: #E6F1FB; color: #185FA5; }
				.tve-role-Lecturer { background: #EEEDFE; color: #3C3489; }
				.tve-role-CR { background: #FBEAF0; color: #72243E; }
				.tve-role-DA { background: #FAEEDA; color: #633806; }

				.tve-status-badge {
					display: inline-block; padding: 2px 8px;
					border-radius: 10px; font-size: 11px;
					font-weight: 500;
				}
				.tve-status-enabled  { background: #DCF1E8; color: #0F6E56; }
				.tve-status-disabled { background: #F1EFE8; color: #5F5E5A; }

				/* Side panel */
				.tve-side-panel {
					position: fixed;
					top: 0; right: 0;
					width: 420px; height: 100vh;
					background: #fff;
					border-left: 1px solid var(--border-color);
					box-shadow: -8px 0 24px rgba(0,0,0,0.08);
					z-index: 1000;
					overflow-y: auto;
					transform: translateX(100%);
					transition: transform 0.25s;
				}
				.tve-side-panel.open { transform: translateX(0); }
				.tve-sp-header {
					padding: 18px 20px;
					border-bottom: 1px solid var(--border-color);
					display: flex; align-items: center; justify-content: space-between;
				}
				.tve-sp-close {
					background: transparent; border: 0;
					font-size: 22px; cursor: pointer;
					color: var(--text-muted);
				}
				.tve-sp-body { padding: 16px 20px; }
				.tve-sp-section {
					margin-bottom: 18px;
				}
				.tve-sp-section-title {
					font-size: 11px; text-transform: uppercase;
					letter-spacing: 0.05em; color: var(--text-muted);
					margin-bottom: 8px; font-weight: 500;
				}
				.tve-sp-field {
					display: flex; justify-content: space-between;
					padding: 6px 0; font-size: 13px;
					border-bottom: 1px solid var(--border-color);
				}
				.tve-sp-field-label { color: var(--text-muted); }
				.tve-sp-actions {
					display: flex; flex-direction: column;
					gap: 8px; margin-top: 12px;
				}
				.tve-sp-actions .btn { text-align: left; }

				.tve-empty {
					padding: 40px 20px; text-align: center;
					color: var(--text-muted); font-size: 13px;
				}
			</style>
		`);

		// Tab switching
		this.wrapper.find(".tve-tab").on("click", (e) => {
			const tab = $(e.currentTarget).data("tab");
			this.show_tab(tab);
		});
	}

	show_tab(tab) {
		this.current_tab = tab;
		this.wrapper.find(".tve-tab").removeClass("active");
		this.wrapper.find(`.tve-tab[data-tab="${tab}"]`).addClass("active");
		this.wrapper.find(".tve-tab-content").hide();
		this.wrapper.find(`.tve-tab-content[data-content="${tab}"]`).show();

		if (tab === "import")     this._render_import_tab();
		if (tab === "individual") this._render_individual_tab();
		if (tab === "manage")     this._render_manage_tab();
	}

	// =================================================================
	// TAB 1 — BULK IMPORT
	// =================================================================

	_render_import_tab() {
		const $tab = this.wrapper.find('.tve-tab-content[data-content="import"]');
		$tab.html(`
			<div class="tve-card">
				<div class="tve-section-title">${__("1. Download template")}</div>
				<div class="tve-template-row">
					<button class="btn btn-default btn-sm" id="tve-dl-student">
						<i class="fa fa-download"></i> ${__("Student Template")}
					</button>
					<button class="btn btn-default btn-sm" id="tve-dl-lecturer">
						<i class="fa fa-download"></i> ${__("Lecturer Template")}
					</button>
				</div>
				<p style="font-size: 11px; color: var(--text-muted); margin: 0;">
					${__("Fill in the template with your registrar's export, then upload below.")}
				</p>
			</div>

			<div class="tve-card">
				<div class="tve-section-title">${__("2. Choose import type")}</div>
				<div class="tve-kind-switcher" id="tve-import-kind">
					<button class="tve-kind-btn active" data-kind="student">
						${__("Students")}
					</button>
					<button class="tve-kind-btn" data-kind="lecturer">
						${__("Lecturers")}
					</button>
				</div>

				<div class="tve-section-title" style="margin-top: 12px;">
					${__("3. Upload CSV")}
				</div>
				<div class="tve-upload-area" id="tve-upload">
					<div class="tve-upload-icon"><i class="fa fa-file-text-o"></i></div>
					<div>${__("Click to choose a CSV file")}</div>
					<div class="tve-upload-hint">${__("or drag and drop")}</div>
					<div class="tve-filename"></div>
				</div>
				<input type="file" id="tve-file-input" accept=".csv" style="display:none;">

				<div class="tve-options">
					<label class="tve-checkbox">
						<input type="checkbox" id="tve-sync-mode">
						${__("Sync mode")}
					</label>
					<div class="tve-warn">
						${__("Disables users in this role who are NOT in the uploaded CSV. Useful for end-of-semester cleanup. Use carefully.")}
					</div>
					<label class="tve-checkbox" style="margin-top: 10px;">
						<input type="checkbox" id="tve-welcome" checked>
						${__("Send welcome emails to new users")}
					</label>
				</div>

				<div class="tve-action-row">
					<button class="btn btn-default" id="tve-preview-btn" disabled>
						<i class="fa fa-eye"></i> ${__("Validate CSV")}
					</button>
					<button class="btn btn-primary" id="tve-import-btn" disabled>
						<i class="fa fa-cloud-upload"></i> ${__("Run Import")}
					</button>
				</div>

				<div class="tve-progress" id="tve-progress">
					<span class="spinner"></span>
					<span id="tve-progress-text">${__("Importing...")}</span>
				</div>

				<div id="tve-result"></div>
			</div>

			<div class="tve-card" id="tve-preview-card" style="display:none;">
				<div class="tve-section-title">${__("Validation preview")}</div>
				<div class="tve-preview-summary" id="tve-preview-stats"></div>
				<div id="tve-preview-table-wrap"></div>
				<div id="tve-errors-wrap"></div>
			</div>
		`);

		// Template downloads
		$tab.find("#tve-dl-student").on("click", () => this._download_template("student"));
		$tab.find("#tve-dl-lecturer").on("click", () => this._download_template("lecturer"));

		// Kind switcher
		$tab.find(".tve-kind-btn").on("click", (e) => {
			$tab.find(".tve-kind-btn").removeClass("active");
			$(e.currentTarget).addClass("active");
			this.import_kind = $(e.currentTarget).data("kind");
			this._reset_import_state();
		});

		// File upload
		const $upload = $tab.find("#tve-upload");
		const $input = $tab.find("#tve-file-input");

		$upload.on("click", () => $input.click());

		$upload.on("dragover", (e) => {
			e.preventDefault();
			$upload.css("background", "var(--subtle-fg)");
		});
		$upload.on("dragleave", () => $upload.css("background", ""));
		$upload.on("drop", (e) => {
			e.preventDefault();
			$upload.css("background", "");
			if (e.originalEvent.dataTransfer.files.length) {
				this._handle_file(e.originalEvent.dataTransfer.files[0]);
			}
		});

		$input.on("change", (e) => {
			if (e.target.files.length) {
				this._handle_file(e.target.files[0]);
			}
		});

		// Validate + Import buttons
		$tab.find("#tve-preview-btn").on("click", () => this._run_preview());
		$tab.find("#tve-import-btn").on("click", () => this._run_import());
	}

	_download_template(kind) {
		// Build CSV content client-side from headers — the templates ship
		// with the app but we redirect to the API/static path here.
		const headers = kind === "student"
			? "FirstName,LastName,IndexNumber,Gender,DateOfBirth,Email,Phone,ProgrammeCode,AcademicYear"
			: "FirstName,LastName,IDNumber,Email,Phone,DepartmentCode,StaffNumber";

		const example = kind === "student"
			? "\nJohn,Doe,NIT/BIT/2023/2157,Male,2003-05-12,john.doe@nit.ac.tz,+255712345678,BIT,2025/2026"
			: "\nEdward,Mwambage,19851012-12345-67890-12,edward.m@nit.ac.tz,+255712345701,CCT,STAFF-001";

		const blob = new Blob([headers + example], { type: "text/csv" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `${kind}s_template.csv`;
		a.click();
		URL.revokeObjectURL(url);
	}

	_handle_file(file) {
		if (!file.name.toLowerCase().endsWith(".csv")) {
			frappe.msgprint({
				title: __("Wrong file type"),
				message: __("Please upload a .csv file"),
				indicator: "red",
			});
			return;
		}

		this.csv_filename = file.name;
		const reader = new FileReader();
		reader.onload = (e) => {
			this.csv_content = e.target.result;
			const $upload = this.wrapper.find("#tve-upload");
			$upload.addClass("has-file");
			$upload.find(".tve-filename").text(file.name);
			this.wrapper.find("#tve-preview-btn").prop("disabled", false);
		};
		reader.readAsText(file);
	}

	_reset_import_state() {
		this.csv_content = null;
		this.csv_filename = null;
		this.preview_result = null;
		this.wrapper.find("#tve-upload").removeClass("has-file");
		this.wrapper.find("#tve-upload .tve-filename").empty();
		this.wrapper.find("#tve-preview-btn, #tve-import-btn").prop("disabled", true);
		this.wrapper.find("#tve-preview-card").hide();
		this.wrapper.find("#tve-result").empty();
	}

	async _run_preview() {
		if (!this.csv_content) return;

		this.wrapper.find("#tve-preview-btn").prop("disabled", true).text(__("Validating..."));

		try {
			const method = this.import_kind === "student"
				? "tvms.tvms.api.enrollment.preview_student_csv"
				: "tvms.tvms.api.enrollment.preview_lecturer_csv";  // For lecturer, no preview - go straight to import
			// Note: lecturer preview not yet built; for now we do basic client-side validation
			// and use the same preview endpoint (will be extended later for lecturer-specific
			// validation if needed).

			const result = await frappe.xcall(method, { csv_content: this.csv_content });
			this.preview_result = result;
			this._render_preview(result);
			this.wrapper.find("#tve-import-btn").prop("disabled", result.valid === 0);
		} catch (e) {
			frappe.msgprint({
				title: __("Validation failed"),
				message: e.message || __("Could not validate the CSV file."),
				indicator: "red",
			});
		} finally {
			this.wrapper.find("#tve-preview-btn").prop("disabled", false).html(
				`<i class="fa fa-eye"></i> ${__("Validate CSV")}`
			);
		}
	}

	_render_preview(result) {
		const $card = this.wrapper.find("#tve-preview-card");
		$card.show();

		// Summary stats
		this.wrapper.find("#tve-preview-stats").html(`
			<div class="tve-stat">
				<div class="tve-stat-num">${result.total}</div>
				<div class="tve-stat-label">${__("Total Rows")}</div>
			</div>
			<div class="tve-stat success">
				<div class="tve-stat-num">${result.valid}</div>
				<div class="tve-stat-label">${__("Valid")}</div>
			</div>
			<div class="tve-stat ${result.error_count > 0 ? 'danger' : ''}">
				<div class="tve-stat-num">${result.error_count}</div>
				<div class="tve-stat-label">${__("Errors")}</div>
			</div>
		`);

		// Preview table
		if (result.preview && result.preview.length) {
			const rows = result.preview.map(p => `
				<tr>
					<td>${frappe.utils.escape_html(p.email)}</td>
					<td>${frappe.utils.escape_html(p.full_name)}</td>
					<td>${frappe.utils.escape_html(p.index || "")}</td>
					<td>${frappe.utils.escape_html(p.program || "—")}</td>
					<td>${frappe.utils.escape_html(p.year_level || "—")}</td>
					<td class="action-${p.exists}">${p.exists}</td>
				</tr>
			`).join("");

			this.wrapper.find("#tve-preview-table-wrap").html(`
				<table class="tve-preview-table">
					<thead>
						<tr>
							<th>${__("Email")}</th>
							<th>${__("Name")}</th>
							<th>${__("Index")}</th>
							<th>${__("Program")}</th>
							<th>${__("Year")}</th>
							<th>${__("Action")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
				<p style="font-size: 11px; color: var(--text-muted); margin: 8px 0 0;">
					${__("Showing first {0} of {1} valid rows", [result.preview.length, result.valid])}
				</p>
			`);
		}

		// Error list
		if (result.errors && result.errors.length) {
			const errors_html = result.errors.map(err => `
				<div class="tve-error-row">
					<span class="row-num">Row ${err.row}</span>
					<span class="field">${frappe.utils.escape_html(err.field)}:</span>
					${frappe.utils.escape_html(err.message)}
				</div>
			`).join("");

			this.wrapper.find("#tve-errors-wrap").html(`
				<div style="margin-top: 14px;">
					<div style="font-size: 12px; color: var(--text-muted); margin-bottom: 6px;">
						${__("Validation errors")} ${result.error_count > result.errors.length
							? `(${__("showing first {0}", [result.errors.length])})`
							: ""}
					</div>
					<div class="tve-errors">${errors_html}</div>
				</div>
			`);
		} else {
			this.wrapper.find("#tve-errors-wrap").empty();
		}
	}

	async _run_import() {
		if (!this.csv_content) return;
		if (!this.preview_result || this.preview_result.valid === 0) {
			frappe.msgprint(__("Run validation first"));
			return;
		}

		const sync_mode = this.wrapper.find("#tve-sync-mode").prop("checked") ? 1 : 0;
		const welcome   = this.wrapper.find("#tve-welcome").prop("checked") ? 1 : 0;

		if (sync_mode) {
			const ok = await new Promise((resolve) =>
				frappe.confirm(
					__("Sync mode will DISABLE users in this role who are not in your CSV. Continue?"),
					() => resolve(true), () => resolve(false),
				)
			);
			if (!ok) return;
		}

		this.wrapper.find("#tve-preview-btn, #tve-import-btn").prop("disabled", true);
		this.wrapper.find("#tve-progress").addClass("show");
		this.wrapper.find("#tve-progress-text").text(
			__("Importing {0} rows...", [this.preview_result.total])
		);

		try {
			const method = this.import_kind === "student"
				? "tvms.tvms.api.enrollment.import_students"
				: "tvms.tvms.api.enrollment.import_lecturers";

			const result = await frappe.xcall(method, {
				csv_content: this.csv_content,
				sync_mode, send_welcome_emails: welcome,
			});

			this._render_import_result(result);
		} catch (e) {
			this.wrapper.find("#tve-result").html(`
				<div class="tve-result failed">
					<div class="tve-result-summary">${__("Import failed")}</div>
					<div>${frappe.utils.escape_html(e.message || "Unknown error")}</div>
				</div>
			`);
		} finally {
			this.wrapper.find("#tve-progress").removeClass("show");
			this.wrapper.find("#tve-preview-btn, #tve-import-btn").prop("disabled", false);
		}
	}

	_render_import_result(result) {
		const cls = result.status === "COMPLETED" ? "success"
			: result.status === "PARTIAL" ? "partial" : "failed";

		this.wrapper.find("#tve-result").html(`
			<div class="tve-result ${cls}">
				<div class="tve-result-summary">${frappe.utils.escape_html(result.summary)}</div>
				<div style="font-size: 12px; margin-top: 4px;">
					${__("Batch ID")}: <a href="/app/tvms-enrollment-batch/${result.batch_name}">
						${result.batch_name}
					</a>
				</div>
			</div>
		`);
	}

	// =================================================================
	// TAB 2 — ADD INDIVIDUAL
	// =================================================================

	_render_individual_tab() {
		const $tab = this.wrapper.find('.tve-tab-content[data-content="individual"]');
		$tab.html(`
			<div class="tve-card">
				<div class="tve-kind-switcher" id="tve-ind-kind">
					<button class="tve-kind-btn active" data-kind="student">
						${__("Student")}
					</button>
					<button class="tve-kind-btn" data-kind="lecturer">
						${__("Lecturer")}
					</button>
				</div>

				<div id="tve-ind-form"></div>
			</div>
		`);

		$tab.find(".tve-kind-btn").on("click", (e) => {
			$tab.find(".tve-kind-btn").removeClass("active");
			$(e.currentTarget).addClass("active");
			this.individual_kind = $(e.currentTarget).data("kind");
			this._render_individual_form();
		});

		this._render_individual_form();
	}

	async _render_individual_form() {
		const $form = this.wrapper.find("#tve-ind-form");

		if (this.individual_kind === "student") {
			// Fetch programs for dropdown
			const programs = await this._get_programs();
			const program_opts = programs.map(p =>
				`<option value="${frappe.utils.escape_html(p.name)}">${frappe.utils.escape_html(p.program_name || p.name)}</option>`
			).join("");

			$form.html(`
				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("First Name")} <span class="req">*</span></label>
						<input type="text" id="ind-first">
					</div>
					<div class="tve-form-field">
						<label>${__("Last Name")} <span class="req">*</span></label>
						<input type="text" id="ind-last">
					</div>
				</div>

				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("Email")} <span class="req">*</span></label>
						<input type="email" id="ind-email">
					</div>
					<div class="tve-form-field">
						<label>${__("Phone")}</label>
						<input type="text" id="ind-phone" placeholder="+255...">
					</div>
				</div>

				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("Index Number")} <span class="req">*</span></label>
						<input type="text" id="ind-index" placeholder="NIT/BIT/2023/2157">
					</div>
					<div class="tve-form-field">
						<label>${__("Academic Year")} <span class="req">*</span></label>
						<input type="text" id="ind-ay" placeholder="2025/2026">
					</div>
				</div>

				<div class="tve-year-preview" id="ind-year-preview" style="display:none;"></div>

				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("Programme")} <span class="req">*</span></label>
						<select id="ind-program">
							<option value="">${__("Select programme...")}</option>
							${program_opts}
						</select>
					</div>
					<div class="tve-form-field">
						<label>${__("Gender")}</label>
						<select id="ind-gender">
							<option value="">—</option>
							<option value="Male">${__("Male")}</option>
							<option value="Female">${__("Female")}</option>
							<option value="Other">${__("Other")}</option>
						</select>
					</div>
				</div>

				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("Date of Birth")}</label>
						<input type="date" id="ind-dob">
					</div>
					<div class="tve-form-field"></div>
				</div>

				<label class="tve-checkbox">
					<input type="checkbox" id="ind-welcome" checked>
					${__("Send welcome email")}
				</label>

				<div class="tve-action-row">
					<button class="btn btn-primary" id="ind-save">
						${__("Create Student")}
					</button>
				</div>
			`);

			// Live year-of-study preview
			const update_year_preview = () => {
				const idx = $form.find("#ind-index").val();
				const ay  = $form.find("#ind-ay").val();
				const $preview = $form.find("#ind-year-preview");

				const idx_match = idx.match(/\/(\d{4})\//);
				const ay_match = ay.match(/(\d{4})/);

				if (idx_match && ay_match) {
					const entry = parseInt(idx_match[1]);
					const start = parseInt(ay_match[1]);
					const yos = Math.max(1, Math.min(start - entry + 1, 6));
					const labels = {
						1: "First Year (1)", 2: "Second Year (2)",
						3: "Third Year (3)", 4: "Fourth Year (4)",
						5: "Fifth Year (5)", 6: "Sixth Year (6)",
					};
					$preview.text(__("Computed year of study: {0}", [labels[yos]])).show();
				} else {
					$preview.hide();
				}
			};

			$form.find("#ind-index, #ind-ay").on("input", update_year_preview);

			$form.find("#ind-save").on("click", () => this._save_individual_student());
		}
		else {
			// Lecturer form
			const departments = await this._get_departments();
			const dept_opts = departments.map(d =>
				`<option value="${frappe.utils.escape_html(d.name)}">${frappe.utils.escape_html(d.department_name || d.name)}</option>`
			).join("");

			$form.html(`
				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("First Name")} <span class="req">*</span></label>
						<input type="text" id="ind-first">
					</div>
					<div class="tve-form-field">
						<label>${__("Last Name")} <span class="req">*</span></label>
						<input type="text" id="ind-last">
					</div>
				</div>

				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("Email")} <span class="req">*</span></label>
						<input type="email" id="ind-email">
					</div>
					<div class="tve-form-field">
						<label>${__("Phone")}</label>
						<input type="text" id="ind-phone" placeholder="+255...">
					</div>
				</div>

				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("ID Number")}</label>
						<input type="text" id="ind-idnum" placeholder="${__("National ID")}">
					</div>
					<div class="tve-form-field">
						<label>${__("Staff Number")}</label>
						<input type="text" id="ind-staff">
					</div>
				</div>

				<div class="tve-form-row">
					<div class="tve-form-field">
						<label>${__("Department")}</label>
						<select id="ind-dept">
							<option value="">${__("Select department...")}</option>
							${dept_opts}
						</select>
					</div>
					<div class="tve-form-field"></div>
				</div>

				<label class="tve-checkbox">
					<input type="checkbox" id="ind-welcome" checked>
					${__("Send welcome email")}
				</label>

				<div class="tve-action-row">
					<button class="btn btn-primary" id="ind-save">
						${__("Create Lecturer")}
					</button>
				</div>
			`);

			$form.find("#ind-save").on("click", () => this._save_individual_lecturer());
		}
	}

	async _save_individual_student() {
		const $form = this.wrapper.find("#tve-ind-form");
		const args = {
			first_name:    $form.find("#ind-first").val().trim(),
			last_name:     $form.find("#ind-last").val().trim(),
			email:         $form.find("#ind-email").val().trim(),
			phone:         $form.find("#ind-phone").val().trim() || null,
			index_number:  $form.find("#ind-index").val().trim(),
			academic_year: $form.find("#ind-ay").val().trim(),
			program:       $form.find("#ind-program").val(),
			send_welcome:  $form.find("#ind-welcome").prop("checked") ? 1 : 0,
		};

		// Client-side validation
		const errors = [];
		if (!args.first_name) errors.push(__("First name is required"));
		if (!args.last_name) errors.push(__("Last name is required"));
		if (!args.email || !args.email.includes("@")) errors.push(__("Valid email is required"));
		if (!args.index_number) errors.push(__("Index number is required"));
		if (!args.academic_year) errors.push(__("Academic year is required"));
		if (!args.program) errors.push(__("Programme is required"));

		if (errors.length) {
			frappe.msgprint({
				title: __("Missing required fields"),
				message: errors.join("<br>"),
				indicator: "red",
			});
			return;
		}

		try {
			await frappe.xcall("tvms.tvms.api.enrollment.add_individual_student", args);
			frappe.show_alert({ message: __("Student created"), indicator: "green" });
			$form.find("input, select").val("");
			$form.find("#ind-welcome").prop("checked", true);
			$form.find("#ind-year-preview").hide();
		} catch (e) {
			frappe.msgprint({
				title: __("Could not create student"),
				message: e.message,
				indicator: "red",
			});
		}
	}

	async _save_individual_lecturer() {
		const $form = this.wrapper.find("#tve-ind-form");
		const args = {
			first_name:   $form.find("#ind-first").val().trim(),
			last_name:    $form.find("#ind-last").val().trim(),
			email:        $form.find("#ind-email").val().trim(),
			phone:        $form.find("#ind-phone").val().trim() || null,
			id_number:    $form.find("#ind-idnum").val().trim() || null,
			staff_number: $form.find("#ind-staff").val().trim() || null,
			department:   $form.find("#ind-dept").val() || null,
			send_welcome: $form.find("#ind-welcome").prop("checked") ? 1 : 0,
		};

		const errors = [];
		if (!args.first_name) errors.push(__("First name is required"));
		if (!args.last_name) errors.push(__("Last name is required"));
		if (!args.email || !args.email.includes("@")) errors.push(__("Valid email is required"));

		if (errors.length) {
			frappe.msgprint({
				title: __("Missing required fields"),
				message: errors.join("<br>"),
				indicator: "red",
			});
			return;
		}

		try {
			await frappe.xcall("tvms.tvms.api.enrollment.add_individual_lecturer", args);
			frappe.show_alert({ message: __("Lecturer created"), indicator: "green" });
			$form.find("input, select").val("");
			$form.find("#ind-welcome").prop("checked", true);
		} catch (e) {
			frappe.msgprint({
				title: __("Could not create lecturer"),
				message: e.message,
				indicator: "red",
			});
		}
	}

	// =================================================================
	// TAB 3 — MANAGE USERS
	// =================================================================

	async _render_manage_tab() {
		const $tab = this.wrapper.find('.tve-tab-content[data-content="manage"]');
		$tab.html(`
			<div class="tve-card">
				<div class="tve-filters-row">
					<input type="text" class="form-control input-sm" id="mgmt-search"
						placeholder="${__('Search name or email')}">
					<select class="form-control input-sm" id="mgmt-role">
						<option value="">${__("All roles")}</option>
						<option value="Student">${__("Student")}</option>
						<option value="Lecturer">${__("Lecturer")}</option>
						<option value="Class Representative (CR)">${__("CR")}</option>
						<option value="Department Admin">${__("Department Admin")}</option>
					</select>
					<select class="form-control input-sm" id="mgmt-enabled">
						<option value="">${__("All statuses")}</option>
						<option value="1">${__("Enabled only")}</option>
						<option value="0">${__("Disabled only")}</option>
					</select>
					<button class="btn btn-default btn-sm" id="mgmt-refresh">
						<i class="fa fa-refresh"></i>
					</button>
				</div>

				<div id="mgmt-results"></div>
			</div>

			<div class="tve-side-panel" id="user-panel">
				<div class="tve-sp-header">
					<div style="font-weight: 500;">${__("User Details")}</div>
					<button class="tve-sp-close">&times;</button>
				</div>
				<div class="tve-sp-body" id="user-panel-body"></div>
			</div>
		`);

		// Wire filters
		$tab.find("#mgmt-search").on("input", frappe.utils.debounce(() => this._load_users(), 400));
		$tab.find("#mgmt-role, #mgmt-enabled").on("change", () => this._load_users());
		$tab.find("#mgmt-refresh").on("click", () => this._load_users());

		// Side panel close
		this.wrapper.find(".tve-sp-close").on("click", () =>
			this.wrapper.find(".tve-side-panel").removeClass("open")
		);

		await this._load_users();
	}

	async _load_users() {
		const args = {
			search:  this.wrapper.find("#mgmt-search").val() || null,
			role:    this.wrapper.find("#mgmt-role").val() || null,
			enabled: this.wrapper.find("#mgmt-enabled").val(),
			limit:   200,
		};

		this.wrapper.find("#mgmt-results").html(`
			<div class="tve-empty">${__("Loading...")}</div>
		`);

		try {
			const users = await frappe.xcall("tvms.tvms.api.enrollment.list_users", args);
			this._render_users_table(users);
		} catch (e) {
			this.wrapper.find("#mgmt-results").html(`
				<div class="tve-empty">${__("Could not load users")}</div>
			`);
		}
	}

	_render_users_table(users) {
		if (!users.length) {
			this.wrapper.find("#mgmt-results").html(`
				<div class="tve-empty">${__("No users match the current filters")}</div>
			`);
			return;
		}

		const rows = users.map(u => {
			const role_badges = (u.roles || []).map(r => {
				let cls = "Student";
				if (r === "Lecturer")                  cls = "Lecturer";
				if (r === "Class Representative (CR)") cls = "CR";
				if (r === "Department Admin")          cls = "DA";
				const label = r === "Class Representative (CR)" ? "CR"
					: r === "Department Admin" ? "Dept Admin" : r;
				return `<span class="tve-role-badge tve-role-${cls}">${frappe.utils.escape_html(label)}</span>`;
			}).join("");

			const prog_year = [u.program, u.year_level].filter(Boolean).join(" - ");
			const status_cls = u.enabled ? "enabled" : "disabled";
			const status_text = u.enabled ? __("Enabled") : __("Disabled");

			return `
				<tr data-email="${frappe.utils.escape_html(u.name)}">
					<td>
						<div class="tve-name">${frappe.utils.escape_html(u.full_name || "—")}</div>
						<div class="tve-email-small">${frappe.utils.escape_html(u.name)}</div>
					</td>
					<td>${role_badges}</td>
					<td>${frappe.utils.escape_html(prog_year || u.department || "—")}</td>
					<td>${frappe.utils.escape_html(u.mobile_no || "—")}</td>
					<td><span class="tve-status-badge tve-status-${status_cls}">${status_text}</span></td>
				</tr>
			`;
		}).join("");

		this.wrapper.find("#mgmt-results").html(`
			<table class="tve-users-table">
				<thead>
					<tr>
						<th>${__("Name")}</th>
						<th>${__("Roles")}</th>
						<th>${__("Programme / Department")}</th>
						<th>${__("Phone")}</th>
						<th>${__("Status")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		`);

		// Row click → open side panel
		this.wrapper.find(".tve-users-table tbody tr").on("click", (e) => {
			const email = $(e.currentTarget).data("email");
			this._open_user_panel(email);
		});
	}

	async _open_user_panel(email) {
		const $panel = this.wrapper.find("#user-panel");
		const $body = this.wrapper.find("#user-panel-body");

		$panel.addClass("open");
		$body.html(`<div class="tve-empty">${__("Loading...")}</div>`);

		try {
			const users = await frappe.xcall("tvms.tvms.api.enrollment.list_users", { search: email, limit: 1 });
			const user = users.find(u => u.name === email);
			if (!user) {
				$body.html(`<div class="tve-empty">${__("User not found")}</div>`);
				return;
			}

			const is_student  = (user.roles || []).includes("Student");
			const is_lecturer = (user.roles || []).includes("Lecturer");
			const is_cr       = (user.roles || []).includes("Class Representative (CR)");
			const is_da       = (user.roles || []).includes("Department Admin");

			$body.html(`
				<div class="tve-sp-section">
					<div class="tve-sp-section-title">${__("Account")}</div>
					<div class="tve-sp-field">
						<span class="tve-sp-field-label">${__("Name")}</span>
						<span>${frappe.utils.escape_html(user.full_name)}</span>
					</div>
					<div class="tve-sp-field">
						<span class="tve-sp-field-label">${__("Email")}</span>
						<span>${frappe.utils.escape_html(user.name)}</span>
					</div>
					<div class="tve-sp-field">
						<span class="tve-sp-field-label">${__("Phone")}</span>
						<span>${frappe.utils.escape_html(user.mobile_no || "—")}</span>
					</div>
					<div class="tve-sp-field">
						<span class="tve-sp-field-label">${__("Status")}</span>
						<span class="tve-status-badge tve-status-${user.enabled ? 'enabled' : 'disabled'}">
							${user.enabled ? __("Enabled") : __("Disabled")}
						</span>
					</div>
				</div>

				${(user.program || user.year_level || user.department) ? `
					<div class="tve-sp-section">
						<div class="tve-sp-section-title">${__("Assignment")}</div>
						${user.program ? `
							<div class="tve-sp-field">
								<span class="tve-sp-field-label">${__("Programme")}</span>
								<span>${frappe.utils.escape_html(user.program)}</span>
							</div>` : ""}
						${user.year_level ? `
							<div class="tve-sp-field">
								<span class="tve-sp-field-label">${__("Year")}</span>
								<span>${frappe.utils.escape_html(user.year_level)}</span>
							</div>` : ""}
						${user.department ? `
							<div class="tve-sp-field">
								<span class="tve-sp-field-label">${__("Department")}</span>
								<span>${frappe.utils.escape_html(user.department)}</span>
							</div>` : ""}
					</div>
				` : ""}

				<div class="tve-sp-section">
					<div class="tve-sp-section-title">${__("Roles")}</div>
					<div style="margin-bottom: 8px;">
						${(user.roles || []).map(r => {
							let cls = "Student";
							if (r === "Lecturer")                  cls = "Lecturer";
							if (r === "Class Representative (CR)") cls = "CR";
							if (r === "Department Admin")          cls = "DA";
							return `<span class="tve-role-badge tve-role-${cls}">${frappe.utils.escape_html(r)}</span>`;
						}).join("")}
					</div>
				</div>

				<div class="tve-sp-section">
					<div class="tve-sp-section-title">${__("Actions")}</div>
					<div class="tve-sp-actions">
						${is_student && !is_cr ? `
							<button class="btn btn-default btn-sm" data-action="promote-cr">
								<i class="fa fa-arrow-up"></i> ${__("Promote to CR")}
							</button>` : ""}
						${is_cr ? `
							<button class="btn btn-default btn-sm" data-action="demote-cr">
								<i class="fa fa-arrow-down"></i> ${__("Remove CR role")}
							</button>` : ""}
						${is_lecturer && !is_da ? `
							<button class="btn btn-default btn-sm" data-action="promote-da">
								<i class="fa fa-arrow-up"></i> ${__("Promote to Department Admin")}
							</button>` : ""}
						${is_da ? `
							<button class="btn btn-default btn-sm" data-action="demote-da">
								<i class="fa fa-arrow-down"></i> ${__("Remove Department Admin role")}
							</button>` : ""}

						<button class="btn btn-default btn-sm" data-action="reset-password">
							<i class="fa fa-key"></i> ${__("Reset password & email")}
						</button>

						${user.enabled ? `
							<button class="btn btn-default btn-sm" data-action="disable">
								<i class="fa fa-ban"></i> ${__("Disable account")}
							</button>
						` : `
							<button class="btn btn-default btn-sm" data-action="enable">
								<i class="fa fa-check"></i> ${__("Enable account")}
							</button>
						`}
					</div>
				</div>
			`);

			// Wire actions
			$body.find("[data-action]").on("click", async (e) => {
				const action = $(e.currentTarget).data("action");
				await this._run_user_action(email, action);
				await this._open_user_panel(email);     // refresh panel
				await this._load_users();               // refresh table
			});
		} catch (e) {
			$body.html(`<div class="tve-empty">${__("Could not load user")}</div>`);
		}
	}

	async _run_user_action(email, action) {
		const action_map = {
			"promote-cr":     "promote_to_cr",
			"demote-cr":      "demote_from_cr",
			"promote-da":     "promote_to_dept_admin",
			"demote-da":      "demote_from_dept_admin",
			"enable":         "enable_user",
			"disable":        "disable_user",
			"reset-password": "reset_user_password",
		};
		const fn = action_map[action];
		if (!fn) return;

		// Confirm destructive actions
		if (action === "disable" || action === "reset-password") {
			const msg = action === "disable"
				? __("Disable {0}? They will lose access immediately.", [email])
				: __("Reset password and email new credentials to {0}?", [email]);
			const ok = await new Promise(r =>
				frappe.confirm(msg, () => r(true), () => r(false))
			);
			if (!ok) return;
		}

		try {
			const args = { email };
			if (action === "reset-password") args.send_email = 1;
			await frappe.xcall(`tvms.tvms.api.enrollment.${fn}`, args);
			frappe.show_alert({ message: __("Done"), indicator: "green" });
		} catch (e) {
			frappe.msgprint({
				title: __("Action failed"),
				message: e.message,
				indicator: "red",
			});
		}
	}

	// =================================================================
	// HELPERS
	// =================================================================

	async _get_programs() {
		if (this._programs_cache) return this._programs_cache;
		const r = await frappe.db.get_list("Program", {
			fields: ["name", "program_name"],
			limit: 200,
			order_by: "program_name asc",
		});
		this._programs_cache = r;
		return r;
	}

	async _get_departments() {
		if (this._departments_cache) return this._departments_cache;
		const r = await frappe.db.get_list("Departments", {
			fields: ["name", "department_name"],
			limit: 200,
			order_by: "department_name asc",
		});
		this._departments_cache = r;
		return r;
	}
}