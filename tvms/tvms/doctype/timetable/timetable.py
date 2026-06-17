# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt


from datetime import datetime

import frappe
import json
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_time, getdate

_TVMS_LOGGED_FIELDS = [
	"course", "venue", "lecturer", "date", "start_time", "end_time",
	"day_of_week", "duration_hours", "status", "publish_status",
	"academic_year", "semester", "department", "program", "year_level",
	"students_groups",
]
 
 
def _serialise(value):
	"""Convert dates / times to ISO strings so the log JSON is portable."""
	if value is None:
		return None
	try:
		# date, datetime, time all have isoformat
		return value.isoformat()
	except AttributeError:
		return str(value)
 
 
def _normalise(value):
	"""Comparable form — treat None and '' as equal so empty edits don't log."""
	if value is None:
		return ""
	try:
		return value.isoformat()
	except AttributeError:
		return str(value).strip()
 
 
def _summarise(action, changes, doc_name):
	"""Build the one-line summary text stored on the log row."""
	if action == "CREATED":
		return _("Timetable entry {0} created").format(doc_name)
	if action == "DELETED":
		return _("Timetable entry {0} deleted").format(doc_name)
	if action == "PUBLISHED":
		return _("Timetable entry {0} published").format(doc_name)
	if action == "UNPUBLISHED":
		return _("Timetable entry {0} moved back to draft").format(doc_name)
	# UPDATED — list up to 3 field names in the summary
	if changes:
		fields = [c["fieldname"] for c in changes][:3]
		rest = len(changes) - len(fields)
		text = ", ".join(fields)
		if rest > 0:
			text += _(" and {0} more").format(rest)
		return _("Updated {0} on {1}").format(text, doc_name)
	return _("Updated {0}").format(doc_name)
 
 
def log_change(
	timetable_entry,
	action,
	changes=None,
	snapshot_before=None,
	snapshot_after=None,
	reason=None,
):
	"""Append one row to Timetable Change Log.
 
	Called automatically by Timetable.on_update / on_trash for the standard
	CREATED / UPDATED / DELETED / PUBLISHED / UNPUBLISHED actions. Can also
	be called explicitly from bulk operations (publish_timetable etc.) when
	you want a single log row instead of one per entry.
 
	Args:
	    timetable_entry -- the Timetable docname (e.g. "TIMETABLE-0001")
	    action          -- one of CREATED, UPDATED, PUBLISHED, UNPUBLISHED, DELETED
	    changes         -- list of {fieldname, old, new} or None
	    snapshot_before -- dict of pre-change field values (or None for CREATED)
	    snapshot_after  -- dict of post-change field values (or None for DELETED)
	    reason          -- optional free-text explanation
	"""
	try:
		summary = _summarise(action, changes, timetable_entry)
 
		doc = frappe.get_doc({
			"doctype":         "Timetable Change Log",
			"timetable_entry": timetable_entry,
			"action":          action,
			"timestamp":       frappe.utils.now_datetime(),
			"changed_by":      frappe.session.user if frappe.session else "System",
			"summary":         summary,
			"reason":          reason or None,
			"changes":         json.dumps(changes, default=str) if changes else None,
			"snapshot_before": json.dumps(snapshot_before, default=str) if snapshot_before else None,
			"snapshot_after":  json.dumps(snapshot_after, default=str)  if snapshot_after  else None,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
	except Exception:
		# Logging must never block the calling operation
		frappe.logger().warning(
			f"[TVMS] log_change failed for {timetable_entry} action={action}",
			exc_info=True,
		)

ADMIN_ROLES = {"System Manager", "Administrator", "Department Admin"}


def _ensure_timetable_admin():
	"""Raise PermissionError unless caller is an admin role."""
	if not ADMIN_ROLES.intersection(frappe.get_roles()):
		frappe.throw(
			_("Only Admins can create, edit, or delete timetable entries"),
			frappe.PermissionError,
		)


# ============================================================
# Timetable doctype
# ============================================================

class Timetable(Document):

	def validate(self):
		self._validate_time_range()
		self._compute_duration()
		self._sync_day_of_week()
		self._check_venue_conflict()
		self._check_lecturer_conflict()

	# ----- field-level validation ----------------------------------

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
			self.day_of_week = getdate(self.date).strftime("%A")

	# ----- conflict detection --------------------------------------

	def _check_venue_conflict(self):
		"""Prevent double-booking a venue against other Timetable rows."""
		if not self.venue or not self.date or not self.start_time or not self.end_time:
			return

		start_str = str(self.start_time)[:8]
		end_str   = str(self.end_time)[:8]

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
			).format(
				self.venue, c["course"],
				str(c["start_time"])[:5], str(c["end_time"])[:5], self.date,
			))

	def _check_lecturer_conflict(self):
		"""Prevent double-booking a lecturer across Timetable rows."""
		if not self.lecturer or not self.date or not self.start_time or not self.end_time:
			return

		start_str = str(self.start_time)[:8]
		end_str   = str(self.end_time)[:8]

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
			).format(
				self.lecturer, c["course"], c["venue"] or "—",
				str(c["start_time"])[:5], str(c["end_time"])[:5], self.date,
			))

	def before_save(self):
		"""Snapshot the previous database state so on_update can diff against it.
		
		Runs ONCE per save, BEFORE validate(). We stash the snapshot on
		self.flags so it survives across the validate → save → on_update
		sequence inside the same request.
		"""
		if self.is_new():
			self.flags._tvms_old_state = None
			return
		try:
			# Read the row directly from DB before the new values are written.
			# This is more reliable than self.get_doc_before_save() which
			# can return None in some Frappe code paths.
			row = frappe.db.get_value(
				"Timetable",
				self.name,
				_TVMS_LOGGED_FIELDS,
				as_dict=True,
			)
			self.flags._tvms_old_state = row or None
		except Exception:
			self.flags._tvms_old_state = None
 
	def on_update(self):
		"""Write a CREATED or UPDATED row to Timetable Change Log."""
		try:
			old_state = self.flags.get("_tvms_old_state")
			new_state = {f: self.get(f) for f in _TVMS_LOGGED_FIELDS}
 
			if old_state is None:
				# First save — CREATED
				log_change(
					timetable_entry=self.name,
					action="CREATED",
					changes=None,
					snapshot_before=None,
					snapshot_after=new_state,
				)
				return
 
			# Subsequent save — diff field by field
			changes = []
			for fieldname in _TVMS_LOGGED_FIELDS:
				old_val = old_state.get(fieldname)
				new_val = new_state.get(fieldname)
				if _normalise(old_val) != _normalise(new_val):
					changes.append({
						"fieldname": fieldname,
						"old": _serialise(old_val),
						"new": _serialise(new_val),
					})
 
			if not changes:
				return  # save with no actual field changes — don't log noise
 
			# Special-case PUBLISHED / UNPUBLISHED so the action column is meaningful
			pub_change = next(
				(c for c in changes if c["fieldname"] == "publish_status"), None
			)
			if pub_change and len(changes) == 1:
				if pub_change["new"] == "PUBLISHED":
					action = "PUBLISHED"
				elif pub_change["new"] == "DRAFT":
					action = "UNPUBLISHED"
				else:
					action = "UPDATED"
			else:
				action = "UPDATED"
 
			log_change(
				timetable_entry=self.name,
				action=action,
				changes=changes,
				snapshot_before=old_state,
				snapshot_after=new_state,
			)
		except Exception:
			# A failed log write must never block the user's save
			frappe.logger().warning(
				f"[TVMS] Failed to log change for Timetable {self.name}",
				exc_info=True,
			)
 
	def on_trash(self):
		"""Write a DELETED row to Timetable Change Log before the entry vanishes."""
		try:
			snapshot = {f: self.get(f) for f in _TVMS_LOGGED_FIELDS}
			log_change(
				timetable_entry=self.name,
				action="DELETED",
				changes=None,
				snapshot_before=snapshot,
				snapshot_after=None,
			)
		except Exception:
			frappe.logger().warning(
				f"[TVMS] Failed to log delete for Timetable {self.name}",
				exc_info=True,
			)


# ============================================================
# FR-1 — Create a single class OR a weekly recurring series
# ============================================================

@frappe.whitelist(methods=["POST"])
def create_timetable_entry(
	course: str,
	date: str,
	start_time: str,
	end_time: str,
	venue: str = None,
	lecturer: str = None,
	academic_year: str = None,
	semester: str = None,
	department: str = None,
	program: str = None,
	year_level: str = None,
	students_groups: str = None,
	repeat_weekly_until: str = None,
):
	"""Create one timetable entry, or a weekly recurring series.

	If repeat_weekly_until is given, the same class is inserted every week
	on the same weekday from `date` through that end date — this is how
	a full semester schedule is built without any CSV import.

	If a single week in the series hits a conflict, that week is recorded
	in `errors` but the rest of the series still gets created.

	Returns:
	    {
	      "created":   [doc_names...],
	      "count":     N,
	      "first":     "TIMETABLE-0001",
	      "errors":    [{"date": "...", "error": "..."}, ...],
	      "recurring": True|False
	    }
	"""
	_ensure_timetable_admin()

	if not course or not date or not start_time or not end_time:
		frappe.throw(_("course, date, start_time and end_time are required"))

	# Build list of dates to insert
	dates_to_create = [getdate(date)]
	if repeat_weekly_until:
		until = getdate(repeat_weekly_until)
		start_date = getdate(date)
		if until < start_date:
			frappe.throw(_("repeat_weekly_until must be on or after date"))
		if (until - start_date).days > 365:
			frappe.throw(_("Cannot create more than 52 recurring weeks at once"))

		dates_to_create = []
		current = start_date
		while current <= until:
			dates_to_create.append(current)
			current = add_days(current, 7)

	created = []
	errors  = []

	for d in dates_to_create:
		try:
			doc = frappe.new_doc("Timetable")
			doc.course          = course
			doc.venue           = venue
			doc.lecturer        = lecturer
			doc.date            = d
			doc.start_time      = start_time
			doc.end_time        = end_time
			doc.academic_year   = academic_year
			doc.semester        = semester
			doc.department      = department
			doc.program         = program
			doc.year_level      = year_level
			doc.students_groups = students_groups
			doc.status          = "SCHEDULED"
			# New entries always start as DRAFT — admin publishes explicitly
			if hasattr(doc, "publish_status"):
				doc.publish_status = "DRAFT"
			doc.insert()
			created.append(doc.name)
		except frappe.exceptions.ValidationError as e:
			errors.append({"date": str(d), "error": str(e)})

	frappe.db.commit()

	return {
		"created":   created,
		"count":     len(created),
		"first":     created[0] if created else None,
		"errors":    errors,
		"recurring": bool(repeat_weekly_until),
	}


# ============================================================
# FR-2 — Update an existing entry
# ============================================================

@frappe.whitelist(methods=["POST"])
def update_timetable_entry(name: str, **fields):
	"""Update fields on one Timetable entry.

	Only fields that are passed (non-None) are touched. The doctype's
	validate() runs automatically via doc.save() so conflict checks
	happen here too.
	"""
	_ensure_timetable_admin()

	if not frappe.db.exists("Timetable", name):
		frappe.throw(
			_("Timetable entry not found: {0}").format(name),
			frappe.DoesNotExistError,
		)

	allowed = {
		"course", "venue", "lecturer", "date", "start_time", "end_time",
		"academic_year", "semester", "department", "program",
		"year_level", "students_groups", "status", "publish_status",
	}

	doc = frappe.get_doc("Timetable", name)
	changed = []
	for fieldname, value in fields.items():
		if fieldname in allowed and value is not None:
			if doc.get(fieldname) != value:
				doc.set(fieldname, value)
				changed.append(fieldname)

	if changed:
		doc.save()
		frappe.db.commit()

	return {"name": doc.name, "updated": True, "fields_changed": changed}


# ============================================================
# FR-3 — Delete entries (single or bulk)
# ============================================================

@frappe.whitelist(methods=["POST"])
def delete_timetable_entry(name: str):
	"""Delete one Timetable entry."""
	_ensure_timetable_admin()

	if not frappe.db.exists("Timetable", name):
		frappe.throw(
			_("Timetable entry not found: {0}").format(name),
			frappe.DoesNotExistError,
		)

	frappe.delete_doc("Timetable", name, ignore_permissions=False)
	frappe.db.commit()
	return {"name": name, "deleted": True}


@frappe.whitelist(methods=["POST"])
def bulk_delete_timetable_entries(
	program: str = None,
	year_level: str = None,
	semester: str = None,
	academic_year: str = None,
	week_start: str = None,
	publish_status: str = None,
):
	"""Bulk delete timetable entries matching the given filters.

	Safety: at least one filter must be provided. Calling with no filters
	would wipe the whole table and is rejected.

	Common uses:
	    - week_start='2026-09-01'                          → delete one week
	    - program='BSc-IT', year_level='1'                 → reset one segment
	    - publish_status='DRAFT'                           → clear all drafts
	"""
	_ensure_timetable_admin()

	filters = {}
	if program:        filters["program"]        = program
	if year_level:     filters["year_level"]     = str(year_level)
	if semester:       filters["semester"]       = semester
	if academic_year:  filters["academic_year"]  = academic_year
	if publish_status: filters["publish_status"] = publish_status

	if week_start:
		ws = getdate(week_start)
		we = add_days(ws, 7)
		filters["date"] = ["between", [ws, we]]

	if not filters:
		frappe.throw(_("At least one filter is required for bulk delete"))

	names = frappe.db.get_all("Timetable", filters=filters, pluck="name")
	for name in names:
		frappe.delete_doc("Timetable", name, ignore_permissions=False)

	frappe.db.commit()
	return {"deleted": len(names), "filters": filters}


# ============================================================
# FR-2 — Fetch one entry for the edit dialog
# ============================================================

@frappe.whitelist(methods=["GET"])
def get_timetable_entry(name: str):
	"""Return one Timetable entry, pre-formatted for the edit dialog.

	Times are sliced to HH:MM and dates to YYYY-MM-DD so the dialog
	inputs can use the values directly without parsing.
	"""
	_ensure_timetable_admin()

	if not frappe.db.exists("Timetable", name):
		frappe.throw(
			_("Timetable entry not found: {0}").format(name),
			frappe.DoesNotExistError,
		)

	doc = frappe.get_doc("Timetable", name)
	return {
		"name":            doc.name,
		"course":          doc.course,
		"venue":           doc.venue,
		"lecturer":        doc.lecturer,
		"date":            str(doc.date) if doc.date else None,
		"day_of_week":     doc.day_of_week,
		"start_time":      str(doc.start_time)[:5] if doc.start_time else None,
		"end_time":        str(doc.end_time)[:5] if doc.end_time else None,
		"duration_hours":  doc.duration_hours,
		"academic_year":   doc.academic_year,
		"semester":        doc.semester,
		"department":      doc.department,
		"program":         doc.program,
		"year_level":      doc.year_level,
		"students_groups": doc.students_groups,
		"status":          doc.status,
		"publish_status":  getattr(doc, "publish_status", "DRAFT"),
	}


# ============================================================
# Conflict preview — used by the Add Class dialog
# ============================================================

@frappe.whitelist(methods=["GET"])
def preview_conflicts(
	date: str,
	start_time: str,
	end_time: str,
	venue: str = None,
	lecturer: str = None,
	exclude_name: str = None,
):
	"""Return entries that would conflict with the given slot.

	The Add Class dialog calls this whenever date / time / venue / lecturer
	changes so the admin sees conflicts BEFORE hitting Create.
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	if not date or not start_time or not end_time:
		return []

	conflicts = []
	exclude   = exclude_name or ""

	if venue:
		rows = frappe.db.sql("""
			SELECT name, course, lecturer, start_time, end_time, publish_status
			FROM `tabTimetable`
			WHERE venue       = %(venue)s
			  AND date        = %(date)s
			  AND start_time  < %(end_time)s
			  AND end_time    > %(start_time)s
			  AND name       != %(exclude)s
		""", {
			"venue": venue, "date": date,
			"start_time": start_time, "end_time": end_time,
			"exclude": exclude,
		}, as_dict=True)
		for row in rows:
			conflicts.append({
				"reason": "venue",
				"detail": _("Venue is already booked for course {0}").format(row.course),
				"entry":  row,
			})

	if lecturer:
		rows = frappe.db.sql("""
			SELECT name, course, venue, start_time, end_time, publish_status
			FROM `tabTimetable`
			WHERE lecturer    = %(lecturer)s
			  AND date        = %(date)s
			  AND start_time  < %(end_time)s
			  AND end_time    > %(start_time)s
			  AND name       != %(exclude)s
		""", {
			"lecturer": lecturer, "date": date,
			"start_time": start_time, "end_time": end_time,
			"exclude": exclude,
		}, as_dict=True)
		for row in rows:
			conflicts.append({
				"reason": "lecturer",
				"detail": _("Lecturer is already teaching course {0}").format(row.course),
				"entry":  row,
			})

	return conflicts


# ============================================================
# Publish workflow — DRAFT → PUBLISHED (official timetable)
# ============================================================

@frappe.whitelist(methods=["POST"])
def publish_timetable(
	program: str = None,
	year_level: str = None,
	semester: str = None,
	academic_year: str = None,
):
	"""Bulk publish: flip every matching DRAFT entry to PUBLISHED.

	With no filters → publishes ALL drafts (use carefully).
	With program + year_level → publishes one program-year segment (typical).
	"""
	_ensure_timetable_admin()

	filters = [["publish_status", "=", "DRAFT"]]
	if program:       filters.append(["program",       "=", program])
	if year_level:    filters.append(["year_level",    "=", str(year_level)])
	if semester:      filters.append(["semester",      "=", semester])
	if academic_year: filters.append(["academic_year", "=", academic_year])

	drafts = frappe.db.get_all("Timetable", filters=filters, pluck="name")
	for name in drafts:
		frappe.db.set_value("Timetable", name, "publish_status", "PUBLISHED")

	frappe.db.commit()

	frappe.publish_realtime(
		"tvms_timetable_published",
		{"count": len(drafts), "program": program, "year_level": year_level},
	)

	return {
		"published": len(drafts),
		"filters": {
			"program": program, "year_level": year_level,
			"semester": semester, "academic_year": academic_year,
		},
	}


@frappe.whitelist(methods=["POST"])
def unpublish_timetable(
	program: str = None,
	year_level: str = None,
	semester: str = None,
	academic_year: str = None,
):
	"""Reverse of publish — flip PUBLISHED back to DRAFT.
	Use when a major schedule change is being prepared."""
	_ensure_timetable_admin()

	filters = [["publish_status", "=", "PUBLISHED"]]
	if program:       filters.append(["program",       "=", program])
	if year_level:    filters.append(["year_level",    "=", str(year_level)])
	if semester:      filters.append(["semester",      "=", semester])
	if academic_year: filters.append(["academic_year", "=", academic_year])

	published = frappe.db.get_all("Timetable", filters=filters, pluck="name")
	for name in published:
		frappe.db.set_value("Timetable", name, "publish_status", "DRAFT")

	frappe.db.commit()
	return {"unpublished": len(published)}


@frappe.whitelist(methods=["GET"])
def get_publish_status_summary():
	"""Quick stat: how many DRAFT vs PUBLISHED entries currently exist.
	Drives the publish button label on the admin page."""
	frappe.has_permission("Timetable", "read", throw=True)
	return {
		"draft":     frappe.db.count("Timetable", {"publish_status": "DRAFT"}),
		"published": frappe.db.count("Timetable", {"publish_status": "PUBLISHED"}),
		"total":     frappe.db.count("Timetable"),
	}


# ============================================================
# Read APIs — week view
# ============================================================

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

	This is the admin-side read API — shows both DRAFT and PUBLISHED.
	Non-admin users should call get_published_week_timetable() instead.
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	week_days = 7 if int(include_weekends or 0) else 5
	week_end  = str(add_days(getdate(week_start), week_days - 1))

	filters = [
		["date", ">=", week_start],
		["date", "<=", week_end],
	]
	if lecturer:      filters.append(["lecturer",       "=", lecturer])
	if venue:         filters.append(["venue",          "=", venue])
	if course:        filters.append(["course",         "=", course])
	if semester:      filters.append(["semester",       "=", semester])
	if academic_year: filters.append(["academic_year",  "=", academic_year])

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
		fields=[
			"name", "course", "lecturer", "venue", "date", "day_of_week",
			"start_time", "end_time", "duration_hours", "status",
			"publish_status", "program", "year_level",
			"academic_year", "semester", "students_groups",
		],
		order_by="date asc, start_time asc",
	)

	if not sessions:
		return sessions

	# Enrich with display names — 3 small lookups, not N queries
	course_map = {
		r["name"]: r["course_name"]
		for r in frappe.db.get_all("Course", fields=["name", "course_name"])
	}
	user_map = {
		r["name"]: r["full_name"]
		for r in frappe.db.get_all(
			"User", filters={"enabled": 1}, fields=["name", "full_name"]
		)
	}
	venue_map = {
		r["name"]: r
		for r in frappe.db.get_all(
			"Venue", fields=["name", "venue_name", "current_status", "location"]
		)
	}

	for s in sessions:
		s["course_name"]    = course_map.get(s["course"]) or s["course"]
		s["lecturer_name"]  = user_map.get(s["lecturer"]) if s.get("lecturer") else None
		v = venue_map.get(s["venue"]) if s.get("venue") else None
		s["venue_name"]     = v.get("venue_name") if v else s.get("venue")
		s["venue_status"]   = v.get("current_status") if v else None
		s["venue_location"] = v.get("location") if v else None

	return sessions


@frappe.whitelist(methods=["GET"])
def get_published_week_timetable(
	week_start: str,
	program: str = None,
	year_level: str = None,
	semester: str = None,
	academic_year: str = None,
):
	"""Return only PUBLISHED entries for the week — what students/lecturers see.

	The result is grouped by program + year_level for the segmented view.
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	if not week_start:
		frappe.throw(_("week_start is required"))

	start = getdate(week_start)
	end   = add_days(start, 7)

	filters = [
		["publish_status", "=", "PUBLISHED"],
		["date", ">=", start],
		["date", "<",  end],
	]
	if program:       filters.append(["program",       "=", program])
	if year_level:    filters.append(["year_level",    "=", str(year_level)])
	if semester:      filters.append(["semester",      "=", semester])
	if academic_year: filters.append(["academic_year", "=", academic_year])

	rows = frappe.db.get_all(
		"Timetable",
		filters=filters,
		fields=[
			"name", "course", "lecturer", "venue", "date",
			"day_of_week", "start_time", "end_time", "duration_hours",
			"program", "year_level", "academic_year", "semester",
			"department", "students_groups", "status",
		],
		order_by="date asc, start_time asc",
	)

	if not rows:
		return {
			"sessions":   [],
			"groups":     [],
			"week_start": str(start),
			"week_end":   str(end),
		}

	# Batch lookups for course / venue / lecturer display fields
	course_codes = list({r["course"]   for r in rows if r.get("course")})
	venue_codes  = list({r["venue"]    for r in rows if r.get("venue")})
	user_codes   = list({r["lecturer"] for r in rows if r.get("lecturer")})

	course_lookup = {
		c["name"]: c for c in frappe.db.get_all(
			"Course",
			filters={"name": ["in", course_codes]} if course_codes else None,
			fields=["name", "course_code", "course_name"],
		)
	} if course_codes else {}

	venue_lookup = {
		v["name"]: v for v in frappe.db.get_all(
			"Venue",
			filters={"name": ["in", venue_codes]} if venue_codes else None,
			fields=["name", "venue_name", "building_name", "floor_number"],
		)
	} if venue_codes else {}

	user_lookup = {
		u["name"]: u["full_name"] for u in frappe.db.get_all(
			"User",
			filters={"name": ["in", user_codes]} if user_codes else None,
			fields=["name", "full_name"],
		)
	} if user_codes else {}

	for r in rows:
		c = course_lookup.get(r["course"], {})
		v = venue_lookup.get(r["venue"], {})
		r["course_code"]    = c.get("course_code") or r.get("course") or ""
		r["course_name"]    = c.get("course_name") or r.get("course") or ""
		r["venue_name"]     = v.get("venue_name")  or r.get("venue")  or ""
		r["venue_building"] = v.get("building_name") or ""
		r["venue_floor"]    = v.get("floor_number")
		r["lecturer_name"]  = user_lookup.get(r["lecturer"]) if r.get("lecturer") else ""
		r["start_time"]     = str(r["start_time"])[:5] if r.get("start_time") else ""
		r["end_time"]       = str(r["end_time"])[:5]   if r.get("end_time")   else ""
		r["date"]           = str(r["date"])           if r.get("date")       else ""

	# Group by (program, year_level)
	groups_map = {}
	for s in rows:
		prog = s.get("program") or "Unassigned"
		yl   = s.get("year_level") or "Unassigned"
		key  = (prog, yl)
		groups_map.setdefault(key, {
			"program":    prog,
			"year_level": yl,
			"label":      f"{prog} — Year {yl}" if yl != "Unassigned" else prog,
			"sessions":   [],
		})["sessions"].append(s)

	groups = sorted(
		groups_map.values(),
		key=lambda g: (g["program"] == "Unassigned", g["program"], g["year_level"]),
	)

	return {
		"sessions":       rows,
		"groups":         groups,
		"week_start":     str(start),
		"week_end":       str(end),
		"total_sessions": len(rows),
	}


# ============================================================
# Read APIs — program-grouped (segmented admin grid)
# ============================================================

_YEAR_LEVEL_LABELS = {
	"1": "First Year",  "i":   "First Year",  "year 1": "First Year",  "first year":  "First Year",
	"2": "Second Year", "ii":  "Second Year", "year 2": "Second Year", "second year": "Second Year",
	"3": "Third Year",  "iii": "Third Year",  "year 3": "Third Year",  "third year":  "Third Year",
	"4": "Fourth Year", "iv":  "Fourth Year", "year 4": "Fourth Year", "fourth year": "Fourth Year",
	"5": "Fifth Year",  "v":   "Fifth Year",  "year 5": "Fifth Year",  "fifth year":  "Fifth Year",
}


def _year_level_label(value):
	"""Normalise year_level into a display label: '1' → 'First Year'."""
	if not value:
		return ""
	return _YEAR_LEVEL_LABELS.get(str(value).strip().lower(), str(value).strip())


@frappe.whitelist(methods=["GET", "POST"])
def get_program_timetable_groups(
	week_start: str,
	include_weekends: int = 0,
	program: str = None,
	year_level: str = None,
):
	"""Return the week's entries grouped by Program + Year Level.

	Each group becomes its own weekly grid in the admin UI — e.g.
	"Bachelor's Degree in Information - First Year" with its own
	Monday-Friday table, matching paper/Excel timetable layouts.
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	sessions = get_week_timetable(week_start, include_weekends=include_weekends)

	groups = {}
	for s in sessions:
		s_program = s.get("program") or ""
		s_year    = s.get("year_level") or ""

		if program and s_program != program:
			continue
		if year_level and s_year != year_level:
			continue

		key = f"{s_program}||{s_year}"
		if key not in groups:
			label = f"{s_program} - {s_year}" if (s_program and s_year) else (s_program or s_year or "Unassigned")
			groups[key] = {
				"key":        key,
				"label":      label,
				"program":    s_program,
				"year_level": s_year,
				"sessions":   [],
			}
		groups[key]["sessions"].append(s)

	year_order = {
		"first year":  1, "1st year": 1, "year 1": 1, "year i":   1,
		"second year": 2, "2nd year": 2, "year 2": 2, "year ii":  2,
		"third year":  3, "3rd year": 3, "year 3": 3, "year iii": 3,
		"fourth year": 4, "4th year": 4, "year 4": 4, "year iv":  4,
		"fifth year":  5, "5th year": 5, "year 5": 5, "year v":   5,
	}

	sorted_groups = sorted(
		groups.values(),
		key=lambda g: (
			g["program"].lower(),
			year_order.get(g["year_level"].lower(), 99),
			g["year_level"].lower(),
		),
	)

	return {"week_start": week_start, "groups": sorted_groups}


@frappe.whitelist(methods=["GET"])
def get_program_year_options():
	"""Return distinct (program, year_level) combinations for filters
	and for pre-filling the Add Class dialog with a specific segment.
	"""
	frappe.has_permission("Timetable", "read", throw=True)

	rows = frappe.db.get_all(
		"Timetable",
		fields=["program", "year_level"],
		distinct=True,
	)

	programs    = sorted({r["program"]    for r in rows if r.get("program")})
	year_levels = sorted({r["year_level"] for r in rows if r.get("year_level")})

	pairs = sorted({
		(r.get("program") or "", r.get("year_level") or "")
		for r in rows
		if r.get("program") or r.get("year_level")
	})

	groups = []
	for p, y in pairs:
		label = f"{p} - {y}" if (p and y) else (p or y)
		groups.append({"program": p, "year_level": y, "label": label})

	return {
		"programs":    programs,
		"year_levels": year_levels,
		"groups":      groups,
	}


# ============================================================
# Filter options for dropdowns
# ============================================================

@frappe.whitelist(methods=["GET", "POST"])
def get_filter_options():
	"""Return distinct lecturers, venues, courses, programs, semesters,
	and academic years for the page filter dropdowns."""
	frappe.has_permission("Timetable", "read", throw=True)

	def distinct(fieldname):
		return [
			v for v in frappe.db.get_all("Timetable", pluck=fieldname, distinct=True)
			if v
		]

	lecturers = distinct("lecturer")
	venues    = distinct("venue")
	courses   = distinct("course")

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
		"lecturers":      lecturer_options,
		"venues":         venue_options,
		"courses":        course_options,
		"programs":       get_programs(),
		"semesters": frappe.db.sql_list(
			"SELECT DISTINCT semester FROM `tabTimetable` "
			"WHERE semester IS NOT NULL AND semester != '' "
			"ORDER BY semester"
		),
		"academic_years": frappe.db.sql_list(
			"SELECT DISTINCT academic_year FROM `tabTimetable` "
			"WHERE academic_year IS NOT NULL AND academic_year != '' "
			"ORDER BY academic_year"
		),
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_programs():
	"""Return all distinct programs from the Course table."""
	return frappe.db.sql_list(
		"SELECT DISTINCT program FROM `tabCourse` "
		"WHERE program IS NOT NULL AND program != '' "
		"ORDER BY program"
	)


# ============================================================
# Current user context (for page role-aware rendering)
# ============================================================

@frappe.whitelist(methods=["GET", "POST"])
def get_current_user_context():
	"""Return the current user's role context for Desk/page integrations."""
	user  = frappe.session.user
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
		"user":         user,
		"full_name":    full_name,
		"primary_role": primary_role,
		"is_admin":     primary_role == "admin",
		"is_lecturer": primary_role == "lecturer",
	}
#  Two whitelisted read APIs for the UI
@frappe.whitelist(methods=["GET"])
def get_timetable_history(timetable_entry: str, limit: int = 50):
	"""Return the change log for one Timetable entry, newest first.
 
	Used by:
	- The inline "History" tab on the Timetable form
	- The Edit Class dialog footer ("Last changed by X on Y")
	"""
	_ensure_timetable_admin()
 
	if not frappe.db.exists("Timetable", timetable_entry):
		# Don't throw — return empty so a deleted entry's history can still be viewed
		# via the global page where the link still resolves via the log row.
		pass
 
	limit = min(int(limit or 50), 200)
 
	rows = frappe.db.get_all(
		"Timetable Change Log",
		filters={"timetable_entry": timetable_entry},
		fields=[
			"name", "action", "timestamp", "changed_by",
			"summary", "reason", "changes",
		],
		order_by="timestamp desc",
		limit=limit,
	)
 
	# Enrich changed_by with full name (one query, not N)
	users = list({r["changed_by"] for r in rows if r.get("changed_by")})
	full_names = {
		u["name"]: u["full_name"] for u in frappe.db.get_all(
			"User",
			filters={"name": ["in", users]} if users else None,
			fields=["name", "full_name"],
		)
	} if users else {}
 
	for r in rows:
		r["changed_by_name"] = full_names.get(r.get("changed_by"), r.get("changed_by") or "")
		r["timestamp"] = str(r["timestamp"])[:16] if r.get("timestamp") else ""
		# Parse the changes JSON so the UI doesn't have to
		if r.get("changes"):
			try:
				r["changes"] = json.loads(r["changes"])
			except Exception:
				pass
 
	return {
		"timetable_entry": timetable_entry,
		"total": frappe.db.count("Timetable Change Log", {"timetable_entry": timetable_entry}),
		"history": rows,
	}
 
 
@frappe.whitelist(methods=["GET"])
def search_timetable_changes(
	from_date: str = None,
	to_date: str = None,
	changed_by: str = None,
	action: str = None,
	program: str = None,
	limit: int = 100,
):
	"""Global search across the change log — used by /app/tvms-changes.
 
	All filters are optional. With no filters → returns the most recent
	100 changes across the whole timetable.
	"""
	_ensure_timetable_admin()
 
	filters = []
	if from_date:
		filters.append(["timestamp", ">=", from_date])
	if to_date:
		filters.append(["timestamp", "<=", f"{to_date} 23:59:59"])
	if changed_by:
		filters.append(["changed_by", "=", changed_by])
	if action:
		filters.append(["action", "=", action])
 
	rows = frappe.db.get_all(
		"Timetable Change Log",
		filters=filters,
		fields=[
			"name", "timetable_entry", "action", "timestamp",
			"changed_by", "summary", "reason",
		],
		order_by="timestamp desc",
		limit=min(int(limit or 100), 500),
	)
 
	# Filter by program if requested — done in Python because program lives on
	# the Timetable entry, not the log row.
	if program:
		entry_names = [r["timetable_entry"] for r in rows if r.get("timetable_entry")]
		entries_in_program = set(frappe.db.get_all(
			"Timetable",
			filters={
				"name": ["in", entry_names] if entry_names else None,
				"program": program,
			},
			pluck="name",
		)) if entry_names else set()
		rows = [r for r in rows if r["timetable_entry"] in entries_in_program]
 
	users = list({r["changed_by"] for r in rows if r.get("changed_by")})
	full_names = {
		u["name"]: u["full_name"] for u in frappe.db.get_all(
			"User",
			filters={"name": ["in", users]} if users else None,
			fields=["name", "full_name"],
		)
	} if users else {}
 
	for r in rows:
		r["changed_by_name"] = full_names.get(r.get("changed_by"), r.get("changed_by") or "")
		r["timestamp"] = str(r["timestamp"])[:16] if r.get("timestamp") else ""
 
	return {
		"total": len(rows),
		"changes": rows,
		"filters": {
			"from_date": from_date, "to_date": to_date,
			"changed_by": changed_by, "action": action, "program": program,
		},
	}