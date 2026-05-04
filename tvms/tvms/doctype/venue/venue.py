# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import get_datetime, now_datetime, nowdate


class Venue(Document):

	# ---------------------------------------------------------------
	# FR-60 / FR-61: Status computation
	# ---------------------------------------------------------------

	def compute_status(self, at_time=None):
		"""Derive venue status from live session data at the given moment.

		Returns "IN-USE" or "FREE". Does NOT write to the database — call
		refresh_status() to persist the result.

		Precedence: CONFIRMED emergency session → active timetable session → FREE.
		"""
		at = get_datetime(at_time) if at_time else now_datetime()

		# CONFIRMED emergency session beats everything
		if frappe.db.get_all(
			"Emergency session",
			filters=[
				["venue", "=", self.name],
				["status", "=", "CONFIRMED"],
				["start_time", "<=", at],
				["end_time", ">", at],
			],
			fields=["name"],
			limit=1,
		):
			return "IN-USE"

		# Active timetable session (Timetable stores date + time separately)
		at_date = at.date()
		at_time_str = at.strftime("%H:%M:%S")

		if frappe.db.get_all(
			"Timetable",
			filters=[
				["venue", "=", self.name],
				["date", "=", at_date],
				["status", "!=", "COMPLETED"],
				["start_time", "<=", at_time_str],
				["end_time", ">", at_time_str],
			],
			fields=["name"],
			limit=1,
		):
			return "IN-USE"

		return "FREE"

	def refresh_status(self, at_time=None):
		"""Recompute and persist current_status if it differs from the live value."""
		new_status = self.compute_status(at_time)
		if self.current_status != new_status:
			frappe.db.set_value("Venue", self.name, "current_status", new_status)
			self.current_status = new_status
		return new_status

	# ---------------------------------------------------------------
	# FR-62: Availability check
	# ---------------------------------------------------------------

	def is_available(self, start_time, end_time, exclude_session=None):
		"""True if this venue has no conflicting session in [start_time, end_time)."""
		return _is_venue_available(self.name, start_time, end_time, exclude_session)


# ---------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------

def _is_venue_available(venue_name, start_time, end_time, exclude_session=None):
	"""Check venue availability against Emergency sessions and Timetable.

	PENDING + CONFIRMED emergency sessions are treated as reservations.
	Sessions that are CANCELLED / COMPLETED / EXPIRED are ignored.
	"""
	start_dt = get_datetime(start_time)
	end_dt = get_datetime(end_time)

	# Emergency session overlap
	ems_filters = [
		["venue", "=", venue_name],
		["status", "not in", ["CANCELLED", "COMPLETED", "EXPIRED"]],
		["start_time", "<", end_dt],
		["end_time", ">", start_dt],
	]
	if exclude_session:
		ems_filters.append(["name", "!=", exclude_session])

	if frappe.db.get_all("Emergency session", filters=ems_filters, fields=["name"], limit=1):
		return False

	# Timetable overlap — date is a Date field, times are Time fields
	at_date = start_dt.date()
	start_time_str = start_dt.strftime("%H:%M:%S")
	end_time_str = end_dt.strftime("%H:%M:%S")

	if frappe.db.get_all(
		"Timetable",
		filters=[
			["venue", "=", venue_name],
			["date", "=", at_date],
			["status", "!=", "COMPLETED"],
			["start_time", "<", end_time_str],
			["end_time", ">", start_time_str],
		],
		fields=["name"],
		limit=1,
	):
		return False

	return True


def _blocked_venues(start_time, end_time):
	"""Return the set of venue names with any booking conflict in [start_time, end_time).

	Uses two bulk queries instead of per-venue checks so it scales with
	the number of venues.
	"""
	start_dt = get_datetime(start_time)
	end_dt = get_datetime(end_time)
	at_date = start_dt.date()
	start_time_str = start_dt.strftime("%H:%M:%S")
	end_time_str = end_dt.strftime("%H:%M:%S")

	ems_blocked = frappe.db.sql_list("""
		SELECT DISTINCT venue
		FROM `tabEmergency session`
		WHERE status NOT IN ('CANCELLED', 'COMPLETED', 'EXPIRED')
		  AND start_time < %(end_dt)s
		  AND end_time   > %(start_dt)s
		  AND venue IS NOT NULL
	""", {"start_dt": start_dt, "end_dt": end_dt})

	tt_blocked = frappe.db.sql_list("""
		SELECT DISTINCT venue
		FROM `tabTimetable`
		WHERE date       = %(at_date)s
		  AND status    != 'COMPLETED'
		  AND start_time < %(end_time)s
		  AND end_time   > %(start_time)s
		  AND venue IS NOT NULL
	""", {"at_date": at_date, "start_time": start_time_str, "end_time": end_time_str})

	return set(ems_blocked) | set(tt_blocked)


def _venue_has_resources(venue_resources, required):
	"""True when every item in `required` (set of lowercase strings) is present
	in the venue's comma-separated resources string."""
	if not required:
		return True
	available = {r.strip().lower() for r in (venue_resources or "").split(",") if r.strip()}
	return required.issubset(available)


# ---------------------------------------------------------------
# FR-62: Real-time availability API
# ---------------------------------------------------------------

@frappe.whitelist(methods=["GET"])
def get_all_venues(search: str = None):
	"""Return all venues with full details including live status.

	Used by Desk pages and whitelisted integrations.
	"""
	filters = []
	if search:
		filters.append(["venue_name", "like", f"%{search}%"])

	return frappe.db.get_all(
		"Venue",
		filters=filters,
		fields=["name", "venue_name", "venue_code", "location", "capacity", "resources", "current_status"],
		order_by="venue_name asc",
	)


@frappe.whitelist(methods=["GET"])
def get_all_venue_statuses():
	"""Return the stored current_status for every venue.

	Used by Desk pages for the initial venue status snapshot.
	Subsequent updates arrive via the venue_status_update WebSocket event.
	"""
	rows = frappe.db.get_all(
		"Venue",
		fields=["name", "venue_name", "current_status"],
		order_by="name asc",
	)
	# Return as a dict keyed by venue name for O(1) lookups in Desk page scripts.
	return {r["name"]: r["current_status"] or "FREE" for r in rows}

@frappe.whitelist(methods=["GET"])
def get_venue_status(venue: str, at_time: str = None):
	"""Return the live status of a single venue.

	Params:
	  venue    — Venue name (venue_code)
	  at_time  — ISO datetime; defaults to now
	"""
	if not frappe.db.exists("Venue", venue):
		frappe.throw(_("Venue not found: {0}").format(venue), frappe.DoesNotExistError)

	doc = frappe.get_doc("Venue", venue)
	live_status = doc.compute_status(at_time)

	return {
		"venue": venue,
		"venue_name": doc.venue_name,
		"capacity": doc.capacity,
		"resources": doc.resources,
		"live_status": live_status,
		"stored_status": doc.current_status,
		"in_sync": live_status == doc.current_status,
	}


@frappe.whitelist(methods=["GET"])
def get_available_venues(start_time: str, end_time: str, expected_students: int = None):
	"""FR-62: Return all venues with no conflict in [start_time, end_time).

	Params:
	  start_time       — ISO datetime
	  end_time         — ISO datetime
	  expected_students — optional minimum capacity filter
	"""
	if not start_time or not end_time:
		frappe.throw(_("start_time and end_time are required"))

	filters = []
	if expected_students:
		filters.append(["capacity", ">=", int(expected_students)])

	all_venues = frappe.db.get_all(
		"Venue",
		filters=filters,
		fields=["name", "venue_name", "capacity", "resources", "current_status"],
		order_by="capacity asc",
	)

	blocked = _blocked_venues(start_time, end_time)

	return [v for v in all_venues if v["name"] not in blocked]


# ---------------------------------------------------------------
# FR-63: Smart venue recommendation
# ---------------------------------------------------------------

@frappe.whitelist(methods=["GET"])
def recommend_venue(
	expected_students: int,
	start_time: str,
	end_time: str,
	required_resources: str = None,
):
	"""Suggest the best-fit venue for a session.

	Selection criteria (in order):
	  1. capacity >= expected_students
	  2. all required_resources present (comma-separated)
	  3. no booking conflict in [start_time, end_time)
	  4. sorted by capacity ascending — smallest venue that fits wins
	"""
	if not expected_students or not start_time or not end_time:
		frappe.throw(_("expected_students, start_time, and end_time are required"))

	candidates = frappe.db.get_all(
		"Venue",
		filters=[["capacity", ">=", int(expected_students)]],
		fields=["name", "venue_name", "capacity", "resources"],
		order_by="capacity asc",
	)

	# Resource filter
	if required_resources:
		needed = {r.strip().lower() for r in required_resources.split(",") if r.strip()}
		candidates = [v for v in candidates if _venue_has_resources(v.get("resources"), needed)]

	# Availability filter — one bulk query, no per-venue DB hits
	blocked = _blocked_venues(start_time, end_time)
	available = [v for v in candidates if v["name"] not in blocked]

	return available
