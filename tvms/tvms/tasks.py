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

	# ── Step 2: mark occupied venues IN-USE ─────────────────────────
	if should_be_in_use:
		frappe.db.set_value(
			"Venue",
			{"name": ["in", list(should_be_in_use)], "current_status": ["!=", "IN-USE"]},
			"current_status",
			"IN-USE",
		)

	# ── Step 3: mark vacated venues FREE ────────────────────────────
	# Any venue stored as IN-USE with no active session → FREE.
	currently_in_use = set(frappe.db.sql_list(
		"SELECT name FROM `tabVenue` WHERE current_status = 'IN-USE'"
	))
	should_be_free = currently_in_use - should_be_in_use

	if should_be_free:
		frappe.db.set_value(
			"Venue",
			{"name": ["in", list(should_be_free)], "current_status": "IN-USE"},
			"current_status",
			"FREE",
		)
