// Copyright (c) 2026, Magugwani and contributors
// For license information, please see license.txt

frappe.pages["my-profile"].on_page_load = function (wrapper) {
	frappe.my_profile_page = new MyProfilePage(wrapper);
};

class MyProfilePage {
	constructor(wrapper) {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("My Profile"),
			single_column: true,
		});

		this.wrapper = $(wrapper);
		this.page = wrapper.page;
		this.$body = this.wrapper.find(".layout-main-section");
		this.profile = null;

		this.build();
		this.load();
	}

	build() {
		this.$body.html(`
			<div class="mp-page">
				<div id="mp-loader" class="mp-empty">${__("Loading your profile...")}</div>
				<div id="mp-content" style="display:none;"></div>
			</div>

			<style>
				.mp-page { padding: 12px 0; max-width: 720px; margin: 0 auto; }

				.mp-empty {
					padding: 60px 20px;
					text-align: center;
					color: var(--text-muted);
				}

				.mp-header {
					display: flex; gap: 16px; align-items: center;
					padding: 20px;
					background: var(--card-bg);
					border: 1px solid var(--border-color);
					border-radius: 10px;
					margin-bottom: 16px;
				}
				.mp-avatar {
					width: 64px; height: 64px;
					border-radius: 50%;
					background: #1976d2;
					color: #fff;
					display: flex; align-items: center; justify-content: center;
					font-size: 22px; font-weight: 500;
					flex-shrink: 0;
				}
				.mp-avatar img {
					width: 100%; height: 100%;
					border-radius: 50%; object-fit: cover;
				}
				.mp-name {
					font-size: 18px; font-weight: 500;
					margin-bottom: 2px;
				}
				.mp-role-line {
					font-size: 13px; color: var(--text-muted);
				}
				.mp-role-badge {
					display: inline-block;
					padding: 2px 10px; border-radius: 10px;
					background: #E6F1FB; color: #185FA5;
					font-size: 11px; font-weight: 500;
					margin-right: 6px;
				}

				.mp-card {
					background: var(--card-bg);
					border: 1px solid var(--border-color);
					border-radius: 10px;
					padding: 18px 20px;
					margin-bottom: 14px;
				}
				.mp-card-title {
					display: flex; align-items: center;
					font-size: 13px; font-weight: 500;
					margin-bottom: 12px;
					color: var(--text-color);
				}
				.mp-card-title .fa {
					margin-right: 8px; color: var(--text-muted);
				}

				.mp-field {
					display: flex; justify-content: space-between;
					padding: 8px 0;
					border-bottom: 1px solid var(--border-color);
					font-size: 13px;
				}
				.mp-field:last-child { border-bottom: 0; }
				.mp-field-label {
					color: var(--text-muted);
				}
				.mp-field-value {
					color: var(--text-color); font-weight: 500;
				}
				.mp-field-locked {
					font-size: 11px;
					color: var(--text-muted);
					margin-left: 6px;
				}
				.mp-field-locked .fa {
					font-size: 10px; margin-right: 2px;
				}

				.mp-edit-row {
					margin-bottom: 12px;
				}
				.mp-edit-row label {
					display: block; font-size: 11px;
					color: var(--text-muted);
					text-transform: uppercase;
					letter-spacing: 0.04em;
					margin-bottom: 4px; font-weight: 500;
				}
				.mp-edit-row input {
					width: 100%;
					padding: 8px 10px;
					border: 1px solid var(--border-color);
					border-radius: 4px;
					font-size: 13px;
				}

				.mp-action-row {
					display: flex; gap: 8px;
					margin-top: 12px;
				}

				.mp-link-action {
					display: flex; align-items: center; justify-content: space-between;
					padding: 12px;
					border: 1px solid var(--border-color);
					border-radius: 6px;
					margin-bottom: 8px;
					text-decoration: none;
					color: var(--text-color);
					font-size: 13px;
					cursor: pointer;
					background: #fff;
				}
				.mp-link-action:hover {
					background: var(--subtle-fg);
					text-decoration: none;
				}
				.mp-link-action-text { display: flex; align-items: center; }
				.mp-link-action-text .fa { margin-right: 10px; color: var(--text-muted); }
				.mp-link-action .fa-chevron-right {
					color: var(--text-muted); font-size: 12px;
				}

				.mp-save-banner {
					display: none;
					margin: 12px 0;
					padding: 10px 14px;
					background: #DCF1E8;
					color: #0F6E56;
					border-radius: 6px;
					font-size: 12px;
				}
				.mp-save-banner.show { display: block; }
			</style>
		`);
	}

	async load() {
		try {
			this.profile = await frappe.xcall(
				"tvms.tvms.api.enrollment.get_my_profile"
			);
			this._render();
		} catch (e) {
			this.wrapper.find("#mp-loader").html(`
				<div style="color: #A32D2D;">${__("Could not load your profile.")}</div>
			`);
		}
	}

	_render() {
		const p = this.profile;
		const initials = (p.first_name?.[0] || p.full_name?.[0] || "U") +
			(p.last_name?.[0] || "");

		// Build role display
		const roles = p.roles || [];
		const role_label = this._build_role_label(p);

		this.wrapper.find("#mp-loader").hide();
		this.wrapper.find("#mp-content").show().html(`
			<div class="mp-header">
				<div class="mp-avatar">
					${p.user_image ?
						`<img src="${frappe.utils.escape_html(p.user_image)}" alt="">` :
						frappe.utils.escape_html(initials.toUpperCase())}
				</div>
				<div>
					<div class="mp-name">${frappe.utils.escape_html(p.full_name)}</div>
					<div class="mp-role-line">${role_label}</div>
				</div>
			</div>

			<div class="mp-card">
				<div class="mp-card-title">
					<i class="fa fa-lock"></i> ${__("Account Information")}
				</div>
				<div class="mp-field">
					<span class="mp-field-label">${__("Email")}</span>
					<span class="mp-field-value">
						${frappe.utils.escape_html(p.email)}
						<span class="mp-field-locked"><i class="fa fa-lock"></i></span>
					</span>
				</div>
				<div class="mp-field">
					<span class="mp-field-label">${__("Full name")}</span>
					<span class="mp-field-value">
						${frappe.utils.escape_html(p.full_name)}
						<span class="mp-field-locked"><i class="fa fa-lock"></i></span>
					</span>
				</div>
				${p.program ? `
					<div class="mp-field">
						<span class="mp-field-label">${__("Programme")}</span>
						<span class="mp-field-value">
							${frappe.utils.escape_html(p.program)}
							<span class="mp-field-locked"><i class="fa fa-lock"></i></span>
						</span>
					</div>` : ""}
				${p.year_level ? `
					<div class="mp-field">
						<span class="mp-field-label">${__("Year")}</span>
						<span class="mp-field-value">
							${frappe.utils.escape_html(p.year_level)}
							<span class="mp-field-locked"><i class="fa fa-lock"></i></span>
						</span>
					</div>` : ""}
				${p.department ? `
					<div class="mp-field">
						<span class="mp-field-label">${__("Department")}</span>
						<span class="mp-field-value">
							${frappe.utils.escape_html(p.department)}
							<span class="mp-field-locked"><i class="fa fa-lock"></i></span>
						</span>
					</div>` : ""}
				<div class="mp-field">
					<span class="mp-field-label">${__("Roles")}</span>
					<span class="mp-field-value">
						${roles.map(r =>
							`<span class="mp-role-badge">${frappe.utils.escape_html(r)}</span>`
						).join("")}
						<span class="mp-field-locked"><i class="fa fa-lock"></i></span>
					</span>
				</div>
				<p style="font-size: 11px; color: var(--text-muted); margin: 8px 0 0; line-height: 1.4;">
					<i class="fa fa-info-circle"></i>
					${__("Locked fields can only be changed by your administrator.")}
				</p>
			</div>

			<div class="mp-card">
				<div class="mp-card-title">
					<i class="fa fa-pencil"></i> ${__("Editable Profile")}
				</div>
				<div class="mp-edit-row">
					<label>${__("Phone")}</label>
					<input type="text" id="mp-phone" value="${frappe.utils.escape_html(p.phone || '')}" placeholder="+255...">
				</div>
				<div class="mp-action-row">
					<button class="btn btn-primary btn-sm" id="mp-save-phone">
						${__("Save phone")}
					</button>
				</div>
				<div class="mp-save-banner" id="mp-phone-banner">
					${__("Saved")}
				</div>
			</div>

			<div class="mp-card">
				<div class="mp-card-title">
					<i class="fa fa-shield"></i> ${__("Security")}
				</div>
				<a class="mp-link-action" id="mp-change-password">
					<span class="mp-link-action-text">
						<i class="fa fa-key"></i> ${__("Change password")}
					</span>
					<i class="fa fa-chevron-right"></i>
				</a>
				<a class="mp-link-action" id="mp-logout-all">
					<span class="mp-link-action-text">
						<i class="fa fa-sign-out"></i> ${__("Sign out from all devices")}
					</span>
					<i class="fa fa-chevron-right"></i>
				</a>
			</div>

			<div class="mp-card">
				<div class="mp-card-title">
					<i class="fa fa-bell"></i> ${__("Notifications")}
				</div>
				<a class="mp-link-action" href="/app/tvms-notification-preference">
					<span class="mp-link-action-text">
						<i class="fa fa-sliders"></i> ${__("Notification preferences")}
					</span>
					<i class="fa fa-chevron-right"></i>
				</a>
			</div>
		`);

		this._wire_events();
	}

	_build_role_label(p) {
		const roles = p.roles || [];
		const has = (r) => roles.includes(r);

		// Build a clear human-readable role line
		const parts = [];
		if (has("Student")) {
			if (p.year_level && p.program) {
				const year_short = p.year_level.match(/\((\d)\)/);
				const y = year_short ? `Year ${year_short[1]}` : p.year_level;
				parts.push(`${y} ${p.program} Student`);
			} else {
				parts.push("Student");
			}
		}
		if (has("Lecturer")) {
			parts.push(p.department ? `${p.department} Lecturer` : "Lecturer");
		}
		if (has("Class Representative (CR)")) parts.push("Class Representative");
		if (has("Department Admin")) parts.push("Department Admin");

		return frappe.utils.escape_html(parts.join(" • "));
	}

	_wire_events() {
		// Save phone
		this.wrapper.find("#mp-save-phone").on("click", async () => {
			const phone = this.wrapper.find("#mp-phone").val().trim();
			try {
				await frappe.xcall("tvms.tvms.api.enrollment.update_my_phone", { phone });
				this.profile.phone = phone;
				const $banner = this.wrapper.find("#mp-phone-banner");
				$banner.addClass("show");
				setTimeout(() => $banner.removeClass("show"), 2000);
			} catch (e) {
				frappe.msgprint({
					title: __("Could not save"),
					message: e.message,
					indicator: "red",
				});
			}
		});

		// Change password dialog
		this.wrapper.find("#mp-change-password").on("click", () => {
			const d = new frappe.ui.Dialog({
				title: __("Change password"),
				fields: [
					{
						fieldtype: "Password", fieldname: "old_password",
						label: __("Current password"), reqd: 1,
					},
					{
						fieldtype: "Password", fieldname: "new_password",
						label: __("New password (min 8 characters)"), reqd: 1,
					},
					{
						fieldtype: "Password", fieldname: "confirm_password",
						label: __("Confirm new password"), reqd: 1,
					},
				],
				primary_action_label: __("Change Password"),
				primary_action: async (values) => {
					if (values.new_password !== values.confirm_password) {
						frappe.msgprint(__("New passwords don't match"));
						return;
					}
					if (values.new_password.length < 8) {
						frappe.msgprint(__("Password must be at least 8 characters"));
						return;
					}
					try {
						await frappe.xcall("tvms.tvms.api.auth.change_password", {
							old_password: values.old_password,
							new_password: values.new_password,
						});
						d.hide();
						frappe.show_alert({
							message: __("Password changed. You will be signed out."),
							indicator: "green",
						});
						setTimeout(() => { frappe.app.logout(); }, 1500);
					} catch (e) {
						frappe.msgprint({
							title: __("Could not change password"),
							message: e.message,
							indicator: "red",
						});
					}
				},
			});
			d.show();
		});

		// Sign out from all devices
		this.wrapper.find("#mp-logout-all").on("click", async () => {
			const ok = await new Promise(r =>
				frappe.confirm(
					__("This will sign you out from all devices including the mobile app. Continue?"),
					() => r(true), () => r(false),
				)
			);
			if (!ok) return;

			try {
				await frappe.xcall("tvms.tvms.api.auth.mobile_logout");
				frappe.show_alert({
					message: __("Signed out from all devices"),
					indicator: "green",
				});
				setTimeout(() => { frappe.app.logout(); }, 1500);
			} catch (e) {
				frappe.msgprint(e.message);
			}
		});
	}
}