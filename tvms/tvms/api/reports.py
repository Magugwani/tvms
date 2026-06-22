# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

"""Analytics and reporting APIs — FR-44 to FR-48.

This file is the complete replacement for tvms/tvms/api/reports.py.
What changed from the previous version:

  FR-47 additions:
    - department filter on get_venue_utilization
    - department filter on get_session_summary
    - program filter on get_session_summary
    - lecturer filter on get_venue_utilization
    - get_filter_options() — populates dropdowns on the reports page

  FR-48 additions:
    - export_venue_utilization (CSV / Excel / PDF)
    - export_session_summary  (CSV / Excel / PDF)
    - export_peak_hours       (CSV only — single dataset, PDF/Excel
                                doesn't add value over the chart)
"""

import io
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import getdate, add_days, now_datetime, nowdate
from frappe.utils.pdf import get_pdf


# ============================================================
# Dashboard stats — unchanged
# ============================================================

@frappe.whitelist(methods=["GET", "POST"])
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


# ============================================================
# FR-47: Filter options for dropdowns
# ============================================================

@frappe.whitelist(methods=["GET", "POST"])
def get_filter_options():
	"""Return values to populate the reports-page filter dropdowns.

	Used by the page on load — turns the filter row into proper Select
	inputs instead of free-text Data fields. Each list is sorted and
	already de-duplicated.
	"""
	departments = frappe.db.get_all(
		"Departments",
		filters={"status": "Active"},
		fields=["name", "department_name"],
		order_by="department_name asc",
	)

	programs = frappe.db.get_all(
		"Program",
		filters={"status": "Active"},
		fields=["name", "program_name", "department"],
		order_by="program_name asc",
	)

	# Lecturers — distinct users that appear in either Timetable or Emergency session
	tt_lecturers = frappe.db.sql_list(
		"SELECT DISTINCT lecturer FROM `tabTimetable` "
		"WHERE lecturer IS NOT NULL AND lecturer != ''"
	) or []
	ems_lecturers = frappe.db.sql_list(
		"SELECT DISTINCT lecturer FROM `tabEmergency session` "
		"WHERE lecturer IS NOT NULL AND lecturer != ''"
	) or []
	all_lecturer_ids = list(set(tt_lecturers) | set(ems_lecturers))

	lecturers = frappe.db.get_all(
		"User",
		filters={"name": ["in", all_lecturer_ids]} if all_lecturer_ids else None,
		fields=["name", "full_name"],
		order_by="full_name asc",
	) if all_lecturer_ids else []

	venues = frappe.db.get_all(
		"Venue",
		fields=["name", "venue_name", "building_name"],
		order_by="venue_name asc",
	)

	return {
		"departments": departments,
		"programs":    programs,
		"lecturers":   lecturers,
		"venues":      venues,
	}


# ============================================================
# Venue utilization — now with department + lecturer filters
# ============================================================

@frappe.whitelist(methods=["GET", "POST"])
def get_venue_utilization(
	date_from: str,
	date_to: str,
	venue: str = None,
	department: str = None,
	program: str = None,
	lecturer: str = None,
):
	"""FR-44 + FR-47: Utilization % per venue for a date range.

	When department/program/lecturer filters are supplied, the hours-used
	figure counts only sessions matching those filters. The denominator
	(available_hours) is computed from working-day count irrespective
	of filters, so "30% utilization filtered to dept X" reads as
	"this venue was 30% busy with dept X sessions" — which is what
	an admin actually wants.
	"""
	if not date_from or not date_to:
		frappe.throw(_("date_from and date_to are required"))

	start = getdate(date_from)
	end   = getdate(date_to)

	# Count working days in range
	working_days = 0
	cur = start
	while cur <= end:
		if cur.weekday() < 5:
			working_days += 1
		cur = add_days(cur, 1)

	available_hours = max(working_days * 10, 1)

	# ── Timetable hours ─────────────────────────────────────────────
	tt_where = ["date >= %(start)s", "date <= %(end)s"]
	params   = {"start": start, "end": end}

	if venue:
		tt_where.append("venue = %(venue)s")
		params["venue"] = venue
	if lecturer:
		tt_where.append("lecturer = %(lecturer)s")
		params["lecturer"] = lecturer
	if department:
		tt_where.append("department = %(department)s")
		params["department"] = department
	if program:
		tt_where.append("program = %(program)s")
		params["program"] = program

	tt_rows = frappe.db.sql(f"""
		SELECT venue,
		       SUM(TIME_TO_SEC(TIMEDIFF(end_time, start_time)) / 3600.0) AS hours
		FROM   `tabTimetable`
		WHERE  {" AND ".join(tt_where)}
		AND    venue IS NOT NULL AND venue != ''
		GROUP BY venue
	""", params, as_dict=True)

	tt_map = {r["venue"]: float(r["hours"] or 0) for r in tt_rows}

	# ── Emergency session hours ─────────────────────────────────────
	# Emergency sessions don't carry department/program directly. We
	# resolve those via the course → program → department chain.
	ems_where = [
		"DATE(start_time) >= %(start)s",
		"DATE(end_time) <= %(end)s",
		"status IN ('CONFIRMED', 'COMPLETED')",
	]
	if venue:
		ems_where.append("venue = %(venue)s")
	if lecturer:
		ems_where.append("lecturer = %(lecturer)s")

	if department or program:
		# Find which courses belong to the filter
		course_filters = {}
		if program:
			course_filters["program"] = program
		matching_courses = frappe.db.get_all("Course", filters=course_filters, pluck="name")

		if department:
			# program filter resolved to courses already, narrow further by dept
			dept_programs = frappe.db.get_all(
				"Program",
				filters={"department": department},
				pluck="name",
			)
			if dept_programs:
				dept_courses = frappe.db.get_all(
					"Course",
					filters={"program": ["in", dept_programs]},
					pluck="name",
				)
				if matching_courses:
					matching_courses = list(set(matching_courses) & set(dept_courses))
				else:
					matching_courses = dept_courses
			else:
				matching_courses = []

		if matching_courses:
			ems_where.append("course IN %(course_list)s")
			params["course_list"] = tuple(matching_courses)
		else:
			# No matching courses → no emergency hours for this filter
			ems_where.append("1 = 0")

	ems_rows = frappe.db.sql(f"""
		SELECT venue,
		       SUM(TIMESTAMPDIFF(SECOND, start_time, end_time) / 3600.0) AS hours
		FROM   `tabEmergency session`
		WHERE  {" AND ".join(ems_where)}
		AND    venue IS NOT NULL AND venue != ''
		GROUP BY venue
	""", params, as_dict=True)

	ems_map = {r["venue"]: float(r["hours"] or 0) for r in ems_rows}

	# ── Build per-venue result rows ────────────────────────────────
	venue_filter = [["name", "=", venue]] if venue else []
	venues = frappe.db.get_all(
		"Venue",
		filters=venue_filter,
		fields=["name", "venue_name", "location", "building_name", "capacity", "current_status"],
		order_by="venue_name asc",
	)

	result = []
	for v in venues:
		hours = tt_map.get(v["name"], 0) + ems_map.get(v["name"], 0)
		# When filtered, only include venues that actually have hours
		if (department or program or lecturer) and hours == 0:
			continue
		pct = round(min(hours / available_hours * 100, 100), 1)
		result.append({
			"venue":            v["name"],
			"venue_name":       v["venue_name"],
			"location":         v.get("location") or "",
			"building_name":    v.get("building_name") or "",
			"capacity":         v["capacity"],
			"hours_used":       round(hours, 1),
			"available_hours":  available_hours,
			"utilization_pct":  pct,
			"current_status":   v["current_status"] or "FREE",
		})

	result.sort(key=lambda x: x["utilization_pct"], reverse=True)
	return result


# ============================================================
# Peak hours — unchanged
# ============================================================

@frappe.whitelist(methods=["GET", "POST"])
def get_peak_hours(date_from: str = None, date_to: str = None):
	"""FR-44: Session counts by start hour of day for charting peak usage."""
	today = nowdate()
	start = getdate(date_from) if date_from else add_days(today, -30)
	end   = getdate(date_to)   if date_to   else today

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


# ============================================================
# Session summary — now with department + program filters
# ============================================================

@frappe.whitelist(methods=["GET", "POST"])
def get_session_summary(
	date_from: str = None,
	date_to: str = None,
	lecturer: str = None,
	venue: str = None,
	department: str = None,
	program: str = None,
):
	"""FR-44 + FR-47: Summary of sessions grouped by course for reporting."""
	today = nowdate()
	start = getdate(date_from) if date_from else add_days(today, -30)
	end   = getdate(date_to)   if date_to   else today

	filters = [
		["date", ">=", start],
		["date", "<=", end],
	]
	if lecturer:   filters.append(["lecturer",   "=", lecturer])
	if venue:      filters.append(["venue",      "=", venue])
	if department: filters.append(["department", "=", department])
	if program:    filters.append(["program",    "=", program])

	rows = frappe.db.get_list(
		"Timetable",
		filters=filters,
		fields=[
			"name", "course", "lecturer", "venue", "date",
			"start_time", "end_time", "duration_hours",
			"department", "program", "year_level",
		],
		order_by="date asc",
	)

	# Lookups for nicer display in the export
	course_map = {
		r["name"]: r["course_name"]
		for r in frappe.db.get_all("Course", fields=["name", "course_name"])
	}
	user_map = {
		r["name"]: r["full_name"]
		for r in frappe.db.get_all("User", filters={"enabled": 1}, fields=["name", "full_name"])
	}

	totals = {}
	for r in rows:
		key = r["course"]
		if key not in totals:
			totals[key] = {
				"course":       key,
				"course_name":  course_map.get(key) or key,
				"program":      r.get("program") or "",
				"department":   r.get("department") or "",
				"lecturers":    set(),
				"sessions":     0,
				"total_hours":  0.0,
			}
		if r.get("lecturer"):
			totals[key]["lecturers"].add(user_map.get(r["lecturer"]) or r["lecturer"])
		totals[key]["sessions"]    += 1
		totals[key]["total_hours"] += float(r.get("duration_hours") or 0)

	result = []
	for v in totals.values():
		v["lecturers"]   = ", ".join(sorted(v["lecturers"])) if v["lecturers"] else ""
		v["total_hours"] = round(v["total_hours"], 1)
		result.append(v)

	result.sort(key=lambda x: x["sessions"], reverse=True)
	return result


# ============================================================
# FR-48: Server-side exports — CSV, Excel, PDF
# ============================================================

EXPORT_FORMATS = {"csv", "excel", "pdf"}


def _build_filename(prefix: str, fmt: str) -> str:
	ts = datetime.now().strftime("%Y%m%d_%H%M%S")
	ext_map = {"csv": "csv", "excel": "xlsx", "pdf": "pdf"}
	return f"{prefix}_{ts}.{ext_map[fmt]}"


def _csv_response(headers: list, rows: list, filename: str):
	"""Build CSV in memory and return as Frappe file download."""
	import csv as csv_module
	buf = io.StringIO()
	writer = csv_module.writer(buf)
	writer.writerow(headers)
	for row in rows:
		writer.writerow(row)

	frappe.local.response.filename = filename
	frappe.local.response.filecontent = buf.getvalue().encode("utf-8-sig")  # BOM for Excel-compat
	frappe.local.response.type = "binary"


def _excel_response(headers: list, rows: list, filename: str, sheet_title: str = "Report"):
	"""Build a properly formatted .xlsx using openpyxl (shipped with Frappe)."""
	from openpyxl import Workbook
	from openpyxl.styles import Font, PatternFill, Alignment

	wb = Workbook()
	ws = wb.active
	ws.title = sheet_title[:31]  # Excel sheet name limit

	# Header row — bold + filled
	header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
	header_font = Font(bold=True, color="FFFFFF", size=11)
	header_align = Alignment(horizontal="center", vertical="center")

	for col_idx, label in enumerate(headers, start=1):
		cell = ws.cell(row=1, column=col_idx, value=label)
		cell.fill = header_fill
		cell.font = header_font
		cell.alignment = header_align

	# Data rows
	for row_idx, row in enumerate(rows, start=2):
		for col_idx, value in enumerate(row, start=1):
			ws.cell(row=row_idx, column=col_idx, value=value)

	# Auto-width columns based on header length + a comfortable buffer
	for col_idx, label in enumerate(headers, start=1):
		col_letter = ws.cell(row=1, column=col_idx).column_letter
		max_len = len(str(label))
		for row in rows[:50]:  # sample first 50 rows for width
			if col_idx - 1 < len(row):
				max_len = max(max_len, len(str(row[col_idx - 1] or "")))
		ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

	# Freeze the header row
	ws.freeze_panes = "A2"

	buf = io.BytesIO()
	wb.save(buf)

	frappe.local.response.filename = filename
	frappe.local.response.filecontent = buf.getvalue()
	frappe.local.response.type = "binary"


def _pdf_response(title: str, subtitle: str, headers: list, rows: list, filename: str):
	"""Render a styled HTML table and convert to PDF via wkhtmltopdf."""
	# Build the HTML table
	header_html = "".join(f"<th>{frappe.utils.escape_html(str(h))}</th>" for h in headers)
	rows_html_parts = []
	for row in rows:
		cells = "".join(
			f"<td>{frappe.utils.escape_html(str(v if v is not None else ''))}</td>"
			for v in row
		)
		rows_html_parts.append(f"<tr>{cells}</tr>")
	body_html = "".join(rows_html_parts) or '<tr><td colspan="100">No data</td></tr>'

	html = f"""
		<!DOCTYPE html>
		<html>
		<head>
			<meta charset="utf-8">
			<style>
				@page {{ margin: 1.5cm 1.2cm; }}
				body {{
					font-family: 'Helvetica Neue', Arial, sans-serif;
					color: #2c2c2a;
					font-size: 11px;
				}}
				.report-header {{
					border-bottom: 1px solid #d3d1c7;
					padding-bottom: 10px;
					margin-bottom: 14px;
				}}
				h1 {{
					font-size: 18px;
					margin: 0 0 4px;
					font-weight: 500;
					color: #2c2c2a;
				}}
				.subtitle {{
					font-size: 11px;
					color: #888780;
					margin: 0;
				}}
				table {{
					width: 100%;
					border-collapse: collapse;
					margin-top: 8px;
				}}
				th {{
					background: #1F4E79;
					color: #fff;
					padding: 8px 10px;
					text-align: left;
					font-weight: 500;
					font-size: 10px;
					letter-spacing: 0.04em;
					text-transform: uppercase;
				}}
				td {{
					padding: 6px 10px;
					border-bottom: 1px solid #ececec;
					font-size: 10.5px;
				}}
				tr:nth-child(even) td {{
					background: #fafafa;
				}}
				.footer {{
					margin-top: 16px;
					padding-top: 8px;
					border-top: 1px solid #d3d1c7;
					font-size: 9px;
					color: #888780;
					text-align: center;
				}}
			</style>
		</head>
		<body>
			<div class="report-header">
				<h1>{frappe.utils.escape_html(title)}</h1>
				<p class="subtitle">{frappe.utils.escape_html(subtitle)}</p>
			</div>
			<table>
				<thead><tr>{header_html}</tr></thead>
				<tbody>{body_html}</tbody>
			</table>
			<div class="footer">
				Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} ·
				Tanzania Venue Management System
			</div>
		</body>
		</html>
	"""

	pdf_content = get_pdf(html, {"page-size": "A4", "orientation": "Landscape"})
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = pdf_content
	frappe.local.response.type = "pdf"


@frappe.whitelist(methods=["GET", "POST"])
def export_venue_utilization(
	date_from: str,
	date_to: str,
	format: str = "csv",
	venue: str = None,
	department: str = None,
	program: str = None,
	lecturer: str = None,
):
	"""FR-48: Export venue utilization in CSV / Excel / PDF.

	Reuses get_venue_utilization for data so the export and on-screen
	table never diverge. The filter set passed here is echoed into
	the PDF subtitle for traceability.
	"""
	fmt = (format or "csv").lower()
	if fmt not in EXPORT_FORMATS:
		frappe.throw(_("Format must be one of: csv, excel, pdf"))

	data = get_venue_utilization(
		date_from=date_from, date_to=date_to,
		venue=venue, department=department, program=program, lecturer=lecturer,
	)

	headers = [
		"Venue Code", "Venue Name", "Building", "Location",
		"Capacity", "Hours Used", "Available Hours",
		"Utilization %", "Status",
	]
	rows = [
		[
			r["venue"], r["venue_name"], r.get("building_name", ""),
			r["location"], r["capacity"],
			r["hours_used"], r["available_hours"],
			r["utilization_pct"], r["current_status"],
		]
		for r in data
	]

	filename = _build_filename("venue_utilization", fmt)

	if fmt == "csv":
		return _csv_response(headers, rows, filename)
	if fmt == "excel":
		return _excel_response(headers, rows, filename, "Venue Utilization")

	subtitle_parts = [f"Period: {date_from} → {date_to}"]
	if department: subtitle_parts.append(f"Department: {department}")
	if program:    subtitle_parts.append(f"Program: {program}")
	if lecturer:   subtitle_parts.append(f"Lecturer: {lecturer}")
	if venue:      subtitle_parts.append(f"Venue: {venue}")

	return _pdf_response(
		title="Venue Utilization Report",
		subtitle=" · ".join(subtitle_parts),
		headers=headers,
		rows=rows,
		filename=filename,
	)


@frappe.whitelist(methods=["GET", "POST"])
def export_session_summary(
	date_from: str = None,
	date_to: str = None,
	format: str = "csv",
	lecturer: str = None,
	venue: str = None,
	department: str = None,
	program: str = None,
):
	"""FR-48: Export session-by-course summary in CSV / Excel / PDF."""
	fmt = (format or "csv").lower()
	if fmt not in EXPORT_FORMATS:
		frappe.throw(_("Format must be one of: csv, excel, pdf"))

	data = get_session_summary(
		date_from=date_from, date_to=date_to,
		lecturer=lecturer, venue=venue,
		department=department, program=program,
	)

	headers = [
		"Course Code", "Course Name", "Program", "Department",
		"Lecturer(s)", "Sessions", "Total Hours",
	]
	rows = [
		[
			r["course"], r["course_name"],
			r.get("program", ""), r.get("department", ""),
			r.get("lecturers", ""),
			r["sessions"], r["total_hours"],
		]
		for r in data
	]

	filename = _build_filename("session_summary", fmt)

	if fmt == "csv":
		return _csv_response(headers, rows, filename)
	if fmt == "excel":
		return _excel_response(headers, rows, filename, "Session Summary")

	today = nowdate()
	df_start = date_from or str(add_days(today, -30))
	df_end   = date_to   or str(today)
	subtitle_parts = [f"Period: {df_start} → {df_end}"]
	if department: subtitle_parts.append(f"Department: {department}")
	if program:    subtitle_parts.append(f"Program: {program}")
	if lecturer:   subtitle_parts.append(f"Lecturer: {lecturer}")
	if venue:      subtitle_parts.append(f"Venue: {venue}")

	return _pdf_response(
		title="Session Summary by Course",
		subtitle=" · ".join(subtitle_parts),
		headers=headers,
		rows=rows,
		filename=filename,
	)


@frappe.whitelist(methods=["GET", "POST"])
def export_peak_hours(
	date_from: str = None,
	date_to: str = None,
	format: str = "csv",
):
	"""FR-48: Export peak-hour distribution as CSV.

	Excel/PDF are also supported but contribute little over the chart —
	these formats are mostly useful for downstream tooling that wants
	the raw hour-by-hour numbers.
	"""
	fmt = (format or "csv").lower()
	if fmt not in EXPORT_FORMATS:
		frappe.throw(_("Format must be one of: csv, excel, pdf"))

	data = get_peak_hours(date_from=date_from, date_to=date_to)

	headers = ["Hour", "Time", "Session Count"]
	rows = [[r["hour"], r["label"], r["count"]] for r in data]

	filename = _build_filename("peak_hours", fmt)

	if fmt == "csv":
		return _csv_response(headers, rows, filename)
	if fmt == "excel":
		return _excel_response(headers, rows, filename, "Peak Hours")

	today = nowdate()
	df_start = date_from or str(add_days(today, -30))
	df_end   = date_to   or str(today)
	return _pdf_response(
		title="Peak Usage Hours",
		subtitle=f"Period: {df_start} → {df_end}",
		headers=headers,
		rows=rows,
		filename=filename,
	)