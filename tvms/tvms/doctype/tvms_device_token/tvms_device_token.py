# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TVMSDeviceToken(Document):
    """One row per registered mobile device.

    Created via the register_device_token() API in push_notifications.py
    when a user opens the Flutter app and grants notification permission.
    The same user can have multiple device tokens (phone + tablet + web).

    The doctype is automatically deactivated when FCM reports the token
    as invalid (e.g. user uninstalled the app) — handled by
    _deactivate_token() in push_notifications.py.
    """

    def before_insert(self):
        # Stamp registered_at at first save
        if not self.registered_at:
            self.registered_at = frappe.utils.now_datetime()

    def validate(self):
        # Ensure unique (user, token) pair — a single device should not
        # register the same token twice. If it tries, fail clearly so the
        # caller knows to use the existing row.
        if self.token and self.user:
            existing = frappe.db.get_value(
                "TVMS Device Token",
                {
                    "user": self.user,
                    "token": self.token,
                    "name": ["!=", self.name or ""],
                },
                "name",
            )
            if existing:
                frappe.throw(_("This device token is already registered for {0}").format(self.user))