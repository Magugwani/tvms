# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

"""Analytics and reporting APIs — FR-44 to FR-47."""

import frappe
from frappe import _
from frappe.utils import getdate, add_days, now_datetime, nowdate


@frappe.whitelist(methods=["GET"])
def get_dashboard_stats():
	"""Return top-level live stats for the TVMS dashboard."""
	today = nowdate()
	now   = now_datetime()
	current_time = now.strftime("%H:%M:%S")

	total_venues  = frappe.db.count("Venue")
	venues_in_use = frappe.db.count("Venue", {"current_status": "IN-USE"})
	venues_booked = frappe.db.count("Venue", {"current_status": "BOOKED"})

	sessions_today = frappe.db.count(
		"Timetable",
		[["date", "=", today], ["status", "!=", "COMPLETED"]],
	)

	active_emergency = frappe.db.count(
		"Emergency session",
		[["status", "in", ["PENDING", "CONFIRMED"]]],
	)

	# Sessions happening RIGHT NOW
	live_now = frappe.db.count(
		"Timetable",
		[
			["date", "=", today],
			["start_time", "<=", current_time],
			["end_time", ">", current_time],
			["status", "!=", "COMPLETED"],
		],
	)

	total_courses = frappe.db.count("Course")

	week_start = add_days(today, -getdate(today).weekday())
	imports_this_week = len(frappe.db.sql_list(
		"SELECT DISTINCT import_batch FROM `tabTimetable` WHERE date >= %s AND import_batch IS NOT NULL",
		[week_start],
	))

	return {
		"total_venues":       total_venues,
		"venues_in_use":      venues_in_use,
		"venues_booked":      venues_booked,
		"venues_free":        total_venues - venues_in_use - venues_booked,
		"sessions_today":     sessions_today,
		"live_now":           live_now,
		"active_emergency":   active_emergency,
		"total_courses":      total_courses,
		"imports_this_week":  imports_this_week,
	}


@frappe.whitelist(methods=["GET"])
def get_venue_utilization(date_from: str, date_to: str, venue: str = None):
	"""FR-44: Compute utilization % per venue for a date range.

	Utilization = total session hours / available hours × 100
	Available hours: 10 h/day (08:00–18:00) × working days (Mon–Fri).
	"""
	if not date_from or not date_to:
		frappe.throw(_("date_from and date_to are required"))

	start = getdate(date_from)
	end   = getdate(date_to)

	# Count working days in range
	working_days = 0
	cur = start
	while cur <= end:
		if cur.weekday() < 5:  # Mon=0 … Fri=4
			working_days += 1
		cur = add_days(cur, 1)

	available_hours = max(working_days * 10, 1)  # avoid division by zero

	# Timetable: hours used per venue
	tt_filter = "AND venue = %(venue)s" if venue else ""
	tt_rows = frappe.db.sql(f"""
		SELECT venue,
		       SUM(TIME_TO_SEC(TIMEDIFF(end_time, start_time)) / 3600.0) AS hours
		FROM   `tabTimetable`
		WHERE  date >= %(start)s AND date <= %(end)s
		AND    venue IS NOT NULL AND venue != ''
		{tt_filter}
		GROUP BY venue
	""", {"start": start, "end": end, "venue": venue}, as_dict=True)

	tt_map = {r["venue"]: float(r["hours"] or 0) for r in tt_rows}

	# Emergency sessions: hours used per venue (CONFIRMED + COMPLETED only)
	ems_filter = "AND venue = %(venue)s" if venue else ""
	ems_rows = frappe.db.sql(f"""
		SELECT venue,
		       SUM(TIMESTAMPDIFF(SECOND, start_time, end_time) / 3600.0) AS hours
		FROM   `tabEmergency session`
		WHERE  DATE(start_time) >= %(start)s AND DATE(end_time) <= %(end)s
		AND    status IN ('CONFIRMED', 'COMPLETED')
		AND    venue IS NOT NULL AND venue != ''
		{ems_filter}
		GROUP BY venue
	""", {"start": start, "end": end, "venue": venue}, as_dict=True)

	ems_map = {r["venue"]: float(r["hours"] or 0) for r in ems_rows}

	venue_filter = [["name", "=", venue]] if venue else []
	venues = frappe.db.get_all(
		"Venue",
		filters=venue_filter,
		fields=["name", "venue_name", "location", "capacity", "current_status"],
		order_by="venue_name asc",
	)

	result = []
	for v in venues:
		hours = tt_map.get(v["name"], 0) + ems_map.get(v["name"], 0)
		pct   = round(min(hours / available_hours * 100, 100), 1)
		result.append({
			"venue":            v["name"],
			"venue_name":       v["venue_name"],
			"location":         v.get("location") or "",
			"capacity":         v["capacity"],
			"hours_used":       round(hours, 1),
			"available_hours":  available_hours,
			"utilization_pct":  pct,
			"current_status":   v["current_status"] or "FREE",
		})

	result.sort(key=lambda x: x["utilization_pct"], reverse=True)
	return result


@frappe.whitelist(methods=["GET"])
def get_peak_hours(date_from: str = None, date_to: str = None):
	"""FR-44: Session counts by start hour of day for charting peak usage."""
	today  = nowdate()
	start  = getdate(date_from) if date_from else add_days(today, -30)
	end    = getdate(date_to)   if date_to   else today

	tt_rows = frappe.db.sql("""
		SELECT HOUR(start_time) AS hour, COUNT(*) AS cnt
		FROM   `tabTimetable`
		WHERE  date >= %(start)s AND date <= %(end)s
		GROUP BY HOUR(start_time)
	""", {"start": start, "end": end}, as_dict=True)

	ems_rows = frappe.db.sql("""
		SELECT HOUR(start_time) AS hour, COUNT(*) AS cnt
		FROM   `tabEmergency session`
		WHERE  DATE(start_time) >= %(start)s AND DATE(start_time) <= %(end)s
		AND    status IN ('CONFIRMED', 'COMPLETED', 'CANCELLED')
		GROUP BY HOUR(start_time)
	""", {"start": start, "end": end}, as_dict=True)

	hour_map = {h: 0 for h in range(7, 21)}
	for r in tt_rows:
		h = int(r["hour"])
		if h in hour_map:
			hour_map[h] += int(r["cnt"])
	for r in ems_rows:
		h = int(r["hour"])
		if h in hour_map:
			hour_map[h] += int(r["cnt"])

	return [{"hour": h, "label": f"{h:02d}:00", "count": hour_map[h]} for h in range(7, 21)]


@frappe.whitelist(methods=["GET"])
def get_session_summary(date_from: str = None, date_to: str = None, lecturer: str = None, venue: str = None):
	"""Return a summary of sessions grouped by course for reporting."""
	today = nowdate()
	start = getdate(date_from) if date_from else add_days(today, -30)
	end   = getdate(date_to)   if date_to   else today

	filters = [
		["date", ">=", start],
		["date", "<=", end],
	]
	if lecturer:
		filters.append(["lecturer", "=", lecturer])
	if venue:
		filters.append(["venue", "=", venue])

	rows = frappe.db.get_list(
		"Timetable",
		filters=filters,
		fields=["course", "lecturer", "venue", "date", "start_time", "end_time", "duration_hours"],
		order_by="date asc",
	)

	course_map = {r["name"]: r["course_name"] for r in frappe.db.get_all("Course", fields=["name", "course_name"])}
	venue_map  = {r["name"]: r["venue_name"]  for r in frappe.db.get_all("Venue",  fields=["name", "venue_name"])}
	user_map   = {r["name"]: r["full_name"]   for r in frappe.db.get_all("User", filters={"enabled": 1}, fields=["name", "full_name"])}

	totals = {}
	for r in rows:
		key = r["course"]
		if key not in totals:
			totals[key] = {
				"course":       key,
				"course_name":  course_map.get(key) or key,
				"sessions":     0,
				"total_hours":  0,
			}
		totals[key]["sessions"]    += 1
		totals[key]["total_hours"] += float(r.get("duration_hours") or 0)

	result = list(totals.values())
	result.sort(key=lambda x: x["sessions"], reverse=True)
	return result
