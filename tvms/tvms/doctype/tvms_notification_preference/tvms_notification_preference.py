# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

"""TVMS Notification Preference — FR-43.

Per-user toggles for delivery channels (push/email/SMS/in-app)
and event types (session reminders, timetable updates, etc).

The notification engine consults should_deliver() before
sending. Critical notifications (is_critical=1) bypass these
preferences except for the in-app channel which is always on.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time, now_datetime


# ============================================================
# Doctype controller
# ============================================================

class TVMSNotificationPreference(Document):

    def autoname(self):
        # Naming is by user (set in JSON), but ensure it's set
        if not self.user:
            frappe.throw(_("User is required"))
        self.name = self.user

    def validate(self):
        self._user_can_only_edit_own()
        self._sync_summary()

    def _user_can_only_edit_own(self):
        """Block users from editing other users' preferences.

        Admins (System Manager/Administrator) can edit anyone's.
        Other roles can only edit their own row.
        """
        if frappe.session.user == "Administrator":
            return
        admin_roles = {"System Manager", "Administrator"}
        if admin_roles.intersection(frappe.get_roles()):
            return
        if self.user != frappe.session.user:
            frappe.throw(
                _("You can only edit your own notification preferences"),
                frappe.PermissionError,
            )

    def _sync_summary(self):
        """Build a one-line human-readable summary shown in the list view."""
        channels = []
        if self.channel_in_app:    channels.append("In-app")
        if self.channel_email:     channels.append("Email")
        if self.channel_push:      channels.append("Push")
        if self.channel_sms:       channels.append("SMS")
        if self.channel_realtime:  channels.append("Live")

        if not channels:
            self.summary = "All channels off"
        else:
            self.summary = " · ".join(channels)
            if self.respect_quiet_hours:
                self.summary += f" (quiet {self.quiet_start}–{self.quiet_end})"


# ============================================================
# Dispatch logic — called by the notification engine
# ============================================================

# Map between event_type strings used by the notification engine
# and the field names on this preference doctype.
EVENT_TO_FIELD = {
    "SESSION_CREATED":           "session_created",
    "SESSION_CONFIRMED":         "session_confirmed",
    "SESSION_CANCELLED":         "session_cancelled",
    "SESSION_POSTPONED":         "session_postponed",
    "SESSION_REMINDER":          "session_reminder",
    "SESSION_COMPLETED":         "session_completed",
    "SESSION_EXPIRED":           "session_completed",
    "TIMETABLE_UPDATED":         "timetable_updates",
    "TIMETABLE_PUBLISHED":       "timetable_updates",
    "TIMETABLE_UNPUBLISHED":     "timetable_updates",
    "TIMETABLE_TIME_CHANGED":    "timetable_updates",
    "TIMETABLE_LECTURER_CHANGED": "timetable_updates",
    "TIMETABLE_DELETED":         "timetable_updates",
    "TIMETABLE_VENUE_CHANGED":   "venue_changes",
    "VENUE_STATUS_CHANGED":      "venue_changes",
}

CHANNEL_FIELD_MAP = {
    "in-system": "channel_in_app",
    "email":     "channel_email",
    "push":      "channel_push",
    "sms":       "channel_sms",
    "realtime":  "channel_realtime",
    "websocket": "channel_realtime",
}


def _get_or_default(user: str):
    """Load preferences for a user, returning a dict of defaults
    if no row exists yet. Never raises.
    """
    if not user or user == "Guest":
        return _default_prefs()

    try:
        return frappe.get_cached_doc("TVMS Notification Preference", user).as_dict()
    except frappe.DoesNotExistError:
        return _default_prefs()
    except Exception:
        frappe.logger().warning(
            f"[TVMS Prefs] Failed to load prefs for {user}; using defaults",
            exc_info=True,
        )
        return _default_prefs()


def _default_prefs():
    """Defaults that match the doctype defaults — used when a user
    has never opened the preference page.
    """
    return {
        "channel_in_app":      1,
        "channel_email":       1,
        "channel_push":        1,
        "channel_sms":         0,
        "channel_realtime":    1,
        "session_created":     1,
        "session_confirmed":   1,
        "session_cancelled":   1,
        "session_postponed":   1,
        "session_reminder":    1,
        "session_completed":   0,
        "timetable_updates":   1,
        "venue_changes":       1,
        "respect_quiet_hours": 0,
        "critical_override":   1,
    }


def should_deliver(user: str, channel: str, event_type: str = None,
                   is_critical: bool = False) -> bool:
    """Decide whether to send a notification on a given channel.

    The notification engine calls this for every (user, channel, event)
    triple before dispatching. Returns False → channel is skipped silently.

    Args:
        user        -- recipient User docname
        channel     -- one of: in-system, email, push, sms, realtime
        event_type  -- one of the EVENT_TO_FIELD keys (optional)
        is_critical -- bypasses event-type filter; bypasses quiet hours
                       if critical_override is on

    Rules applied in order:
        1. In-app channel — always delivers (cannot be disabled)
        2. Channel toggle off → skip
        3. Event type toggle off (and not critical) → skip
        4. Quiet hours active and not critical → skip
    """
    # Rule 1 — in-app always delivers
    if channel in ("in-system", "in_app"):
        return True

    prefs = _get_or_default(user)

    # Rule 2 — channel toggle
    chan_field = CHANNEL_FIELD_MAP.get(channel)
    if chan_field and not prefs.get(chan_field):
        return False

    # Rule 3 — event-type toggle (critical bypasses this)
    if event_type and not is_critical:
        ev_field = EVENT_TO_FIELD.get(event_type)
        if ev_field and not prefs.get(ev_field):
            return False

    # Rule 4 — quiet hours
    if prefs.get("respect_quiet_hours") and not (is_critical and prefs.get("critical_override")):
        if _in_quiet_hours(prefs.get("quiet_start"), prefs.get("quiet_end")):
            return False

    return True


def _in_quiet_hours(quiet_start, quiet_end) -> bool:
    """Return True if the current server time falls inside the quiet window.

    Handles wraparound (e.g. 22:00 → 07:00 — quiet across midnight).
    """
    if not quiet_start or not quiet_end:
        return False
    try:
        now_t = now_datetime().time()
        start_t = get_time(quiet_start)
        end_t = get_time(quiet_end)

        if start_t == end_t:
            return False  # zero-length window

        if start_t < end_t:
            # Same-day window: 09:00 → 17:00
            return start_t <= now_t < end_t
        else:
            # Wraparound window: 22:00 → 07:00
            return now_t >= start_t or now_t < end_t
    except Exception:
        return False


# ============================================================
# Whitelisted APIs — used by the Flutter app
# ============================================================

@frappe.whitelist(methods=["GET"])
def get_my_preferences():
    """Return the current user's preferences, creating defaults if needed.

    The Flutter "Settings → Notifications" screen calls this on open.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Not authenticated"), frappe.PermissionError)

    try:
        doc = frappe.get_doc("TVMS Notification Preference", user)
        return doc.as_dict()
    except frappe.DoesNotExistError:
        # Lazy-create with defaults so the user can update without setup
        doc = frappe.get_doc({
            "doctype": "TVMS Notification Preference",
            "user":    user,
            **_default_prefs(),
        })
        doc.flags.ignore_permissions = True
        doc.insert()
        return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def update_my_preferences(**kwargs):
    """Update the current user's preferences.

    Accepts any subset of the preference fields. Unknown fields are
    silently ignored. The Flutter Settings screen calls this when the
    user toggles a switch.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Not authenticated"), frappe.PermissionError)

    allowed = set(EVENT_TO_FIELD.values()) | set(CHANNEL_FIELD_MAP.values()) | {
        "respect_quiet_hours", "quiet_start", "quiet_end", "critical_override",
    }

    try:
        doc = frappe.get_doc("TVMS Notification Preference", user)
    except frappe.DoesNotExistError:
        doc = frappe.get_doc({"doctype": "TVMS Notification Preference", "user": user})
        doc.flags.ignore_permissions = True
        doc.insert()

    changed = []
    for field, value in kwargs.items():
        if field in allowed and doc.get(field) != value:
            doc.set(field, value)
            changed.append(field)

    if changed:
        doc.save()
        frappe.db.commit()
        frappe.clear_cache(doctype="TVMS Notification Preference")

    return {
        "user":           doc.user,
        "fields_changed": changed,
        "preferences":    doc.as_dict(),
    }


@frappe.whitelist(methods=["GET"])
def get_preference_schema():
    """Return the schema (labels, descriptions, defaults) of all preference
    fields. Used by the Flutter app to render the settings UI without
    hardcoding labels.
    """
    meta = frappe.get_meta("TVMS Notification Preference")
    fields = []
    for f in meta.fields:
        if f.fieldtype in ("Section Break", "Column Break", "HTML"):
            continue
        if f.fieldname in ("user", "summary"):
            continue
        fields.append({
            "fieldname":   f.fieldname,
            "label":       f.label,
            "fieldtype":   f.fieldtype,
            "default":     f.default,
            "description": f.description,
            "depends_on":  f.depends_on,
        })
    return fields