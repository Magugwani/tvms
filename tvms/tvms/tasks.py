import frappe
from frappe.utils import add_to_date, now_datetime, nowdate


def expire_pending_sessions():
	"""FR-25: Expire PENDING sessions where the grace period has lapsed without confirmation.

	Grace period is read from TVMS Settings (grace_period_minutes), falling back to
	site config 'session_grace_period_minutes', then hardcoded default of 40 min.
	"""
	grace_minutes = (
		frappe.db.get_single_value("TVMS Settings", "grace_period_minutes")
		or frappe.conf.get("session_grace_period_minutes", 40)
	)
	cutoff = add_to_date(now_datetime(), minutes=-grace_minutes)

	pending = frappe.db.get_all(
		"Emergency session",
		filters=[
			["status", "=", "PENDING"],
			["start_time", "<=", cutoff],
		],
		fields=["name"],
	)

	for row in pending:
		try:
			doc = frappe.get_doc("Emergency session", row["name"])
			doc.expire_session()
		except Exception:
			frappe.logger().error(
				f"Failed to expire session {row['name']}",
				exc_info=True,
			)


def complete_confirmed_sessions():
	"""Auto-complete CONFIRMED sessions whose end_time has passed.

	Runs on the 'all' scheduler (every minute) so completion is detected
	within one minute of the session ending.
	"""
	now = now_datetime()

	confirmed = frappe.db.get_all(
		"Emergency session",
		filters=[
			["status", "=", "CONFIRMED"],
			["end_time", "<=", now],
		],
		fields=["name"],
	)

	for row in confirmed:
		try:
			doc = frappe.get_doc("Emergency session", row["name"])
			doc.complete_session()
		except Exception:
			frappe.logger().error(
				f"Failed to auto-complete session {row['name']}",
				exc_info=True,
			)


def sync_timetable_venue_statuses():
	"""FR-60: Sync venue current_status for timetable-driven occupancy.

	Emergency session transitions are already handled synchronously in
	emergency_session.py._update_venue_status(). This task covers the gap
	for regular timetable sessions (which have no status-change trigger).

	Two bulk SQL queries instead of per-venue loops — stays fast even with
	1 000 venues (per SRS non-functional requirement).
	"""
	now = now_datetime()
	today = nowdate()
	current_time = now.strftime("%H:%M:%S")

	# ── Step 1: venues that should be IN-USE right now ──────────────
	# A timetable session is active OR a CONFIRMED emergency session is active.
	tt_active = frappe.db.sql_list("""
		SELECT DISTINCT venue
		FROM `tabTimetable`
		WHERE date      = %(today)s
		  AND status   != 'COMPLETED'
		  AND start_time <= %(now_time)s
		  AND end_time    > %(now_time)s
		  AND venue IS NOT NULL
	""", {"today": today, "now_time": current_time})

	ems_active = frappe.db.sql_list("""
		SELECT DISTINCT venue
		FROM `tabEmergency session`
		WHERE status    = 'CONFIRMED'
		  AND start_time <= %(now)s
		  AND end_time    > %(now)s
		  AND venue IS NOT NULL
	""", {"now": now})

	should_be_in_use = set(tt_active) | set(ems_active)

	ems_booked = frappe.db.sql_list("""
		SELECT DISTINCT venue
		FROM `tabEmergency session`
		WHERE status IN ('PENDING', 'CONFIRMED')
		  AND end_time > %(now)s
		  AND venue IS NOT NULL
	""", {"now": now})
	should_be_booked = set(ems_booked) - should_be_in_use

	# ── Step 2: mark occupied venues IN-USE ─────────────────────────
	if should_be_in_use:
		frappe.db.set_value(
			"Venue",
			{"name": ["in", list(should_be_in_use)], "current_status": ["!=", "IN-USE"]},
			"current_status",
			"IN-USE",
		)

	# ── Step 3: mark reserved emergency venues BOOKED ───────────────
	if should_be_booked:
		frappe.db.set_value(
			"Venue",
			{"name": ["in", list(should_be_booked)], "current_status": ["!=", "BOOKED"]},
			"current_status",
			"BOOKED",
		)

	# ── Step 4: mark vacated venues FREE ────────────────────────────
	# Any venue stored as IN-USE/BOOKED with no active or reserved session → FREE.
	currently_in_use = set(frappe.db.sql_list(
		"SELECT name FROM `tabVenue` WHERE current_status IN ('IN-USE', 'BOOKED')"
	))
	should_be_free = currently_in_use - should_be_in_use - should_be_booked

	if should_be_free:
		frappe.db.set_value(
			"Venue",
			{"name": ["in", list(should_be_free)], "current_status": ["in", ["IN-USE", "BOOKED"]]},
			"current_status",
			"FREE",
		)


# ============================================================
# 2-HOUR REMINDER (FR-33)
# ============================================================
def send_two_hour_reminders():
	"""FR-33: Notify recipients ~2 hours before session start.
 
	Scheduler config (in hooks.py):
 
	    "cron": {
	        "*/5 * * * *": [
	            "tvms.tvms.tasks.send_two_hour_reminders",
	            ...
	        ],
	    }
 
	The 5-minute cadence means each session falls inside the look-ahead
	window for two consecutive ticks. The reminder_sent_at field on
	Emergency Session ensures we only notify once.
	"""
	now = now_datetime()
 
	# Window: sessions starting between 1h55m and 2h05m from now
	window_start = add_to_date(now, hours=1, minutes=55)
	window_end   = add_to_date(now, hours=2, minutes=5)
 
	sessions = frappe.db.get_all(
		"Emergency session",
		filters=[
			["status",       "in", ["PENDING", "CONFIRMED"]],
			["start_time",   ">=", window_start],
			["start_time",   "<=", window_end],
			["reminder_sent_at", "is", "not set"],
		],
		fields=[
			"name", "title", "venue", "course", "lecturer",
			"start_time", "end_time", "status", "created_by",
			"expected_students", "is_critical",
		],
	)
 
	if not sessions:
		return
 
	from tvms.tvms.doctype.tvms_notifications.tvms_notifications import _create_tvms_notification
	from tvms.tvms.doctype.tvms_audit_log.tvms_audit_log import log_event
 
	for session in sessions:
		recipients = _reminder_recipients(session)
		if not recipients:
			# Still mark as sent so we don't recompute every 5 minutes
			frappe.db.set_value(
				"Emergency session", session["name"],
				"reminder_sent_at", now,
			)
			continue
 
		# Compose the message — emphasises the 2-hour window
		start_local = str(session["start_time"])[:16]   # "2026-09-15 14:00"
		venue_label = session.get("venue") or _("To be confirmed")
		course_label = session.get("course") or _("Session")
 
		title   = _("Reminder: {0} starts in ~2 hours").format(course_label)
		message = _(
			"Emergency session <strong>{0}</strong> begins at <strong>{1}</strong> "
			"in venue <strong>{2}</strong>. Status: {3}."
		).format(
			session["title"] or course_label,
			start_local,
			venue_label,
			session["status"],
		)
 
		# Audit row — one per session, before per-recipient deliveries
		audit_name = log_event(
			event_type="SESSION_REMINDER_SENT",
			summary=f"2-hour reminder for {session['name']} sent to {len(recipients)} recipient(s)",
			subject_type="Emergency session",
			subject_name=session["name"],
			subject_label=session["title"] or course_label,
			actor="Administrator",   # scheduler is a system actor
			channel="in-system",
			payload={
				"start_time":       start_local,
				"recipient_count":  len(recipients),
				"is_critical":      bool(session.get("is_critical")),
			},
		)
 
		for recipient_info in recipients:
			recipient_user, recipient_role = recipient_info
			try:
				_create_tvms_notification(
					title=title,
					message=message,
					recipient=recipient_user,
					recipient_role=recipient_role,
					reference_type="Emergency session",
					reference_name=session["name"],
					channel="in-system",
				)
				frappe.publish_realtime(
					"emergency_session_reminder",
					{
						"session":    session["name"],
						"title":      title,
						"start_time": start_local,
						"venue":      venue_label,
					},
					user=recipient_user,
					after_commit=True,
				)
 
				# Per-recipient audit link
				log_event(
					event_type="NOTIFICATION_SENT",
					summary=f"2-hour reminder → {recipient_user}",
					subject_type="Emergency session",
					subject_name=session["name"],
					recipient=recipient_user,
					recipient_role=recipient_role,
					channel="in-system",
					linked_audit=audit_name,
				)
 
				# FR-41 push hook — fire only if push is configured
				_try_send_push(
					recipient=recipient_user,
					title=title,
					body=message,
					data={
						"type":       "session_reminder",
						"session":    session["name"],
						"start_time": start_local,
					},
				)
			except Exception:
				frappe.logger().warning(
					f"[TVMS reminder] failed for session {session['name']} user {recipient_user}",
					exc_info=True,
				)
 
		# Mark this session as reminded so we don't process it again
		frappe.db.set_value(
			"Emergency session", session["name"],
			"reminder_sent_at", now,
		)
 
	frappe.db.commit()
 
 
def _reminder_recipients(session):
	"""Return [(user_email, role), ...] for one session's reminder.
 
	Always includes: creator (the lecturer/staff who booked it)
	Plus:            assigned lecturer if different from creator
	Plus:            all enabled CRs (they forward to students per existing flow)
	Plus (if is_critical): all enabled Students directly (FR-39 bypass)
	"""
	recipients = []
	seen = set()
 
	def _add(user, role):
		if user and user not in seen:
			seen.add(user)
			recipients.append((user, role))
 
	_add(session.get("created_by"), "Lecturer")
	_add(session.get("lecturer"),   "Lecturer")
 
	# All enabled CRs
	crs = frappe.db.sql("""
		SELECT DISTINCT u.name
		FROM   `tabHas Role` hr
		INNER JOIN `tabUser` u ON hr.parent = u.name
		WHERE  hr.role = 'Class Representative (CR)'
		AND    u.enabled = 1
	""", as_dict=True)
	for cr in crs:
		_add(cr["name"], "Class Representative (CR)")
 
	# FR-39: critical reminders go straight to students too
	if session.get("is_critical"):
		students = frappe.db.sql("""
			SELECT DISTINCT u.name
			FROM   `tabHas Role` hr
			INNER JOIN `tabUser` u ON hr.parent = u.name
			WHERE  hr.role = 'Student'
			AND    u.enabled = 1
		""", as_dict=True)
		for s in students:
			_add(s["name"], "Student")
 
	return recipients
 
 
def _try_send_push(recipient, title, body, data):
	"""Best-effort push notification. Silent no-op if push isn't configured."""
	try:
		from tvms.tvms.api.push_notifications import send_push_to_user
		send_push_to_user(recipient, title, body, data)
	except Exception:
		# Push is optional — never break notification flow if it fails
		pass