# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt
#
# ============================================================
# TVMS Audit Log — FR-30 + FR-40
# ============================================================
#
# This module is the single point where every TVMS-significant
# event gets recorded. Three call sites use log_event():
#
#   1. emergency_session.py — session lifecycle (create, confirm,
#      cancel, complete, expire, postpone)
#   2. tvms_notifications.py — notification creation and forwarding
#   3. venue.py — venue status transitions (optional, replaces the
#      existing log_venue_status_change later)
#
# log_event() must NEVER throw — a failed audit write must not
# block the user's actual action.

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class TVMSAuditLog(Document):
    """Append-only log doctype. Rows are written by log_event() —
    admins should never create rows manually, the data is intended
    to be immutable.
    """
    pass


# ==================================================================
# Core writer — used by every TVMS module
# ==================================================================

def log_event(
    event_type: str,
    summary: str,
    *,
    subject_type: str = None,
    subject_name: str = None,
    subject_label: str = None,
    actor: str = None,
    recipient: str = None,
    recipient_role: str = None,
    payload: dict = None,
    linked_audit: str = None,
    channel: str = None,
    ip_address: str = None,
):
    """Append one row to TVMS Audit Log.

    All keyword args except event_type and summary are optional —
    pass only what's relevant to the event being logged.

    Args:
        event_type   -- one of the SELECT options on the doctype
                        (e.g. SESSION_CONFIRMED, NOTIFICATION_FORWARDED)
        summary      -- one-line human-readable description
        subject_type -- doctype of the subject (e.g. "Emergency session")
        subject_name -- docname of the subject (e.g. "EMS-0042")
        subject_label -- cached display label for the subject. Required when
                         the subject may be deleted later — without this,
                         the audit row points at a vanished docname.
        actor        -- user who performed the action. Defaults to the
                        current session user, or "System" if none.
        recipient    -- for NOTIFICATION_* events, the recipient user
        recipient_role -- e.g. "Class Representative (CR)"
        payload      -- dict of event-specific data; serialised to JSON
        linked_audit -- name of the parent audit row that caused this one
                        (e.g. a NOTIFICATION_SENT row links to the
                        SESSION_CANCELLED that triggered it)
        channel      -- delivery channel for notification events
        ip_address   -- optional client IP for sensitive actions

    Returns the new TVMS Audit Log docname, or None on failure.
    """
    try:
        # Resolve actor — default to current session user, fall back to "System"
        if not actor:
            try:
                actor = frappe.session.user if frappe.session else "Administrator"
            except Exception:
                actor = "Administrator"

        # Resolve IP if not provided and we're in a request context
        if not ip_address:
            try:
                ip_address = frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None
            except Exception:
                ip_address = None

        doc = frappe.get_doc({
            "doctype":        "TVMS Audit Log",
            "event_type":     event_type,
            "summary":        summary[:500] if summary else event_type,
            "subject_type":   subject_type or None,
            "subject_name":   subject_name or None,
            "subject_label":  (subject_label or "")[:200],
            "timestamp":      now_datetime(),
            "actor":          actor,
            "recipient":      recipient or None,
            "recipient_role": recipient_role or None,
            "payload":        json.dumps(payload, default=str) if payload else None,
            "linked_audit":   linked_audit or None,
            "channel":        channel or None,
            "ip_address":     ip_address,
        })
        doc.flags.ignore_permissions = True
        doc.insert()
        return doc.name

    except Exception:
        # Audit writes must NEVER block the calling operation
        frappe.logger().warning(
            f"[TVMS Audit] log_event failed: type={event_type} subject={subject_name}",
            exc_info=True,
        )
        return None


# ==================================================================
# Read APIs — for the session timeline and the global audit page
# ==================================================================

def _ensure_audit_read_access():
    """Only Admins can browse the audit log."""
    roles = set(frappe.get_roles())
    if not {"System Manager", "Administrator", "Department Admin"}.intersection(roles):
        frappe.throw(_("Not authorized to view audit log"), frappe.PermissionError)


@frappe.whitelist(methods=["GET", "POST"])
def get_subject_audit(subject_type: str, subject_name: str, limit: int = 100):
    """Return all audit events for one specific subject, newest first.

    Powers the inline audit tab on the Emergency Session form and the
    notification timeline on a Tvms Notifications form.
    """
    _ensure_audit_read_access()

    if not subject_type or not subject_name:
        frappe.throw(_("subject_type and subject_name are required"))

    limit = min(int(limit or 100), 500)

    rows = frappe.db.get_all(
        "TVMS Audit Log",
        filters={
            "subject_type": subject_type,
            "subject_name": subject_name,
        },
        fields=[
            "name", "event_type", "timestamp", "actor",
            "summary", "recipient", "recipient_role",
            "payload", "channel", "linked_audit",
        ],
        order_by="timestamp desc",
        limit=limit,
    )

    # Enrich actor / recipient with full names — batch query, not N
    user_ids = list({r["actor"] for r in rows if r.get("actor")} |
                    {r["recipient"] for r in rows if r.get("recipient")})

    names = {
        u["name"]: u["full_name"]
        for u in frappe.db.get_all(
            "User",
            filters={"name": ["in", user_ids]} if user_ids else None,
            fields=["name", "full_name"],
        )
    } if user_ids else {}

    for r in rows:
        r["actor_name"]     = names.get(r.get("actor"), r.get("actor") or "")
        r["recipient_name"] = names.get(r.get("recipient"), r.get("recipient") or "")
        r["timestamp"] = str(r["timestamp"])[:16] if r.get("timestamp") else ""
        # Parse payload JSON so the UI doesn't have to
        if r.get("payload"):
            try:
                r["payload"] = json.loads(r["payload"])
            except Exception:
                pass

    return {
        "subject_type": subject_type,
        "subject_name": subject_name,
        "total":  frappe.db.count(
            "TVMS Audit Log",
            {"subject_type": subject_type, "subject_name": subject_name},
        ),
        "events": rows,
    }


@frappe.whitelist(methods=["GET", "POST"])
def search_audit_log(
    from_date: str = None,
    to_date: str = None,
    actor: str = None,
    event_type: str = None,
    subject_type: str = None,
    subject_name: str = None,
    recipient: str = None,
    limit: int = 100,
):
    """Global search across the audit log — used by /app/tvms-audit.

    All filters are optional. With no filters → returns the 100 most
    recent audit events across the whole site.
    """
    _ensure_audit_read_access()

    filters = []
    if from_date:    filters.append(["timestamp", ">=", from_date])
    if to_date:      filters.append(["timestamp", "<=", f"{to_date} 23:59:59"])
    if actor:        filters.append(["actor", "=", actor])
    if event_type:   filters.append(["event_type", "=", event_type])
    if subject_type: filters.append(["subject_type", "=", subject_type])
    if subject_name: filters.append(["subject_name", "=", subject_name])
    if recipient:    filters.append(["recipient", "=", recipient])

    rows = frappe.db.get_all(
        "TVMS Audit Log",
        filters=filters,
        fields=[
            "name", "event_type", "timestamp", "actor",
            "subject_type", "subject_name", "subject_label",
            "summary", "recipient", "recipient_role", "channel",
        ],
        order_by="timestamp desc",
        limit=min(int(limit or 100), 500),
    )

    user_ids = list({r["actor"] for r in rows if r.get("actor")} |
                    {r["recipient"] for r in rows if r.get("recipient")})
    names = {
        u["name"]: u["full_name"]
        for u in frappe.db.get_all(
            "User",
            filters={"name": ["in", user_ids]} if user_ids else None,
            fields=["name", "full_name"],
        )
    } if user_ids else {}

    for r in rows:
        r["actor_name"]     = names.get(r.get("actor"), r.get("actor") or "")
        r["recipient_name"] = names.get(r.get("recipient"), r.get("recipient") or "")
        r["timestamp"] = str(r["timestamp"])[:16] if r.get("timestamp") else ""

    return {
        "total":  len(rows),
        "events": rows,
        "filters_applied": {
            "from_date": from_date, "to_date": to_date,
            "actor": actor, "event_type": event_type,
            "subject_type": subject_type, "subject_name": subject_name,
            "recipient": recipient,
        },
    }


@frappe.whitelist(methods=["GET", "POST"])
def get_notification_chain(audit_name: str):
    """Walk the linked_audit chain for one event.

    Useful for FR-40: starting from a session action, follow the chain
    to every notification it generated and every CR forward those
    notifications produced.

    Returns the original event plus all events that link back to it
    (recursively, one level deep — enough for session → notif → forward).
    """
    _ensure_audit_read_access()

    if not frappe.db.exists("TVMS Audit Log", audit_name):
        frappe.throw(_("Audit log entry not found"), frappe.DoesNotExistError)

    root = frappe.get_doc("TVMS Audit Log", audit_name).as_dict()
    children = frappe.db.get_all(
        "TVMS Audit Log",
        filters={"linked_audit": audit_name},
        fields=[
            "name", "event_type", "timestamp", "actor",
            "subject_type", "subject_name", "summary",
            "recipient", "recipient_role", "channel",
        ],
        order_by="timestamp asc",
    )

    # Walk one level deeper — children's children (e.g. forwards of notifications)
    grandchildren_by_parent = {}
    if children:
        child_names = [c["name"] for c in children]
        gc = frappe.db.get_all(
            "TVMS Audit Log",
            filters={"linked_audit": ["in", child_names]},
            fields=[
                "name", "event_type", "timestamp", "actor",
                "linked_audit", "subject_type", "subject_name",
                "summary", "recipient", "recipient_role", "channel",
            ],
            order_by="timestamp asc",
        )
        for row in gc:
            grandchildren_by_parent.setdefault(row["linked_audit"], []).append(row)

    for c in children:
        c["children"] = grandchildren_by_parent.get(c["name"], [])

    return {
        "root":     root,
        "children": children,
    }