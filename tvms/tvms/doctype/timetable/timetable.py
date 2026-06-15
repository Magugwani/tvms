# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import csv
import io
import uuid
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_time, getdate, now


# Day name → offset from Monday (0-based)
# Covers full names, abbreviations, and FET numbered-day formats
_DAY_OFFSETS = {
	"monday": 0,    "mon": 0, "mo": 0,
	"tuesday": 1,   "tue": 1, "tu": 1,
	"wednesday": 2, "wed": 2, "we": 2,
	"thursday": 3,  "thu": 3, "th": 3,
	"friday": 4,    "fri": 4, "fr": 4,
	"saturday": 5,  "sat": 5,
	"sunday": 6,    "sun": 6,
	# Numbered days that FET sometimes emits (1-indexed and 0-indexed)
	"day 1": 0, "day 2": 1, "day 3": 2, "day 4": 3, "day 5": 4,
	"day1":  0, "day2":  1, "day3":  2, "day4":  3, "day5":  4,
	"1": 0, "2": 1, "3": 2, "4": 3, "5": 4,
}

# All FET column name variants → normalised key
_COL_ALIASES = {
	# Activity ID
	"activity id": "activity_id", "activity_id": "activity_id", "id": "activity_id",
	# Subject / Course
	"subject": "subject", "subject name": "subject", "course": "subject",
	# Teacher
	"teacher": "teacher", "teachers": "teacher", "teacher(s)": "teacher",
	# Students
	"students": "students", "students set(s)": "students",
	"students sets": "students", "students_sets": "students",
	# Duration (in hours/slots)
	"duration": "duration",
	# Day
	"day": "day",
	# Hour / start time
	"hour": "hour", "start hour": "hour", "start_hour": "hour",
	"start time": "hour", "start_time": "hour",
	# Room / Venue
	"room": "room", "room name": "room", "rooms": "room",
}


class Timetable(Document):

	def validate(self):
		self._validate_time_range()
		self._compute_duration()
		self._sync_day_of_week()
		self._check_venue_conflict()
		self._check_lecturer_conflict()

	# ------------------------------------------------------------------

	def _validate_time_range(self):
		if self.start_time and self.end_time:
			if get_time(self.start_time) >= get_time(self.end_time):
				frappe.throw(_("Start time must be before end time"))

	def _compute_duration(self):
		if self.start_time and self.end_time:
			start = datetime.strptime(str(self.start_time), "%H:%M:%S")
			end = datetime.strptime(str(self.end_time), "%H:%M:%S")
			delta = (end - start).total_seconds() / 3600
			self.duration_hours = round(delta, 1)

	def _sync_day_of_week(self):
		if self.date:
			self.day_of_week = getdate(self.date).strftime("%A")  # "Monday" … "Sunday"

	def _check_venue_conflict(self):
		"""Prevent double-booking a venue against other Timetable rows"""
		if self.flags.get("fet_import"):
			return  # FET guarantees no intra-timetable conflicts; skip for bulk import
		if not self.venue or not self.date or not self.start_time or not self.end_time:
			return

		start_str = str(self.start_time)[:8]
		end_str = str(self.end_time)[:8]

		conflict = frappe.db.get_all(
			"Timetable",
			filters=[
				["venue", "=", self.venue],
				["date", "=", self.date],
				["status", "!=", "COMPLETED"],
				["name", "!=", self.name or ""],
				["start_time", "<", end_str],
				["end_time", ">", start_str],
			],
			fields=["name", "course", "start_time", "end_time"],
			limit=1,
		)
		if conflict:
			c = conflict[0]
			frappe.throw(_(
				"Venue <strong>{0}</strong> is already booked for <strong>{1}</strong> "
				"({2} – {3}) on {4}."
			).format(self.venue, c["course"], str(c["start_time"])[:5],
					 str(c["end_time"])[:5], self.date))

	def _check_lecturer_conflict(self):
		"""Prevent double-booking a lecturer across Timetable rows"""
		if self.flags.get("fet_import"):
			return  # FET guarantees no intra-timetable conflicts; skip for bulk import
		if not self.lecturer or not self.date or not self.start_time or not self.end_time:
			return

		start_str = str(self.start_time)[:8]
		end_str = str(self.end_time)[:8]

		conflict = frappe.db.get_all(
			"Timetable",
			filters=[
				["lecturer", "=", self.lecturer],
				["date", "=", self.date],
				["status", "!=", "COMPLETED"],
				["name", "!=", self.name or ""],
				["start_time", "<", end_str],
				["end_time", ">", start_str],
			],
			fields=["name", "course", "venue", "start_time", "end_time"],
			limit=1,
		)
		if conflict:
			c = conflict[0]
			frappe.throw(_(
				"Lecturer <strong>{0}</strong> already has a session "
				"<strong>{1}</strong> in {2} ({3} – {4}) on {5}."
			).format(self.lecturer, c["course"], c["venue"] or "—",
					 str(c["start_time"])[:5], str(c["end_time"])[:5], self.date))


# ==================================================================
# FET CSV import engine
# ==================================================================

@frappe.whitelist(methods=["POST"])
def import_from_fet_csv(
	file_content: str,
	semester_start: str,
	semester_end: str,
	academic_year: str = None,
	semester: str = None,
	source_file: str = None,
	overwrite: bool = False,
):
	"""Import a FET activities CSV into Timetable entries for a full semester.

	Two-phase approach:
	  Phase 1 — resolve each CSV row once (course lookup, soft lecturer/venue match)
	  Phase 2 — expand each resolved row across every week in the semester range

	Args:
	    file_content:   Raw CSV text (FET exports; semicolon or comma separated)
	    semester_start: Monday of the first week — YYYY-MM-DD
	    semester_end:   Last day of the semester (inclusive) — YYYY-MM-DD
	    academic_year:  e.g. "2026/2027"
	    semester:       e.g. "Semester 1"
	    source_file:    Original filename (for audit)
	    overwrite:      Delete all Timetable rows in the date range before import
	"""
	frappe.only_for(["Department Admin", "System Manager", "Administrator"])

	start_date = getdate(semester_start)
	end_date   = getdate(semester_end)
	if start_date > end_date:
		frappe.throw(_("Semester start must be before semester end"))
	if start_date.weekday() != 0:
		frappe.throw(_("Semester start must be a Monday"))

	# All Monday dates within the semester range
	week_starts = []
	current = start_date
	while current <= end_date:
		week_starts.append(current)
		current = add_days(current, 7)

	batch_id       = "IMP-" + str(uuid.uuid4())[:8].upper()
	imported_at_ts = now()

	rows = _parse_fet_csv(file_content)
	if not rows:
		frappe.throw(_("No data rows found in the uploaded file"))

	if overwrite:
		last_day  = add_days(week_starts[-1], 6)
		old_names = frappe.db.get_all(
			"Timetable",
			filters=[["date", ">=", start_date], ["date", "<=", last_day]],
			pluck="name",
		)
		for name in old_names:
			frappe.delete_doc("Timetable", name, ignore_permissions=True)

	imported, skipped = 0, 0
	warning_rows, error_rows = [], []

	# ------------------------------------------------------------------
	# Phase 1 — resolve each CSV row once (no DB writes)
	# ------------------------------------------------------------------
	resolved_rows = []
	for row_num, row in enumerate(rows, start=2):
		try:
			resolved = _resolve_row(row)
			resolved_rows.append((row_num, resolved))
			if resolved["row_warnings"]:
				warning_rows.append({"row": row_num, "warnings": resolved["row_warnings"]})
		except frappe.ValidationError as exc:
			error_rows.append({"row": row_num, "error": str(exc)})
		except Exception as exc:
			error_rows.append({"row": row_num, "error": str(exc)})
			frappe.logger().error(
				f"Timetable import row {row_num} resolve failed: {exc}", exc_info=True
			)

	# ------------------------------------------------------------------
	# Phase 2 — expand each resolved row across every week
	# ------------------------------------------------------------------
	for row_num, resolved in resolved_rows:
		for week_date in week_starts:
			try:
				name = _create_entry(
					resolved, week_date, batch_id, imported_at_ts,
					academic_year, semester, source_file, end_date,
				)
				if name:
					imported += 1
				else:
					skipped += 1
			except Exception as exc:
				error_rows.append({"row": row_num, "error": str(exc)})
				frappe.logger().error(
					f"Timetable import row {row_num} week {week_date} failed: {exc}",
					exc_info=True,
				)

	frappe.db.commit()

	return {
		"batch_id":         batch_id,
		"semester_start":   str(start_date),
		"semester_end":     str(end_date),
		"num_weeks":        len(week_starts),
		"total_activities": len(resolved_rows) * len(week_starts),
		"imported":         imported,
		"skipped":          skipped,
		"warnings":         len(warning_rows),
		"errors":           len(error_rows),
		"warning_details":  warning_rows[:50],
		"error_details":    error_rows[:50],
	}


def _resolve_row(row):
	"""Parse and validate one CSV row. Runs once per row across the whole import.

	Returns a dict of resolved field values + day_offset (0=Mon..6=Sun).
	Raises ValidationError for hard failures (missing course, unknown day).
	"""
	activity_id = row.get("activity_id", "").strip()
	subject     = row.get("subject", "").strip()
	teacher     = row.get("teacher", "").strip()
	students    = row.get("students", "").strip()
	duration    = row.get("duration", "1").strip()
	day         = row.get("day", "").strip()
	hour        = row.get("hour", "").strip()
	room        = row.get("room", "").strip()

	if not subject:
		frappe.throw(_("Subject/Course is required"))
	if not day:
		frappe.throw(_("Day is required"))
	if not hour:
		frappe.throw(_("Hour/Start time is required"))

	day_offset = _DAY_OFFSETS.get(day.strip().lower())
	if day_offset is None:
		frappe.throw(_("Unrecognised day name: '{0}'").format(day))

	try:
		start_time = _parse_time(hour)
	except ValueError:
		frappe.throw(_("Invalid start time: '{0}'").format(hour))

	try:
		duration_val = float(duration) if duration else 1.0
	except ValueError:
		frappe.throw(_("Invalid duration: '{0}'").format(duration))
	end_time = _offset_time(start_time, duration_val)

	course = _resolve_course(subject)

	row_warnings = []
	lecturer = _resolve_soft("lecturer", teacher, row_warnings)
	venue    = _resolve_soft("venue",    room,    row_warnings)

	return {
		"activity_id":    activity_id,
		"course":         course,
		"lecturer":       lecturer,
		"venue":          venue,
		"day_offset":     day_offset,
		"start_time":     start_time,
		"end_time":       end_time,
		"duration_hours": duration_val,
		"student_groups": students or None,
		"row_warnings":   row_warnings,
	}


def _create_entry(resolved, week_start_date, batch_id, imported_at_ts,
					academic_year, semester, source_file, end_date):
	"""Insert one Timetable doc for a resolved row on a specific week.

	Returns doc.name if created, None if the entry already exists (duplicate)
	or if the generated date falls outside the semester range.
	"""
	actual_date = add_days(week_start_date, resolved["day_offset"])
	if actual_date > end_date:
		return None

	if resolved["activity_id"] and frappe.db.exists("Timetable", {
		"fet_activity_id": resolved["activity_id"],
		"date": actual_date,
	}):
		return None

	doc = frappe.get_doc({
		"doctype":         "Timetable",
		"course":          resolved["course"],
		"lecturer":        resolved["lecturer"],
		"venue":           resolved["venue"],
		"date":            actual_date,
		"start_time":      resolved["start_time"],
		"end_time":        resolved["end_time"],
		"student_groups":  resolved["student_groups"],
		"academic_year":   academic_year or None,
		"semester":        semester or None,
		"fet_activity_id": resolved["activity_id"] or None,
		"import_batch":    batch_id,
		"source_file":     source_file or None,
		"imported_at":     imported_at_ts,
		"status":          "SCHEDULED",
	})
	doc.flags.fet_import = True
	doc.insert(ignore_permissions=True)
	return doc.name


# ==================================================================
# CSV parsing helpers
# ==================================================================

def _parse_fet_csv(content):
	"""Parse FET activities CSV.

	FET uses semicolons in European locales, commas in English.
	Normalises all header names to canonical keys via _COL_ALIASES.
	Returns list of dicts with normalised keys.
	"""
	content = content.strip()
	if not content:
		return []

	# Detect delimiter from the header line
	first_line = content.split("\n")[0]
	delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","

	reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
	rows = []
	for raw_row in reader:
		normalised = {}
		for raw_key, value in raw_row.items():
			alias = _COL_ALIASES.get((raw_key or "").strip().lower())
			if alias:
				normalised[alias] = (value or "").strip()
		rows.append(normalised)
	return rows


def _day_to_date(day_name, week_start_date):
	"""Convert FET day name (e.g. 'Monday') to actual date using week_start_date."""
	offset = _DAY_OFFSETS.get(day_name.strip().lower())
	if offset is None:
		return None
	return add_days(week_start_date, offset)


def _parse_time(time_str):
	"""Normalise FET hour values to HH:MM:SS.

	Accepts: "08:00", "8:00", "08:00:00", "8" (slot → on-the-hour).
	"""
	time_str = str(time_str).strip()
	if ":" in time_str:
		parts = time_str.split(":")
		h = int(parts[0])
		m = int(parts[1]) if len(parts) > 1 else 0
	else:
		h = int(time_str)
		m = 0
	return f"{h:02d}:{m:02d}:00"


def _offset_time(time_str, hours):
	"""Add `hours` (float) to a HH:MM:SS string and return a new HH:MM:SS string."""
	t = datetime.strptime(time_str, "%H:%M:%S")
	t += timedelta(hours=hours)
	return t.strftime("%H:%M:%S")

# ---------------------------------------------------------------
# Program/Year segmented timetable (one grid per "Program - Year")
# ---------------------------------------------------------------

def _program_year_label(program, year_level):
	"""Build a display label like 'Bachelor's Degree in Information - First Year'."""
	program = (program or "").strip()
	year_level = (year_level or "").strip()
	if program and year_level:
		return f"{program} - {year_level}"
	return program or year_level or "Unassigned"


@frappe.whitelist(methods=["GET", "POST"])
def get_program_timetable_groups(
	week_start: str,
	include_weekends: int = 0,
	program: str = None,
	year_level: str = None,
):
	"""Return the week's Timetable entries grouped by Program + Year Level.

	Each group becomes one weekly grid section in the admin UI — e.g.
	"Bachelor's Degree in Information - First Year" with its own
	Monday-Saturday table, mirroring the layout of the FET export.

	Args:
	    week_start       -- Monday of the week (YYYY-MM-DD)
	    include_weekends -- 1 to include Saturday/Sunday columns
	    program          -- optional filter to a single program
	    year_level       -- optional filter to a single year level

	Returns:
	    {
	      "week_start": "...",
	      "groups": [
	        {
	          "key": "Bachelor's Degree in Information||First Year",
	          "label": "Bachelor's Degree in Information - First Year",
	          "program": "Bachelor's Degree in Information",
	          "year_level": "First Year",
	          "sessions": [ ...same shape as get_week_timetable... ]
	        },
	        ...
	      ]
	    }
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	sessions = get_week_timetable(week_start, include_weekends=include_weekends)

	groups = {}
	for s in sessions:
		s_program = s.get("program") or ""
		s_year = s.get("year_level") or ""

		if program and s_program != program:
			continue
		if year_level and s_year != year_level:
			continue

		key = f"{s_program}||{s_year}"
		if key not in groups:
			groups[key] = {
				"key": key,
				"label": _program_year_label(s_program, s_year),
				"program": s_program,
				"year_level": s_year,
				"sessions": [],
			}
		groups[key]["sessions"].append(s)

	# Sort groups: by program name, then by a sensible year ordering
	year_order = {
		"first year": 1, "1st year": 1, "year 1": 1, "year i": 1,
		"second year": 2, "2nd year": 2, "year 2": 2, "year ii": 2,
		"third year": 3, "3rd year": 3, "year 3": 3, "year iii": 3,
		"fourth year": 4, "4th year": 4, "year 4": 4, "year iv": 4,
		"fifth year": 5, "5th year": 5, "year 5": 5, "year v": 5,
	}

	def _sort_key(g):
		return (
			g["program"].lower(),
			year_order.get(g["year_level"].lower(), 99),
			g["year_level"].lower(),
		)

	sorted_groups = sorted(groups.values(), key=_sort_key)

	return {"week_start": week_start, "groups": sorted_groups}


@frappe.whitelist(methods=["GET", "POST"])
def get_program_year_options():
	"""Return distinct (program, year_level) combinations for filter dropdowns
	and for pre-filling the "Add Class" dialog with a specific segment.
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	rows = frappe.db.get_all(
		"Timetable",
		fields=["program", "year_level"],
		distinct=True,
	)

	programs = sorted({r["program"] for r in rows if r.get("program")})
	year_levels = sorted({r["year_level"] for r in rows if r.get("year_level")})

	groups = sorted(
		{(r.get("program") or "", r.get("year_level") or "") for r in rows
		 if r.get("program") or r.get("year_level")}
	)

	return {
		"programs": programs,
		"year_levels": year_levels,
		"groups": [
			{"program": p, "year_level": y, "label": _program_year_label(p, y)}
			for p, y in groups
		],
	}


# ---------------------------------------------------------------
# Program-wise grouped timetable (for the segmented admin grid UI)
# ---------------------------------------------------------------

_YEAR_LEVEL_LABELS = {
	"1": "First Year", "i": "First Year", "year 1": "First Year", "first year": "First Year",
	"2": "Second Year", "ii": "Second Year", "year 2": "Second Year", "second year": "Second Year",
	"3": "Third Year", "iii": "Third Year", "year 3": "Third Year", "third year": "Third Year",
	"4": "Fourth Year", "iv": "Fourth Year", "year 4": "Fourth Year", "fourth year": "Fourth Year",
	"5": "Fifth Year", "v": "Fifth Year", "year 5": "Fifth Year", "fifth year": "Fifth Year",
}


def _year_level_label(value):
	"""Normalise year_level into a display label e.g. '1' -> 'First Year'."""
	if not value:
		return ""
	key = str(value).strip().lower()
	return _YEAR_LEVEL_LABELS.get(key, str(value).strip())


@frappe.whitelist(methods=["GET", "POST"])
def get_week_timetable_grouped(
	week_start: str,
	lecturer: str = None,
	venue: str = None,
	course: str = None,
	program: str = None,
	year_level: str = None,
	semester: str = None,
	academic_year: str = None,
	include_weekends: int = 0,
):
	"""Return the week's Timetable entries grouped by Program + Year Level.

	Used by the segmented admin grid: each group renders as its own
	mini-timetable (e.g. "Information Technology — First Year"), matching
	the layout of program-wise paper/Excel timetables.

	Returns:
	    {
	      "groups": [
	          {
	              "program": "Information Technology",
	              "year_level": "1",
	              "year_level_label": "First Year",
	              "label": "Information Technology — First Year",
	              "sessions": [ ...same shape as get_week_timetable... ]
	          },
	          ...
	      ],
	      "week_start": "...",
	      "week_end": "...",
	  }

	Groups are sorted alphabetically by program, then by year_level.
	Sessions with no program/year_level are grouped under "Unassigned".
	"""
	sessions = get_week_timetable(
		week_start=week_start,
		lecturer=lecturer,
		venue=venue,
		course=course,
		program=program,
		semester=semester,
		academic_year=academic_year,
		include_weekends=include_weekends,
	)

	if year_level:
		target_label = _year_level_label(year_level)
		sessions = [
			s for s in sessions
			if _year_level_label(s.get("year_level")) == target_label
		]

	groups_map = {}
	for s in sessions:
		prog = (s.get("program") or "").strip() or "Unassigned"
		yl_raw = s.get("year_level") or ""
		yl_label = _year_level_label(yl_raw) or "Unassigned"
		key = (prog, yl_label)
		if key not in groups_map:
			groups_map[key] = {
				"program": prog,
				"year_level": yl_raw,
				"year_level_label": yl_label,
				"label": f"{prog} — {yl_label}" if yl_label != "Unassigned" else prog,
				"sessions": [],
			}
		groups_map[key]["sessions"].append(s)

	# Sort: named programs first (alphabetical), "Unassigned" last
	def sort_key(group):
		is_unassigned = group["program"] == "Unassigned"
		return (is_unassigned, group["program"], group["year_level_label"])

	groups = sorted(groups_map.values(), key=sort_key)

	week_days = 7 if int(include_weekends or 0) else 5
	week_end = str(add_days(getdate(week_start), week_days - 1))

	return {
		"groups": groups,
		"week_start": week_start,
		"week_end": week_end,
		"total_sessions": len(sessions),
		"total_groups": len(groups),
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_program_year_options():
	"""Return distinct (program, year_level) combinations across all Timetable entries.

	Used to populate the Program / Year Level filters and the "Add Class" dialog
	defaults, and to let the admin jump straight to a specific program's section.
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	rows = frappe.db.get_all(
		"Timetable",
		filters=[["program", "is", "set"]],
		fields=["program", "year_level"],
		distinct=True,
	)

	combos = {}
	for r in rows:
		prog = (r.get("program") or "").strip()
		if not prog:
			continue
		yl_raw = r.get("year_level") or ""
		yl_label = _year_level_label(yl_raw) or "Unassigned"
		combos[(prog, yl_label)] = yl_raw

	result = []
	for (prog, yl_label), yl_raw in combos.items():
		result.append({
			"program": prog,
			"year_level": yl_raw,
			"year_level_label": yl_label,
			"label": f"{prog} — {yl_label}" if yl_label != "Unassigned" else prog,
		})

	result.sort(key=lambda x: (x["program"], x["year_level_label"]))
	return result

# ==================================================================
# Link resolution helpers
# ==================================================================

def _resolve_course(subject):
	"""Find Course — required field, throws if not matched.

	Match order: exact course_name → case-insensitive course_name → exact docname.
	"""
	# 1. Exact course_name match
	name = frappe.db.get_value("Course", {"course_name": subject}, "name")
	if name:
		return name

	# 2. Case-insensitive course_name match
	name = frappe.db.sql_list(
		"SELECT name FROM `tabCourse` WHERE LOWER(course_name) = %s LIMIT 1",
		[subject.lower()]
	)
	if name:
		return name[0]

	# 3. Direct docname match (course code used as name)
	if frappe.db.exists("Course", subject):
		return subject

	frappe.throw(_("Course not found for subject '{0}'. "
				   "Ensure the course_name in Frappe matches the FET subject exactly.").format(subject))


def _resolve_soft(field_type, raw_value, warnings):
	"""Resolve lecturer (User) or venue (Venue) without throwing.

	On mismatch: appends a human-readable warning and returns None so the
	row is still imported with the field left blank.
	"""
	if not raw_value:
		return None

	if field_type == "lecturer":
		# Exact full_name → case-insensitive full_name → email
		user = frappe.db.get_value("User", {"full_name": raw_value, "enabled": 1}, "name")
		if not user:
			user = frappe.db.sql_list(
				"SELECT name FROM `tabUser` WHERE LOWER(full_name) = %s AND enabled = 1 LIMIT 1",
				[raw_value.lower()]
			)
			user = user[0] if user else None
		if not user:
			user = frappe.db.get_value("User", {"email": raw_value, "enabled": 1}, "name")
		if not user:
			warnings.append(
				f"Lecturer '{raw_value}' not found in Frappe Users — field left blank."
			)
		return user

	if field_type == "venue":
		# Exact venue_code (docname) → exact venue_name → case-insensitive venue_name
		if frappe.db.exists("Venue", raw_value):
			return raw_value
		name = frappe.db.get_value("Venue", {"venue_name": raw_value}, "name")
		if not name:
			name_list = frappe.db.sql_list(
				"SELECT name FROM `tabVenue` WHERE LOWER(venue_name) = %s LIMIT 1",
				[raw_value.lower()]
			)
			name = name_list[0] if name_list else None
		if not name:
			warnings.append(
				f"Venue '{raw_value}' not found — field left blank."
			)
		return name

	return None


# ==================================================================
# Existing read APIs
# ==================================================================

@frappe.whitelist(methods=["GET", "POST"])
def get_week_timetable(
	week_start: str,
	lecturer: str = None,
	venue: str = None,
	course: str = None,
	program: str = None,
	semester: str = None,
	academic_year: str = None,
	include_weekends: int = 0,
):
	"""Return Timetable entries for the week starting on week_start.

	Imported FET rows are stored as regular Timetable documents. This API is
	the read model for the static timetable grid used by Students, CRs,
	Lecturers, and admins, and also acts as the general timetable reference
	for venue availability workflows.
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	week_days = 7 if int(include_weekends or 0) else 5
	week_end = str(add_days(getdate(week_start), week_days - 1))

	filters = [
		["date", ">=", week_start],
		["date", "<=", week_end],
	]
	if lecturer:
		filters.append(["lecturer", "=", lecturer])
	if venue:
		filters.append(["venue", "=", venue])
	if course:
		filters.append(["course", "=", course])
	if semester:
		filters.append(["semester", "=", semester])
	if academic_year:
		filters.append(["academic_year", "=", academic_year])

	if program:
		courses_in_program = frappe.db.get_all(
			"Course", filters={"program": program}, pluck="name"
		)
		if not courses_in_program:
			return []
		filters.append(["course", "in", courses_in_program])

	sessions = frappe.db.get_list(
		"Timetable",
		filters=filters,
		fields=["name", "course", "lecturer", "venue", "date", "day_of_week",
				"start_time", "end_time", "duration_hours", "status",
				"academic_year", "semester", "student_groups", "import_batch"],
		order_by="date asc, start_time asc",
	)

	if not sessions:
		return sessions

	# Enrich with human-readable display names (two small lookups, not N queries)
	course_map = {
		r["name"]: r["course_name"]
		for r in frappe.db.get_all("Course", fields=["name", "course_name"])
	}
	user_map = {
		r["name"]: r["full_name"]
		for r in frappe.db.get_all("User", filters={"enabled": 1}, fields=["name", "full_name"])
	}
	venue_map = {
		r["name"]: r
		for r in frappe.db.get_all("Venue", fields=["name", "venue_name", "current_status", "location"])
	}

	for s in sessions:
		s["course_name"]   = course_map.get(s["course"]) or s["course"]
		s["lecturer_name"] = user_map.get(s["lecturer"]) if s.get("lecturer") else None
		venue_doc = venue_map.get(s["venue"]) if s.get("venue") else None
		s["venue_name"] = venue_doc.get("venue_name") if venue_doc else s.get("venue")
		s["venue_status"] = venue_doc.get("current_status") if venue_doc else None
		s["venue_location"] = venue_doc.get("location") if venue_doc else None

	return sessions


@frappe.whitelist(methods=["GET", "POST"])
def get_filter_options():
	"""Return distinct lecturers, venues, courses, and programs for filter dropdowns."""
	frappe.has_permission("Timetable", "read", throw=True)

	def distinct_values(fieldname):
		return [
			value for value in frappe.db.get_all("Timetable", pluck=fieldname, distinct=True)
			if value
		]

	lecturers = distinct_values("lecturer")
	venues = distinct_values("venue")
	courses = distinct_values("course")

	lecturer_options = frappe.db.get_all(
			"User",
			filters={"name": ["in", lecturers]},
			fields=["name", "full_name"],
		) if lecturers else []
	venue_options = frappe.db.get_all(
			"Venue",
			filters={"name": ["in", venues]},
			fields=["name", "venue_name"],
		) if venues else []
	course_options = frappe.db.get_all(
			"Course",
			filters={"name": ["in", courses]},
			fields=["name", "course_name", "program"],
		) if courses else []

	return {
		"lecturers": lecturer_options,
		"venues": venue_options,
		"courses": course_options,
		"programs": get_programs(),
		"semesters": frappe.db.sql_list(
			"SELECT DISTINCT semester FROM `tabTimetable` WHERE semester IS NOT NULL AND semester != '' ORDER BY semester"
		),
		"academic_years": frappe.db.sql_list(
			"SELECT DISTINCT academic_year FROM `tabTimetable` WHERE academic_year IS NOT NULL AND academic_year != '' ORDER BY academic_year"
		),
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_programs():
	"""Return all distinct programs from the Course table."""
	return frappe.db.sql_list(
		"SELECT DISTINCT program FROM `tabCourse` "
		"WHERE program IS NOT NULL AND program != '' ORDER BY program"
	)


@frappe.whitelist(methods=["GET", "POST"])
def get_current_user_context():
	"""Return the current user's role context for Desk/page integrations."""
	user = frappe.session.user
	roles = frappe.get_roles(user)

	if "System Manager" in roles or "Administrator" in roles or "Department Admin" in roles:
		primary_role = "admin"
	elif "Lecturer" in roles:
		primary_role = "lecturer"
	elif "Class Representative (CR)" in roles:
		primary_role = "cr"
	elif "Student" in roles:
		primary_role = "student"
	else:
		primary_role = "viewer"

	full_name = frappe.db.get_value("User", user, "full_name") or user

	return {
		"user": user,
		"full_name": full_name,
		"primary_role": primary_role,
		"is_admin": primary_role == "admin",
		"is_lecturer": primary_role == "lecturer",
		"can_import": primary_role == "admin",
	}
