# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import get_datetime, now_datetime, add_to_date, time_diff_in_hours, getdate, get_time
from tvms.tvms.doctype.tvms_notifications.tvms_notifications import _create_tvms_notification
from tvms.tvms.doctype.tvms_audit_log.tvms_audit_log import log_event


class Emergencysession(Document):
	def before_validate(self):
		# Defaults must be set here — before validate() reads them
		if not self.created_by:
			self.created_by = frappe.session.user
		roles = frappe.get_roles(self.created_by)

		#lecturers: auto assign
		if "Lecturer" in roles:
			self.lecturer = self.created_by
		#CRs: must specify a lecturer to be notified and avoid double-booking issues.
		elif "Class Representative (CR)" in roles:
			if not self.lecturer:
				frappe.throw("Please specify the lecturer for this session")

		if self.is_new() and not self.status:
			self.status = "PENDING"

		if self.course and not self.expected_students:
			self._set_expected_students_from_course()

		if not self.role_type and self.created_by:
			self._set_role_type()

	def validate(self):
		self._prevent_direct_status_change()
		self._validate_time_range()
		self._validate_session_duration()
		self._validate_venue_capacity()
		self._check_venue_availability()
		self._check_lecturer_availability()

	def on_update(self):
		if (
			self.has_value_changed("status")
			or self.has_value_changed("venue")
			or self.has_value_changed("start_time")
			or self.has_value_changed("end_time")
		):
			self._update_venue_status()
 
		if self.has_value_changed("status"):
			# Map status to audit event_type
			event_type_map = {
				"CONFIRMED": "SESSION_CONFIRMED",
				"CANCELLED": "SESSION_CANCELLED",
				"COMPLETED": "SESSION_COMPLETED",
				"EXPIRED":   "SESSION_EXPIRED",
				"PENDING":   "SESSION_CREATED",
			}
			event_type = event_type_map.get(self.status, "OTHER")
 
			# Write the parent audit row FIRST so notifications can link back to it
			parent_audit = log_event(
				event_type=event_type,
				summary=_("Session {0}: {1}").format(self.status, self.title),
				subject_type="Emergency session",
				subject_name=self.name,
				subject_label=self.title or self.name,
				payload={
					"new_status": self.status,
					"venue":      self.venue,
					"course":     self.course,
					"start_time": str(self.start_time)[:16] if self.start_time else None,
					"end_time":   str(self.end_time)[:16] if self.end_time else None,
				},
			)
 
			# Stash on flags so _send_status_notification / _notify_crs can link to it
			self.flags.parent_audit = parent_audit
 
			# Also still send the side-effect notifications + timeline comment
			self._send_status_notification()
			self._notify_crs()
 
			# Lightweight timeline comment (no second audit write — we already wrote one)
			frappe.get_doc({
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": self.doctype,
				"reference_name": self.name,
				"content": _("Status changed to {0}").format(self.status),
			}).insert(ignore_permissions=True)

	def after_insert(self):
		self._update_venue_status()

	# --- Status protection ---

	def _prevent_direct_status_change(self):
		"""Block UI-level status edits — all transitions must go through action methods"""
		if self.is_new() or self.flags.get("status_action"):
			return
		old_status = frappe.db.get_value("Emergency session", self.name, "status")
		if old_status and old_status != self.status:
			frappe.throw(_(
				"Status cannot be changed directly. "
				"Use the action buttons (Confirm, Cancel, Complete) instead."
			))

	# --- Venue status management ---

	def _update_venue_status(self):
		"""Keep Venue.current_status in sync with the session lifecycle (FR-23, FR-25)"""
		venues = set()
		if self.venue:
			venues.add(self.venue)

		old_doc = self.get_doc_before_save()
		if old_doc and old_doc.venue:
			venues.add(old_doc.venue)

		if not venues:
			return

		for venue in venues:
			venue_doc = frappe.get_doc("Venue", venue)
			venue_status = venue_doc.compute_status()
			frappe.db.set_value("Venue", venue, "current_status", venue_status)
			venue_doc.current_status = venue_status

			# Push live venue status update to Desk pages.
			frappe.publish_realtime(
				"venue_status_update",
				{
					"venue": venue,
					"status": venue_status,
					"session": self.name,
					"session_status": self.status,
					"start_time": self.start_time,
					"end_time": self.end_time,
				},
				after_commit=True,
			)

	# --- Setup helpers ---

	def _set_expected_students_from_course(self):
		students = frappe.db.get_value("Course", self.course, "expected_students")
		if students:
			self.expected_students = students

	def _set_role_type(self):
		roles = frappe.get_roles(self.created_by)
		if "Lecturer" in roles:
			self.role_type = "Lecturer"
		elif "Class Representative (CR)" in roles:
			self.role_type = "Class Representative (CR)"
		elif "Department Admin" in roles:
			self.role_type = "Department Admin"

	# --- Validation ---

	def _validate_time_range(self):
		if self.start_time and self.end_time:
			if get_datetime(self.start_time) >= get_datetime(self.end_time):
				frappe.throw(_("Start time must be before end time"))

	def _validate_session_duration(self):
		"""FR-18: Sessions shall not exceed the configured maximum duration (default 2 hrs)"""
		if not self.start_time or not self.end_time:
			return
		settings = self._get_tvms_settings()
		max_hours = settings.get("max_session_hours") or frappe.conf.get("max_emergency_session_hours", 2)
		duration = time_diff_in_hours(self.end_time, self.start_time)
		if duration > max_hours:
			frappe.throw(_(
				"Session duration ({0:.1f} hrs) exceeds the maximum allowed ({1} hrs)"
			).format(duration, max_hours))

	def _validate_venue_capacity(self):
		if not self.venue or not self.expected_students:
			return
		capacity = frappe.db.get_value("Venue", self.venue, "capacity")
		if capacity is None:
			frappe.throw(_("Venue {0} not found").format(self.venue))
		if capacity and self.expected_students > capacity:
			frappe.throw(_(
				"Expected students ({0}) exceeds venue capacity ({1})"
			).format(self.expected_students, capacity))

	def _check_venue_availability(self):
		"""FR-13: Prevent double booking — A overlaps B iff A.start < B.end AND A.end > B.start"""
		if not self.start_time or not self.end_time or not self.venue:
			return

		conflicts = frappe.db.get_all(
			"Emergency session",
			filters=[
				["venue", "=", self.venue],
				["status", "not in", ["CANCELLED", "COMPLETED", "EXPIRED"]],
				["name", "!=", self.name or ""],
				["start_time", "<", self.end_time],
				["end_time", ">", self.start_time],
			],
			fields=["name", "title"],
		)

		if conflicts:
			frappe.throw(_(
				"Venue is already booked for the requested time. "
				"Conflicting session: {0}"
			).format(conflicts[0]["title"]))

	def _check_lecturer_availability(self):
		"""FR-14: A lecturer cannot be double-booked across any session type at the same time."""
		if not self.created_by or not self.start_time or not self.end_time:
			return
		if "Lecturer" not in frappe.get_roles(self.created_by):
			return

		# 1. Check conflicts against other Emergency Sessions
		ems_conflicts = frappe.db.get_all(
			"Emergency session",
			filters=[
				["lecturer", "=", self.lecturer],
				["status", "not in", ["CANCELLED", "COMPLETED", "EXPIRED"]],
				["name", "!=", self.name or ""],
				["start_time", "<", self.end_time],
				["end_time", ">", self.start_time],
			],
			fields=["name", "title", "venue", "start_time", "end_time"],
		)

		if ems_conflicts:
			c = ems_conflicts[0]
			frappe.throw(
				_("You are already booked in <strong>{0}</strong> (venue: {1}) "
				  "from {2} to {3}.<br><br>"
				  "You cannot hold two venues at the same time. "
				  "Please choose a different time slot.").format(
					c["title"],
					c["venue"] or "—",
					str(c["start_time"])[:16],
					str(c["end_time"])[:16],
				),
				title=_("Lecturer Already Booked"),
			)
		# 2. check conflicts against the course
		course_conflicts = frappe.db.get_all(
			"Emergency session",
			filters=[
				["course", "=", self.course],
				["status", "not in", ["CANCELLED", "COMPLETED", "EXPIRED"]],
				["name", "!=", self.name or ""],
				["start_time", "<", self.end_time],
				["end_time", ">", self.start_time],
			],
			fields=["name", "title", "venue", "start_time", "end_time"],
		)
		if course_conflicts:
			frappe.throw(_("This course already has a session scheduled at the same time. Please choose a different time slot."
				  "in venue {0}."
				  ).format(course_conflicts[0]["venue"]))

		# 3. Check conflicts against the official Timetable
		session_date  = getdate(self.start_time)
		session_start = get_time(self.start_time)
		session_end   = get_time(self.end_time)

		tt_conflicts = frappe.db.get_all(
			"Timetable",
			filters=[
				["lecturer", "=", self.created_by],
				["date", "=", session_date],
				["status", "!=", "COMPLETED"],
				["start_time", "<", session_end],
				["end_time", ">", session_start],
			],
			fields=["name", "course", "venue", "start_time", "end_time"],
		)

		if tt_conflicts:
			c = tt_conflicts[0]
			frappe.throw(
				_("You have a scheduled class <strong>{0}</strong> in venue <strong>{1}</strong> "
				  "at this time ({2} – {3}).<br><br>"
				  "A lecturer cannot be booked in two venues simultaneously. "
				  "Please choose a different time slot.").format(
					c["course"],
					c["venue"] or "—",
					str(c["start_time"])[:5],
					str(c["end_time"])[:5],
				),
				title=_("Lecturer Already Booked"),
			)

	# --- Action methods (callable from desk form via frm.call) ---

	@frappe.whitelist()
	def confirm_session(self):
		"""FR-21: Confirm the emergency session within the grace period"""
		if self.status != "PENDING":
			frappe.throw(_("Only PENDING sessions can be confirmed"))

		grace_minutes = frappe.conf.get("session_grace_period_minutes", 40)
		deadline = add_to_date(get_datetime(self.start_time), minutes=grace_minutes)
		if now_datetime() > deadline:
			frappe.throw(_(
				"The confirmation grace period ({0} min) has lapsed. "
				"This session will be automatically expired."
			).format(grace_minutes))

		self.flags.status_action = True
		self.flags.notification_type = "confirmation"
		self.status = "CONFIRMED"
		self.confirmed = 1
		self.confirmed_at = frappe.utils.now()
		self.save()
		return True

	@frappe.whitelist()
	def cancel_session(self):
		"""FR-19: Cancel the emergency session"""
		if self.status == "CANCELLED":
			frappe.throw(_("Session is already cancelled"))
		if self.status == "COMPLETED":
			frappe.throw(_("Completed sessions cannot be cancelled"))

		self.flags.status_action = True
		self.flags.notification_type = "cancellation"
		self.status = "CANCELLED"
		self.save()
		return True

	@frappe.whitelist()
	def complete_session(self):
		"""Mark a CONFIRMED session as completed"""
		if self.status != "CONFIRMED":
			frappe.throw(_("Only CONFIRMED sessions can be marked as completed"))

		self.flags.status_action = True
		self.flags.notification_type = "completion"
		self.status = "COMPLETED"
		self.save()
		return True

	@frappe.whitelist()
	def expire_session(self):
		"""FR-25: Called by the scheduler when grace period lapses without confirmation"""
		if self.status != "PENDING":
			return False

		self.flags.status_action = True
		self.flags.notification_type = "expiry"
		self.status = "EXPIRED"
		self.save()
		return True

	# --- Notifications ---

	def _send_status_notification(self):
		self._send_email_notification()
		self._send_sms_notification()
		self._send_realtime_notification()

	def _send_email_notification(self):
		if not self._is_email_enabled():
			return
		recipients = self._get_notification_recipients()
		if not recipients:
			return
		frappe.sendmail(
			recipients=recipients,
			subject=_("Emergency Session Update: {0}").format(self.name),
			message=self._prepare_notification_message(),
		)

	def _send_sms_notification(self):
		try:
			from tvms.tvms.api.sms_utils import SMSNotification
			notification_type = self.flags.get("notification_type", "status_change")
			SMSNotification().send_emergency_session_notification(
				self, notification_type=notification_type
			)
		except Exception as e:
			frappe.logger().error(f"SMS notification failed: {str(e)}")

	def _send_realtime_notification(self):
		"""FR-34: Push in-system notification to each recipient via WebSocket and create records."""
		data = {
			"session": self.name,
			"title": self.title,
			"status": self.status,
			"venue": self.venue,
		}
		msg = _("Session '{0}' (Venue: {1}, Course: {2}) is now {3}.").format(
			self.title, self.venue or "N/A", self.course or "N/A", self.status
		)
		parent_audit = self.flags.get("parent_audit")
		for recipient in self._get_notification_recipients():
			frappe.publish_realtime(
				"emergency_session_update",
				data,
				user=recipient,
				after_commit=True,
			)
			_create_tvms_notification(
				title=_("Session {0}: {1}").format(self.status, self.title),
				message=msg,
				recipient=recipient,
				reference_type="Emergency session",
				reference_name=self.name,
				channel="in-system",
			)
						# FR-40: log each notification delivery, link to the session action
			log_event(
				event_type="NOTIFICATION_SENT",
				summary=_("Notification sent to {0}: session {1} is now {2}").format(
					recipient, self.name, self.status
				),
				subject_type="Emergency session",
				subject_name=self.name,
				subject_label=self.title or self.name,
				recipient=recipient,
				channel="in-system",
				linked_audit=parent_audit,
			)
 
	def _notify_crs(self):
		"""FR-26: Notify Class Representatives so they can forward to students.
 
		FR-39: When is_critical=1, ALSO push directly to all enabled students
		without waiting for the CR-forward step. Use case: a session cancelled
		within 2 hours of start time — students need to know NOW, the
		CR-forward chain (which depends on a CR being online to act) is too
		slow.
		"""
		if self.status not in ("CANCELLED", "POSTPONED", "EXPIRED"):
			# Confirmations and creations don't fire the critical-bypass —
			# those aren't urgent enough to justify spamming students directly
			# even when is_critical=1.
			return self._notify_crs_standard()
 
		if self.is_critical:
			self._notify_crs_critical()
		else:
			self._notify_crs_standard()
 
 
	def _notify_crs_standard(self):
		"""Default path: notify CRs only. CRs forward to students per FR-28."""
		from tvms.tvms.doctype.tvms_notifications.tvms_notifications import _create_tvms_notification
 
		crs = frappe.db.sql("""
			SELECT DISTINCT u.name, u.full_name
			FROM   `tabHas Role` hr
			INNER JOIN `tabUser` u ON hr.parent = u.name
			WHERE  hr.role = 'Class Representative (CR)'
			AND    u.enabled = 1
		""", as_dict=True)
 
		title = _("Session {0}: {1}").format(self.status, self.title)
		message = self._compose_status_message()
		parent_audit = self.flags.get("parent_audit")
 
		for cr in crs:
			_create_tvms_notification(
				title=title,
				message=message,
				recipient=cr["name"],
				recipient_role="Class Representative (CR)",
				reference_type="Emergency session",
				reference_name=self.name,
				channel="in-system",
			)
			frappe.publish_realtime(
				"emergency_session_update",
				{"session": self.name, "status": self.status, "title": self.title},
				user=cr["name"],
				after_commit=True,
			)
			# Push if available — silent no-op otherwise
			self._try_push(cr["name"], title, message)
 
 
	def _notify_crs_critical(self):
		"""FR-39 critical path: notify CRs AND every enabled Student directly.
 
		Sends BOTH:
		  - in-system + realtime notifications (same as standard path)
		  - email blast to students with the URGENT prefix
		  - push notifications if FCM/APNs configured
 
		Audit: each delivery is logged separately so the audit trail
		clearly shows the critical bypass was used.
		"""
		from tvms.tvms.doctype.tvms_notifications.tvms_notifications import _create_tvms_notification
		from tvms.tvms.doctype.tvms_audit_log.tvms_audit_log import log_event
 
		recipients = frappe.db.sql("""
			SELECT DISTINCT u.name, u.email,
			       (CASE WHEN hr.role = 'Student' THEN 'Student'
			             ELSE 'Class Representative (CR)' END) AS role
			FROM   `tabHas Role` hr
			INNER JOIN `tabUser` u ON hr.parent = u.name
			WHERE  hr.role IN ('Class Representative (CR)', 'Student')
			AND    u.enabled = 1
		""", as_dict=True)
 
		# Critical-prefixed title so notification UIs can style differently
		title_base = self._compose_status_title()
		title = _("⚠ URGENT: {0}").format(title_base)
		message = self._compose_status_message(prefix=_("This is a CRITICAL notification — please read."))
		parent_audit = self.flags.get("parent_audit")
 
		# Audit one aggregate row for the critical bypass action
		critical_audit = log_event(
			event_type="NOTIFICATION_CRITICAL_BYPASS",
			summary=f"Critical bypass: {self.name} notified {len(recipients)} users directly",
			subject_type="Emergency session",
			subject_name=self.name,
			subject_label=self.title,
			channel="critical",
			linked_audit=parent_audit,
			payload={
				"reason":       self.status,
				"recipients":   len(recipients),
				"students":     len([r for r in recipients if r["role"] == "Student"]),
				"crs":          len([r for r in recipients if r["role"] != "Student"]),
			},
		)
 
		for r in recipients:
			user = r["name"]
 
			# In-system inbox
			_create_tvms_notification(
				title=title,
				message=message,
				recipient=user,
				recipient_role=r["role"],
				reference_type="Emergency session",
				reference_name=self.name,
				channel="in-system",
			)
 
			# Realtime push to Desk session if active
			frappe.publish_realtime(
				"emergency_session_critical",
				{
					"session":  self.name,
					"status":   self.status,
					"title":    self.title,
					"critical": True,
				},
				user=user,
				after_commit=True,
			)
 
			# Email blast — even if email_enabled is off, criticals get through
			try:
				frappe.sendmail(
					recipients=[r.get("email") or user],
					subject=title,
					message=message,
					delayed=False,
				)
			except Exception:
				frappe.logger().warning(
					f"[TVMS critical] email failed for {user}", exc_info=True,
				)
 
			# Push notification (best-effort)
			self._try_push(user, title, message, critical=True)
 
			# Per-recipient audit row, linked to the bypass action
			log_event(
				event_type="NOTIFICATION_SENT",
				summary=f"Critical → {user}",
				subject_type="Emergency session",
				subject_name=self.name,
				recipient=user,
				recipient_role=r["role"],
				channel="email",   # email + push + in-system happened
				linked_audit=critical_audit,
			)
 
 
	def _compose_status_title(self):
		"""Title used by both standard and critical paths."""
		return _("Session {0}: {1}").format(self.status, self.title)
 
 
	def _compose_status_message(self, prefix=None):
		"""Body used by both standard and critical paths."""
		venue_label  = self.venue or _("N/A")
		course_label = self.course or _("N/A")
		start_label  = str(self.start_time)[:16] if self.start_time else _("N/A")
 
		message = _(
			"Emergency session <strong>{0}</strong> "
			"(Course: {1}, Venue: {2}, Start: {3}) is now {4}."
		).format(self.title, course_label, venue_label, start_label, self.status)
 
		if prefix:
			return f"<p><strong>{frappe.utils.escape_html(prefix)}</strong></p>{message}"
 
		return message
 
 
	def _try_push(self, user, title, message, critical=False):
		"""Best-effort push notification. Silent no-op if push isn't set up."""
		try:
			from tvms.tvms.api.push_notifications import send_push_to_user
			send_push_to_user(
				user, title, message,
				data={
					"type":     "session_update",
					"session":  self.name,
					"status":   self.status,
					"critical": critical,
				},
			)
		except Exception:
			# Push is optional infrastructure — never break the notification flow
			pass
	def _is_email_enabled(self):
		settings = self._get_tvms_settings()
		return settings.get("email_enabled", True) if settings else frappe.conf.get("email_enabled", True)

	def _get_tvms_settings(self):
		try:
			return frappe.get_single_doc("TVMS Settings").as_dict()
		except Exception:
			return {}

	def _get_notification_recipients(self):
		emails = set()

		if self.created_by:
			email = frappe.db.get_value("User", self.created_by, "email")
			if email:
				emails.add(email)

		# Single JOIN instead of a loop of individual queries
		managers = frappe.db.sql("""
			SELECT DISTINCT u.email
			FROM `tabHas Role` hr
			INNER JOIN `tabUser` u ON hr.parent = u.name
			WHERE hr.role = 'TVMS Manager'
			AND u.enabled = 1
			AND u.email IS NOT NULL
		""", as_list=True)
		for row in managers:
			emails.add(row[0])

		return list(emails)


	def _prepare_notification_message(self):
		# Postponement gets a different layout — emphasise the time change
		if self.flags.get("notification_type") == "postponement":
			pd = self.flags.get("postpone_details", {})
			return """
				<h3>Session Postponed</h3>
				<p><strong>Session:</strong> {0}</p>
				<p><strong>Title:</strong> {1}</p>
				<p><strong>Venue:</strong> {2}</p>
				<p><strong>Course:</strong> {3}</p>
				<table style="border-collapse:collapse;margin:12px 0;">
					<tr>
						<td style="padding:4px 14px 4px 0;color:#888;">Was:</td>
						<td style="padding:4px 0;text-decoration:line-through;">{4} - {5}</td>
					</tr>
					<tr>
						<td style="padding:4px 14px 4px 0;color:#888;">Now:</td>
						<td style="padding:4px 0;font-weight:600;">{6} - {7}</td>
					</tr>
				</table>
				<p><strong>Reason:</strong> {8}</p>
				<p><strong>Status:</strong> {9}</p>
			""".format(
				self.name, self.title, self.venue or "N/A", self.course or "N/A",
				pd.get("old_start") or "—", pd.get("old_end") or "—",
				pd.get("new_start") or "—", pd.get("new_end") or "—",
				pd.get("reason") or _("Not specified"),
				self.status,
			)
 
		# Default — used for confirm / cancel / complete / expire
		return """
			<h3>Emergency Session Update</h3>
			<p><strong>Session:</strong> {0}</p>
			<p><strong>Title:</strong> {1}</p>
			<p><strong>Venue:</strong> {2}</p>
			<p><strong>Course:</strong> {3}</p>
			<p><strong>Start Time:</strong> {4}</p>
			<p><strong>End Time:</strong> {5}</p>
			<p><strong>Status:</strong> {6}</p>
			<p><strong>Comment:</strong> {7}</p>
		""".format(
			self.name, self.title, self.venue, self.course,
			self.start_time, self.end_time, self.status,
			self.comment or "N/A",
		)

	def _log_action(self, message, event_type="OTHER", payload=None, linked_audit=None):
		"""FR-30: Append both a timeline Comment AND a structured audit row.
 
		The Comment is consumed by Frappe's built-in timeline UI on the form.
		The audit row is consumed by /app/tvms-audit and the subject API.
 
		Args:
		    message     -- human-readable summary (used for both)
		    event_type  -- TVMS Audit Log event_type, e.g. SESSION_CONFIRMED
		    payload     -- dict of structured event data
		    linked_audit -- optional parent audit row name
		"""
		# Timeline comment — unchanged from before
		frappe.get_doc({
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": self.doctype,
			"reference_name": self.name,
			"content": message,
		}).insert(ignore_permissions=True)
 
		# Structured audit row
		log_event(
			event_type=event_type,
			summary=message,
			subject_type="Emergency session",
			subject_name=self.name,
			subject_label=self.title or self.name,
			payload=payload,
			linked_audit=linked_audit,
		)
		# Cache the audit name on flags so notification rows can link back to it
		# inside the same on_update cycle.
		audit_name = log_event.__wrapped__ if hasattr(log_event, "__wrapped__") else None
		# Note: log_event returns the audit doc name. Capture it via the return

# --- Module-level whitelisted APIs ---

@frappe.whitelist(methods=["GET"])
def get_venue_availability(venue: str, date: str):
	"""Get all non-cancelled sessions for a venue on a given date"""
	if not venue or not date:
		frappe.throw(_("Venue and date are required"))

	return frappe.db.get_list(
		"Emergency session",
		filters=[
			["venue", "=", venue],
			["start_time", "like", f"{date}%"],
			["status", "not in", ["CANCELLED", "EXPIRED"]],
		],
		fields=["name", "title", "start_time", "end_time", "status"],
		order_by="start_time asc",
	)


@frappe.whitelist(methods=["POST"])
def create_emergency_session(
	title: str,
	course: str,
	start_time: str,
	end_time: str,
	venue: str = None,
	comment: str = None,
	required_resources: str = None,
):
	"""Create a new emergency session via whitelisted Desk/page integrations."""
	doc = frappe.get_doc({
		"doctype":            "Emergency session",
		"title":              title,
		"venue":              venue or None,
		"course":             course,
		"start_time":         start_time,
		"end_time":           end_time,
		"comment":            comment or None,
		"required_resources": required_resources or None,
	})
	doc.insert()
	return doc.as_dict()


# ------------------------------------------------------------------
# Module-level action wrappers for Desk/page integrations
# ------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def confirm_emergency_session(name: str):
	"""Confirm a PENDING session."""
	return frappe.get_doc("Emergency session", name).confirm_session()

@frappe.whitelist(methods=["POST"])
def postpone_emergency_session(
	name: str,
	new_start_time: str,
	new_end_time: str,
	reason: str = None,
):
	"""Reschedule an emergency session to a new time slot.
 
	Whitelisted wrapper around Emergencysession.postpone_session() so it can
	be called from custom Desk pages, the mobile app, or external integrations.
	"""
	return frappe.get_doc("Emergency session", name).postpone_session(
		new_start_time=new_start_time,
		new_end_time=new_end_time,
		reason=reason,
	)
 

@frappe.whitelist()
def postpone_session(self, new_start_time: str, new_end_time: str, reason: str = None):
		"""FR-32 — Reschedule a session to a new time without changing its identity.
 
		Allowed only while the session is still actionable (PENDING or CONFIRMED).
		The session's status is preserved — postponing a CONFIRMED session keeps
		it CONFIRMED at the new time. The standard validation chain runs against
		the new times so venue and lecturer conflicts are caught automatically.
 
		Args:
		    new_start_time -- ISO datetime string for the new start
		    new_end_time   -- ISO datetime string for the new end
		    reason         -- optional explanation surfaced to CRs / students
 
		Raises:
		    ValidationError if the new times overlap an existing booking, exceed
		    the configured max session duration, or violate the time-range check.
		"""
		# Guard: must be in an actionable state
		if self.status not in ("PENDING", "CONFIRMED"):
			frappe.throw(_(
				"Only PENDING or CONFIRMED sessions can be postponed. "
				"This session is currently {0}."
			).format(self.status))
 
		if not new_start_time or not new_end_time:
			frappe.throw(_("Both new start time and new end time are required"))
 
		# Refuse a no-op postpone (admin clicked Postpone but didn't change anything)
		if (get_datetime(new_start_time) == get_datetime(self.start_time)
				and get_datetime(new_end_time) == get_datetime(self.end_time)):
			frappe.throw(_("New times are the same as the current times — nothing to postpone"))
 
		# Capture the FIRST original start time we ever see (preserve across multiple postponements)
		if not self.postponed:
			self.original_start_time = self.start_time
 
		old_start = self.start_time
		old_end   = self.end_time
 
		# Apply the new times — the standard validate() chain will re-run when we save:
		#   _validate_time_range       — checks start < end
		#   _validate_session_duration — checks against max_session_hours
		#   _validate_venue_capacity   — unchanged (venue same, capacity same)
		#   _check_venue_availability  — re-runs against NEW slot
		#   _check_lecturer_availability — re-runs against NEW slot
		self.start_time      = new_start_time
		self.end_time        = new_end_time
		self.postponed       = 1
		self.postpone_reason = reason or None
 
		# Flags consumed by on_update / notifications below
		self.flags.status_action     = True   # not a status change, but bypass the protection
		self.flags.notification_type = "postponement"
		self.flags.postpone_details  = {
			"old_start":  str(old_start)[:16] if old_start else None,
			"old_end":    str(old_end)[:16] if old_end else None,
			"new_start":  str(new_start_time)[:16],
			"new_end":    str(new_end_time)[:16],
			"reason":     reason or "",
		}
 
		self.save()
 
		# Explicit audit log — _log_action wraps the timeline comment
		self._log_action(_(
			"Session postponed from {0}–{1} to {2}–{3}. Reason: {4}"
		).format(
			str(old_start)[:16] if old_start else "—",
			str(old_end)[:16] if old_end else "—",
			str(new_start_time)[:16],
			str(new_end_time)[:16],
			reason or _("(none supplied)"),
		))
 
		# Trigger notifications independently of status-change pathway.
		# on_update only fires _send_status_notification when status changes —
		# we changed times, not status, so we trigger it explicitly here.
		self._send_status_notification()
		self._notify_crs()
 
		return {
			"name":           self.name,
			"old_start_time": str(old_start)[:16] if old_start else None,
			"old_end_time":   str(old_end)[:16] if old_end else None,
			"new_start_time": str(new_start_time)[:16],
			"new_end_time":   str(new_end_time)[:16],
			"status":         self.status,
			"postponed":      True,
		}


@frappe.whitelist(methods=["POST"])
def cancel_emergency_session(name: str):
	"""Cancel a session."""
	return frappe.get_doc("Emergency session", name).cancel_session()


@frappe.whitelist(methods=["POST"])
def complete_emergency_session(name: str):
	"""Mark a CONFIRMED session completed."""
	return frappe.get_doc("Emergency session", name).complete_session()


@frappe.whitelist(methods=["GET"])
def get_user_emergency_sessions(status: str = None, limit: int = 50):
	"""Return emergency sessions visible to the current user.

	Admins see all; Lecturers see their own; CRs/Students see all.
	"""
	user  = frappe.session.user
	roles = frappe.get_roles(user)
	is_admin    = any(r in roles for r in ("Department Admin", "System Manager", "Administrator"))
	is_lecturer = "Lecturer" in roles

	filters = []
	if status:
		filters.append(["status", "=", status])
	if is_admin:
		pass
	elif is_lecturer:
		filters.append(["lecturer", "=", user])

	sessions = frappe.db.get_list(
		"Emergency session",
		filters=filters,
		fields=[
			"name", "title", "venue", "course", "lecturer", "created_by", "role_type",
			"start_time", "end_time", "status", "comment", "expected_students", "required_resources",
		],
		order_by="start_time desc",
		limit=int(limit),
	)

	if not sessions:
		return sessions

	course_map = {r["name"]: r["course_name"] for r in frappe.db.get_all("Course", fields=["name", "course_name"])}
	venue_map  = {r["name"]: r["venue_name"]  for r in frappe.db.get_all("Venue",  fields=["name", "venue_name"])}
	user_map   = {r["name"]: r["full_name"]   for r in frappe.db.get_all("User", filters={"enabled": 1}, fields=["name", "full_name"])}

	for s in sessions:
		s["course_name"]     = course_map.get(s["course"])   or s["course"]
		s["venue_name"]      = venue_map.get(s["venue"])     or s["venue"]
		s["lecturer_name"]   = user_map.get(s["lecturer"])   if s.get("lecturer")   else None
		s["created_by_name"] = user_map.get(s["created_by"]) if s.get("created_by") else s["created_by"]

	return sessions


@frappe.whitelist(methods=["GET"])
def get_upcoming_sessions(limit: int = 10):
	"""Get upcoming PENDING and CONFIRMED emergency sessions"""
	return frappe.db.get_list(
		"Emergency session",
		filters=[
			["start_time", ">=", frappe.utils.now()],
			["status", "in", ["PENDING", "CONFIRMED"]],
		],
		fields=["name", "title", "venue", "course", "start_time", "end_time", "status"],
		order_by="start_time asc",
		limit=limit,
	)


@frappe.whitelist(methods=["GET"])
def check_venue_conflicts(
	venue: str,
	start_time: str,
	end_time: str,
	exclude_session: str = None,
):
	"""Check for venue booking conflicts in the given time window"""
	filters = [
		["venue", "=", venue],
		["status", "not in", ["CANCELLED", "COMPLETED", "EXPIRED"]],
		["start_time", "<", end_time],
		["end_time", ">", start_time],
	]
	if exclude_session:
		filters.append(["name", "!=", exclude_session])

	return frappe.db.get_list(
		"Emergency session",
		filters=filters,
		fields=["name", "title", "start_time", "end_time", "status"],
	)


@frappe.whitelist(methods=["GET"])
def get_week_emergency_sessions(
	week_start: str,
	venue: str = None,
	course: str = None,
):
	"""Return emergency sessions that fall within the given week (Mon–Sun).

	Used by Desk timetable pages to overlay emergency sessions on the
	regular schedule grid and trigger real-time venue status updates.
	"""
	from frappe.utils import getdate, add_days

	week_start_date = getdate(week_start)
	week_end_date   = add_days(week_start_date, 7)

	filters = [
		["status", "not in", ["CANCELLED", "EXPIRED"]],
		["start_time", "<",  str(week_end_date) + " 23:59:59"],
		["end_time",   ">",  str(week_start_date) + " 00:00:00"],
	]
	if venue:
		filters.append(["venue", "=", venue])
	if course:
		filters.append(["course", "=", course])

	return frappe.db.get_all(
		"Emergency session",
		filters=filters,
		fields=["name", "title", "venue", "course", "lecturer",
				"start_time", "end_time", "status", "confirmed_at"],
		order_by="start_time asc",
	)
