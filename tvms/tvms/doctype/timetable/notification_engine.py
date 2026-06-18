# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt
#
# ============================================================
# Timetable Notification Engine — FR-42
# ============================================================
#
# Centralises the logic for "who gets told what" when a timetable
# entry changes. Built around three rules:
#
#   1. DRAFT changes never notify (drafts are admin-only)
#   2. PUBLISHED changes notify the lecturer, CRs, and students
#   3. Bulk operations send ONE aggregate notification per recipient,
#      not N (where N = number of entries touched)
#
# Every notification creation goes through _create_tvms_notification
# (the existing in-system inbox) and log_event (the audit log).
# Email and SMS are sent only for high-impact changes (cancellation,
# new class), not minor edits — controlled via the URGENCY map.

import frappe
from frappe import _
from frappe.utils import now

from tvms.tvms.doctype.tvms_notifications.tvms_notifications import _create_tvms_notification
from tvms.tvms.doctype.tvms_audit_log.tvms_audit_log import log_event


# ============================================================
# Event taxonomy — what kinds of timetable changes trigger notifications
# ============================================================

EVT_PUBLISHED        = "TIMETABLE_PUBLISHED"        # DRAFT → PUBLISHED on single entry
EVT_UNPUBLISHED      = "TIMETABLE_UNPUBLISHED"      # PUBLISHED → DRAFT
EVT_TIME_CHANGED     = "TIMETABLE_TIME_CHANGED"     # start/end/date changed on published entry
EVT_VENUE_CHANGED    = "TIMETABLE_VENUE_CHANGED"    # venue changed on published entry
EVT_LECTURER_CHANGED = "TIMETABLE_LECTURER_CHANGED" # lecturer changed on published entry
EVT_DELETED          = "TIMETABLE_DELETED"          # published entry removed
EVT_BULK_PUBLISH     = "TIMETABLE_BULK_PUBLISH"     # publish_timetable() called
EVT_BULK_UNPUBLISH   = "TIMETABLE_BULK_UNPUBLISH"   # unpublish_timetable() called

# Which events warrant email + in-system, vs in-system only.
# Anything in HIGH_URGENCY also gets a real-time push so subscribed Desk users
# see it instantly. LOW_URGENCY events only land in the inbox.
HIGH_URGENCY = {
	EVT_DELETED,
	EVT_TIME_CHANGED,
	EVT_VENUE_CHANGED,
	EVT_BULK_PUBLISH,
	EVT_BULK_UNPUBLISH,
}
LOW_URGENCY = {
	EVT_PUBLISHED,
	EVT_UNPUBLISHED,
	EVT_LECTURER_CHANGED,
}

# Fields whose change on a PUBLISHED entry triggers a notification.
# Other field edits (e.g. department, students_groups) are quieter — they
# show up in the audit log but don't ping anyone.
NOTIFIABLE_FIELDS = {
	"date":       EVT_TIME_CHANGED,
	"start_time": EVT_TIME_CHANGED,
	"end_time":   EVT_TIME_CHANGED,
	"venue":      EVT_VENUE_CHANGED,
	"lecturer":   EVT_LECTURER_CHANGED,
}


# ============================================================
# Public entry points — called by Timetable.on_update / on_trash
# and by publish_timetable / unpublish_timetable
# ============================================================

def notify_timetable_entry_change(timetable_doc, changes, old_state, action):
	"""Called from Timetable.on_update AFTER the audit log write.

	Decides whether the change is notification-worthy and, if so,
	identifies recipients and dispatches the notifications.

	Args:
	    timetable_doc -- the saved Timetable Document
	    changes       -- list of {fieldname, old, new} dicts produced by on_update
	    old_state     -- dict of pre-change field values
	    action        -- the audit action label: CREATED / UPDATED / PUBLISHED / etc.
	"""
	try:
		# Rule 1: drafts don't notify
		new_publish_status = timetable_doc.get("publish_status") or "DRAFT"
		old_publish_status = (old_state or {}).get("publish_status") or "DRAFT"

		if new_publish_status != "PUBLISHED" and old_publish_status != "PUBLISHED":
			return  # entry is and was a draft → silent

		# Determine the dominant event_type for this save
		event_types = _classify_changes(changes, old_publish_status, new_publish_status)
		if not event_types:
			return  # nothing notification-worthy changed

		# Dedupe: only the highest-urgency event type wins for this save
		# (so a save that changes both venue AND time fires ONE notification, not two)
		event_type = _pick_dominant_event(event_types)

		recipients = _resolve_recipients(timetable_doc, event_type)
		if not recipients:
			return

		title, message = _compose_message(timetable_doc, event_type, old_state)

		for recipient_user, recipient_role in recipients:
			_dispatch_one(
				timetable_doc=timetable_doc,
				event_type=event_type,
				recipient=recipient_user,
				recipient_role=recipient_role,
				title=title,
				message=message,
			)
	except Exception:
		# Notification failures must never block the user's save
		frappe.logger().warning(
			f"[TVMS notify] failed for Timetable {timetable_doc.name}",
			exc_info=True,
		)


def notify_timetable_entry_deleted(timetable_doc):
	"""Called from Timetable.on_trash — only fires for PUBLISHED entries."""
	try:
		if (timetable_doc.get("publish_status") or "DRAFT") != "PUBLISHED":
			return  # draft delete → silent

		recipients = _resolve_recipients(timetable_doc, EVT_DELETED)
		if not recipients:
			return

		title, message = _compose_message(timetable_doc, EVT_DELETED, old_state=None)
		for recipient_user, recipient_role in recipients:
			_dispatch_one(
				timetable_doc=timetable_doc,
				event_type=EVT_DELETED,
				recipient=recipient_user,
				recipient_role=recipient_role,
				title=title,
				message=message,
			)
	except Exception:
		frappe.logger().warning(
			f"[TVMS notify] delete failed for Timetable {timetable_doc.name}",
			exc_info=True,
		)


def notify_bulk_publish(program=None, year_level=None, semester=None, academic_year=None, count=0):
	"""Called from publish_timetable() AFTER the bulk update.

	One aggregate notification per recipient instead of N (where N = published entries).
	"""
	try:
		if count == 0:
			return

		recipients = _resolve_program_recipients(program, year_level)
		if not recipients:
			return

		scope = _format_scope(program, year_level, semester, academic_year)
		title = _("Timetable published")
		message = _(
			"{0} timetable entr{1} for {2} {3} now published. "
			"Open the timetable to see your schedule."
		).format(
			count,
			"y is" if count == 1 else "ies are",
			scope,
			"have" if count == 1 else "are",
		)

		for recipient_user, recipient_role in recipients:
			_dispatch_aggregate(
				event_type=EVT_BULK_PUBLISH,
				recipient=recipient_user,
				recipient_role=recipient_role,
				title=title,
				message=message,
				payload={
					"program": program, "year_level": year_level,
					"semester": semester, "academic_year": academic_year,
					"count": count,
				},
			)
	except Exception:
		frappe.logger().warning(f"[TVMS notify] bulk publish failed", exc_info=True)


def notify_bulk_unpublish(program=None, year_level=None, semester=None, academic_year=None, count=0):
	"""Called from unpublish_timetable() AFTER the bulk update."""
	try:
		if count == 0:
			return

		recipients = _resolve_program_recipients(program, year_level)
		if not recipients:
			return

		scope = _format_scope(program, year_level, semester, academic_year)
		title = _("Timetable being updated")
		message = _(
			"The {0} timetable is being reorganised ({1} entr{2} removed from view). "
			"Updates will be published shortly."
		).format(scope, count, "y" if count == 1 else "ies")

		for recipient_user, recipient_role in recipients:
			_dispatch_aggregate(
				event_type=EVT_BULK_UNPUBLISH,
				recipient=recipient_user,
				recipient_role=recipient_role,
				title=title,
				message=message,
				payload={
					"program": program, "year_level": year_level,
					"semester": semester, "academic_year": academic_year,
					"count": count,
				},
			)
	except Exception:
		frappe.logger().warning(f"[TVMS notify] bulk unpublish failed", exc_info=True)


# ============================================================
# Internal — classify, resolve, compose, dispatch
# ============================================================

def _classify_changes(changes, old_publish_status, new_publish_status):
	"""Map field changes to event types.

	Returns a set of event_type strings (one per distinct change category).
	An empty set means nothing notification-worthy changed.
	"""
	results = set()

	# Transition events take precedence
	if old_publish_status != "PUBLISHED" and new_publish_status == "PUBLISHED":
		results.add(EVT_PUBLISHED)
	elif old_publish_status == "PUBLISHED" and new_publish_status != "PUBLISHED":
		results.add(EVT_UNPUBLISHED)

	# Only fire field-change notifications if the entry IS published now
	if new_publish_status != "PUBLISHED":
		return results

	# Map field-level changes to event categories
	if not changes:
		return results
	for change in changes:
		fieldname = change.get("fieldname")
		if fieldname in NOTIFIABLE_FIELDS:
			results.add(NOTIFIABLE_FIELDS[fieldname])

	return results


def _pick_dominant_event(event_types):
	"""When a save triggers multiple categories, pick the most user-relevant one.

	Priority order: PUBLISHED/UNPUBLISHED > TIME > VENUE > LECTURER.
	"""
	priority = [
		EVT_UNPUBLISHED,      # most disruptive
		EVT_PUBLISHED,        # new timetable
		EVT_TIME_CHANGED,     # critical to students
		EVT_VENUE_CHANGED,    # critical to students
		EVT_LECTURER_CHANGED, # less critical
	]
	for evt in priority:
		if evt in event_types:
			return evt
	return next(iter(event_types))  # fallback


def _resolve_recipients(timetable_doc, event_type):
	"""Determine who should be notified for one entry-level change.

	Returns a list of (user_id, role_label) tuples.
	Deduplicated — a user with two roles only gets one notification per event.
	"""
	recipients = {}  # user → role

	# The entry's lecturer always gets notified (unless they made the change themselves)
	lecturer = timetable_doc.get("lecturer")
	if lecturer and lecturer != frappe.session.user:
		recipients[lecturer] = "Lecturer"

	# CRs of the program-year (for relay)
	program = timetable_doc.get("program")
	year_level = timetable_doc.get("year_level")
	for cr in _crs_for_program(program, year_level):
		recipients.setdefault(cr, "Class Representative (CR)")

	# Students get notified ONLY for high-urgency changes (delete, time, venue)
	# For low-urgency (publish, lecturer change), only CR relays them
	if event_type in HIGH_URGENCY:
		for student in _students_for_program(program, year_level):
			recipients.setdefault(student, "Student")

	return [(user, role) for user, role in recipients.items()]


def _resolve_program_recipients(program, year_level):
	"""For bulk publish/unpublish — get every CR + student in the program-year."""
	recipients = {}
	for cr in _crs_for_program(program, year_level):
		recipients.setdefault(cr, "Class Representative (CR)")
	for student in _students_for_program(program, year_level):
		recipients.setdefault(student, "Student")
	return [(user, role) for user, role in recipients.items()]


def _crs_for_program(program, year_level):
	"""Return all CR users.

	NOTE: today every CR receives every program's notifications because we don't
	yet have a per-user program/year link. Once that mapping exists, narrow the
	query with: AND u.program = %(program)s AND u.year_level = %(year_level)s.
	The function signature already accepts program/year_level so the upgrade is
	transparent to callers.
	"""
	return frappe.db.sql_list("""
		SELECT DISTINCT u.name
		FROM   `tabHas Role` hr
		INNER JOIN `tabUser` u ON hr.parent = u.name
		WHERE  hr.role = 'Class Representative (CR)'
		AND    u.enabled = 1
	""")


def _students_for_program(program, year_level):
	"""Return all Student users. Same caveat as _crs_for_program."""
	return frappe.db.sql_list("""
		SELECT DISTINCT u.name
		FROM   `tabHas Role` hr
		INNER JOIN `tabUser` u ON hr.parent = u.name
		WHERE  hr.role = 'Student'
		AND    u.enabled = 1
	""")


def _compose_message(timetable_doc, event_type, old_state):
	"""Build the title + message for a per-entry notification."""
	course_name   = _resolve_label("Course", timetable_doc.get("course"), "course_name")
	venue_name    = _resolve_label("Venue",  timetable_doc.get("venue"),  "venue_name") or "—"
	date          = timetable_doc.get("date")
	start         = str(timetable_doc.get("start_time"))[:5] if timetable_doc.get("start_time") else "—"
	end           = str(timetable_doc.get("end_time"))[:5]   if timetable_doc.get("end_time")   else "—"

	if event_type == EVT_DELETED:
		title = _("Class cancelled: {0}").format(course_name)
		message = _("The {0} class scheduled for {1} ({2}–{3}) at {4} has been cancelled.").format(
			course_name, date, start, end, venue_name,
		)
		return title, message

	if event_type == EVT_PUBLISHED:
		title = _("Class added: {0}").format(course_name)
		message = _("{0} is now in your timetable: {1} from {2} to {3}, venue {4}.").format(
			course_name, date, start, end, venue_name,
		)
		return title, message

	if event_type == EVT_UNPUBLISHED:
		title = _("Class removed (draft): {0}").format(course_name)
		message = _("The {0} class on {1} has been moved back to draft and is no longer official.").format(
			course_name, date,
		)
		return title, message

	if event_type == EVT_TIME_CHANGED:
		old_start = str((old_state or {}).get("start_time"))[:5] if (old_state or {}).get("start_time") else "—"
		old_end   = str((old_state or {}).get("end_time"))[:5]   if (old_state or {}).get("end_time")   else "—"
		old_date  = (old_state or {}).get("date") or date
		title = _("Class rescheduled: {0}").format(course_name)
		message = _(
			"{0} has been rescheduled.\n"
			"Was: {1} {2}–{3}\n"
			"Now: {4} {5}–{6}\n"
			"Venue: {7}"
		).format(course_name, old_date, old_start, old_end, date, start, end, venue_name)
		return title, message

	if event_type == EVT_VENUE_CHANGED:
		old_venue = _resolve_label("Venue", (old_state or {}).get("venue"), "venue_name") or "—"
		title = _("Venue changed: {0}").format(course_name)
		message = _(
			"{0} on {1} ({2}–{3}) has moved venue.\n"
			"Was: {4}\n"
			"Now: {5}"
		).format(course_name, date, start, end, old_venue, venue_name)
		return title, message

	if event_type == EVT_LECTURER_CHANGED:
		new_lect = _resolve_label("User", timetable_doc.get("lecturer"), "full_name") or "—"
		title = _("Lecturer changed: {0}").format(course_name)
		message = _("{0} on {1} will now be taught by {2}.").format(
			course_name, date, new_lect,
		)
		return title, message

	# Fallback
	title = _("Timetable change: {0}").format(course_name)
	message = _("Your {0} timetable entry has been updated.").format(course_name)
	return title, message


def _dispatch_one(timetable_doc, event_type, recipient, recipient_role, title, message):
	"""Send one in-system notification + write the audit row + push realtime + optional email."""
	# Step 1 — in-system notification record (the bell inbox)
	_create_tvms_notification(
		title=title,
		message=message,
		recipient=recipient,
		recipient_role=recipient_role,
		reference_type="Timetable",
		reference_name=timetable_doc.name,
		channel="in-system",
	)

	# Step 2 — realtime push so active Desk users see the bell update instantly
	frappe.publish_realtime(
		"tvms_notification",
		{
			"title":      title,
			"event_type": event_type,
			"timetable":  timetable_doc.name,
		},
		user=recipient,
		after_commit=True,
	)

	# Step 3 — audit trail (links into the same TVMS Audit Log used for sessions)
	log_event(
		event_type=event_type,
		summary=title,
		subject_type="Timetable",
		subject_name=timetable_doc.name,
		subject_label=_resolve_label("Course", timetable_doc.get("course"), "course_name"),
		recipient=recipient,
		recipient_role=recipient_role,
		channel="in-system",
		payload={
			"event": event_type,
			"program": timetable_doc.get("program"),
			"year_level": timetable_doc.get("year_level"),
		},
	)

	# Step 4 — email for high-urgency events only
	if event_type in HIGH_URGENCY and _email_enabled():
		_send_email(recipient, title, message, timetable_doc)


def _dispatch_aggregate(event_type, recipient, recipient_role, title, message, payload):
	"""Bulk-operation variant — no per-entry subject linkage."""
	_create_tvms_notification(
		title=title,
		message=message,
		recipient=recipient,
		recipient_role=recipient_role,
		reference_type="Timetable",
		reference_name=None,
		channel="in-system",
	)

	frappe.publish_realtime(
		"tvms_notification",
		{"title": title, "event_type": event_type, "payload": payload},
		user=recipient,
		after_commit=True,
	)

	log_event(
		event_type=event_type,
		summary=title,
		subject_type="Timetable",
		subject_name=None,
		subject_label=payload.get("program") or "All programs",
		recipient=recipient,
		recipient_role=recipient_role,
		channel="in-system",
		payload=payload,
	)

	if event_type in HIGH_URGENCY and _email_enabled():
		_send_email(recipient, title, message, timetable_doc=None)


def _send_email(recipient, title, message, timetable_doc):
	"""Fire-and-forget email. Frappe's mail queue handles retries."""
	try:
		email = frappe.db.get_value("User", recipient, "email")
		if not email:
			return
		body = "<h3>{0}</h3><p>{1}</p>".format(
			title, message.replace("\n", "<br>"),
		)
		if timetable_doc:
			body += '<p><a href="/app/timetable/{0}">Open in TVMS</a></p>'.format(
				timetable_doc.name,
			)
		frappe.sendmail(recipients=[email], subject=title, message=body)
	except Exception:
		frappe.logger().warning(
			f"[TVMS notify] email send failed for {recipient}",
			exc_info=True,
		)


def _email_enabled():
	"""Read the global email toggle from TVMS Settings (defaults to True)."""
	try:
		settings = frappe.get_single_doc("TVMS Settings").as_dict()
		return settings.get("email_enabled", True)
	except Exception:
		return True


def _resolve_label(doctype, docname, fieldname):
	"""Return a display label for a linked record. Falls back to docname on error."""
	if not docname:
		return docname or ""
	try:
		val = frappe.db.get_value(doctype, docname, fieldname)
		return val or docname
	except Exception:
		return docname


def _format_scope(program, year_level, semester, academic_year):
	"""Build a human-readable label like 'BSc-IT Year 1, Semester 1'."""
	parts = []
	if program:    parts.append(program)
	if year_level: parts.append(f"Year {year_level}")
	if semester:   parts.append(semester)
	if academic_year: parts.append(academic_year)
	return " ".join(parts) if parts else "the"