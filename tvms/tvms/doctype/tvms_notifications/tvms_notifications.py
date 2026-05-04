# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class TvmsNotifications(Document):
	pass


# ==================================================================
# Internal helper — called by other modules (not itself whitelisted)
# ==================================================================

def _create_tvms_notification(
	title, message, recipient,
	recipient_role=None, reference_type=None, reference_name=None,
	channel="in-system",
):
	"""Create a TVMS Notifications record. Never throws — failures logged only."""
	try:
		frappe.get_doc({
			"doctype": "Tvms Notifications",
			"title": title,
			"message": message,
			"recipient": recipient,
			"recipient_role": recipient_role or "",
			"reference_type": reference_type or "",
			"reference_name": reference_name or "",
			"status": "SENT",
			"channel": channel,
			"sent_at": now(),
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.logger().error("Failed to create TVMS notification", exc_info=True)


# ==================================================================
# Public APIs consumed by Desk pages and Frappe form scripts
# ==================================================================

@frappe.whitelist(methods=["GET"])
def get_user_notifications(limit: int = 30):
	"""Return the current user's notifications, most recent first."""
	return frappe.db.get_list(
		"Tvms Notifications",
		filters=[["recipient", "=", frappe.session.user]],
		fields=[
			"name", "title", "message", "status", "channel",
			"sent_at", "read_at", "reference_type", "reference_name",
			"is_forwarded", "forwarded_at",
		],
		order_by="sent_at desc",
		limit=int(limit),
	)


@frappe.whitelist(methods=["GET"])
def get_unread_count():
	"""Return the count of unread notifications for the current user."""
	return frappe.db.count(
		"Tvms Notifications",
		filters=[
			["recipient", "=", frappe.session.user],
			["status", "in", ["PENDING", "SENT"]],
		],
	)


@frappe.whitelist(methods=["POST"])
def mark_notification_read(name: str):
	"""Mark a single notification as READ."""
	doc = frappe.get_doc("Tvms Notifications", name)
	if doc.recipient != frappe.session.user:
		frappe.throw(_("Not authorized"), frappe.PermissionError)
	if doc.status != "READ":
		doc.status = "READ"
		doc.read_at = now()
		doc.save(ignore_permissions=True)
	return True


@frappe.whitelist(methods=["POST"])
def mark_all_read():
	"""Mark all of the current user's unread notifications as READ."""
	frappe.db.sql("""
		UPDATE `tabTvms Notifications`
		SET    status = 'READ', read_at = %s
		WHERE  recipient = %s
		AND    status IN ('PENDING', 'SENT')
	""", [now(), frappe.session.user])
	frappe.db.commit()
	return True


@frappe.whitelist(methods=["POST"])
def forward_notification(name: str):
	"""FR-28: CR forwards a notification to all enabled Students.

	Creates a new TVMS Notifications record for each Student and broadcasts
	a realtime 'tvms_notification' event so their bell updates immediately.
	Returns the number of students notified.
	"""
	doc = frappe.get_doc("Tvms Notifications", name)
	user = frappe.session.user

	if doc.recipient != user:
		frappe.throw(_("Not authorized"), frappe.PermissionError)
	if "Class Representative (CR)" not in frappe.get_roles(user):
		frappe.throw(_("Only Class Representatives can forward notifications"))
	if doc.is_forwarded:
		frappe.throw(_("This notification has already been forwarded"))

	cr_name = frappe.db.get_value("User", user, "full_name") or user

	students = frappe.db.sql("""
		SELECT DISTINCT u.name
		FROM   `tabHas Role` hr
		INNER JOIN `tabUser` u ON hr.parent = u.name
		WHERE  hr.role = 'Student'
		AND    u.enabled = 1
	""", as_dict=True)

	msg = f"[Forwarded by CR {cr_name}] {doc.message}"
	rt_data = {"title": doc.title, "message": doc.message, "from_cr": cr_name}

	for student in students:
		_create_tvms_notification(
			title=doc.title,
			message=msg,
			recipient=student["name"],
			recipient_role="Students",
			reference_type=doc.reference_type,
			reference_name=doc.reference_name,
			channel="in-system",
		)
		frappe.publish_realtime(
			"tvms_notification", rt_data, user=student["name"], after_commit=True
		)

	doc.is_forwarded = 1
	doc.forwarded_at = now()
	doc.forwarded_by = user
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return len(students)
