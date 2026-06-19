# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
import io
import base64
import json as _json
from frappe.utils.pdf import get_pdf
import math
from frappe.model.document import Document
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime, nowdate

VENUE_VIEW_ROLES = {
	"System Manager",
	"Administrator",
	"Department Admin",
	"Lecturer",
	"Class Representative (CR)",
	"Student",
}

class Venue(Document):

	# ---------------------------------------------------------------
	# Validation
	# ---------------------------------------------------------------

	def validate(self):
		self._validate_coordinates()
		self._validate_floor_number()
		self._validate_capacity()

	def _validate_coordinates(self):
		"""FR-19: Coordinates must be a valid decimal degree pair when provided."""
		if self.latitude and not (-90 <= float(self.latitude) <= 90):
			frappe.throw(_("Latitude must be between -90 and 90 degrees"))
		if self.longitude and not (-180 <= float(self.longitude) <= 180):
			frappe.throw(_("Longitude must be between -180 and 180 degrees"))
		if (self.latitude and not self.longitude) or (self.longitude and not self.latitude):
			frappe.throw(_("Both Latitude and Longitude must be provided together"))

	def _validate_floor_number(self):
		"""Floor number must be a reasonable value (basements allowed as negatives)."""
		if self.floor_number is not None and not (-10 <= int(self.floor_number) <= 200):
			frappe.throw(_("Floor number seems invalid. Use 0 for ground floor, negative for basement."))

	def _validate_capacity(self):
		if self.capacity is not None and int(self.capacity) < 1:
			frappe.throw(_("Capacity must be at least 1"))


# Average walking speed used for distance → time estimation.
# 1.4 m/s ≈ 5 km/h, the World Health Organization's reference
# value for adult walking pace on flat ground.
	_WALKING_SPEED_MPS = 1.4
	def _haversine_meters(lat1, lon1, lat2, lon2):
		"""Great-circle distance between two GPS points, in metres.
	
		Used for nearby-venue search and walking-time estimates.
		Accurate to within a few metres at campus distances.
		"""
		R = 6371000  # Earth radius in metres
		phi1 = math.radians(float(lat1))
		phi2 = math.radians(float(lat2))
		dphi = math.radians(float(lat2) - float(lat1))
		dlambda = math.radians(float(lon2) - float(lon1))
	
		a = (math.sin(dphi / 2) ** 2
			+ math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
		c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
		return R * c
	
	
	def _format_walking_time(distance_m):
		"""Turn metres into a human-friendly "About 3 min walk" string."""
		seconds = distance_m / _WALKING_SPEED_MPS
		minutes = seconds / 60
	
		if minutes < 1:
			return _("Less than 1 min walk")
		if minutes < 2:
			return _("About 1 min walk")
		return _("About {0} min walk").format(int(round(minutes)))
	# ---------------------------------------------------------------
	# FR-11: Computed helpers
	# ---------------------------------------------------------------

	def get_floor_label(self):
		"""Return human-readable floor label (Ground floor, 1st floor, Basement, etc.)."""
		n = int(self.floor_number or 0)
		if n == 0:
			return "Ground floor"
		if n < 0:
			return f"Basement {abs(n)}" if abs(n) > 1 else "Basement"
		suffixes = {1: "st", 2: "nd", 3: "rd"}
		suffix = suffixes.get(n if n <= 3 else 0, "th")
		return f"{n}{suffix} floor"

	def get_coordinates(self):
		"""Return (latitude, longitude) tuple or None if not set."""
		if self.latitude and self.longitude:
			return (float(self.latitude), float(self.longitude))
		return None

	def has_coordinates(self):
		return bool(self.latitude and self.longitude)

	# ---------------------------------------------------------------
	# FR-60 / FR-61: Status computation (unchanged)
	# ---------------------------------------------------------------

	def compute_status(self, at_time=None):
		"""Derive venue status from live session data at the given moment.

		Returns "IN-USE", "BOOKED", or "FREE". Does NOT write to the database — call
		refresh_status() to persist the result.

		Precedence: active confirmed emergency/timetable → reserved emergency → FREE.
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

		# PENDING sessions reserve the venue until cancelled / expired
		if frappe.db.get_all(
			"Emergency session",
			filters=[
				["venue", "=", self.name],
				["status", "in", ["PENDING", "CONFIRMED"]],
				["end_time", ">", at],
			],
			fields=["name"],
			limit=1,
		):
			return "BOOKED"

		return "FREE"

	def refresh_status(self, at_time=None, trigger=None, reference_type=None,
					   reference_name=None, note=None):
		"""Recompute and persist current_status if it differs from the live value.

		When the status changes a Venue Status History row is appended (FR-14).

		Args:
		    at_time        -- datetime to evaluate at (defaults to now)
		    trigger        -- what caused the change e.g. "Emergency Session Confirmed"
		    reference_type -- DocType that triggered this e.g. "Emergency session"
		    reference_name -- Document name e.g. "EMS-0001"
		    note           -- optional free-text context
		"""
		new_status = self.compute_status(at_time)
		if self.current_status != new_status:
			old_status = self.current_status          # capture BEFORE overwriting
			frappe.db.set_value("Venue", self.name, "current_status", new_status)
			self.current_status = new_status
			# FR-14: log every transition automatically
			frappe.get_doc({
				"doctype": "Venue Status History",
				"venue": self.name,
				"from_status": old_status,
				"to_status": new_status,
				"trigger": trigger or "Scheduler Sync",
				"reference_type": reference_type,
				"reference_name": reference_name,
				"note": note,
			}).insert(ignore_permissions=True)
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
	start_dt = get_datetime(start_time)
	end_dt = get_datetime(end_time)

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
	"""Return the set of venue names with any booking conflict in [start_time, end_time)."""
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
	if not required:
		return True
	available = {r.strip().lower() for r in (venue_resources or "").split(",") if r.strip()}
	return required.issubset(available)


def _format_datetime(value):
	return str(value)[:16] if value else None


def _ensure_venue_view_access():
	user_roles = set(frappe.get_roles())
	if user_roles.intersection(VENUE_VIEW_ROLES):
		return
	if frappe.has_permission("Venue", "read"):
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def _get_venue_booking_windows(venue_name, at_time=None, limit=5):
	at = get_datetime(at_time) if at_time else now_datetime()
	today = at.date()
	now_time = at.strftime("%H:%M:%S")
	limit = int(limit or 5)

	emergency_rows = frappe.db.get_all(
		"Emergency session",
		filters=[
			["venue", "=", venue_name],
			["status", "in", ["PENDING", "CONFIRMED"]],
			["end_time", ">", at],
		],
		fields=["name", "title", "course", "lecturer", "start_time", "end_time", "status"],
		order_by="start_time asc",
		limit=limit,
	)

	timetable_rows = frappe.db.get_all(
		"Timetable",
		filters=[
			["venue", "=", venue_name],
			["status", "!=", "COMPLETED"],
			["date", ">=", today],
		],
		fields=["name", "course", "lecturer", "date", "start_time", "end_time", "status"],
		order_by="date asc, start_time asc",
		limit=limit,
	)
	timetable_rows = [
		row for row in timetable_rows
		if str(row.get("date")) > str(today) or str(row.get("end_time"))[:8] > now_time
	]

	course_names = {
		r["name"]: r["course_name"]
		for r in frappe.db.get_all("Course", fields=["name", "course_name"])
	}
	user_names = {
		r["name"]: r["full_name"]
		for r in frappe.db.get_all("User", filters={"enabled": 1}, fields=["name", "full_name"])
	}

	windows = []
	for row in emergency_rows:
		windows.append({
			"source": "Emergency session",
			"name": row.name,
			"title": row.title,
			"course": row.course,
			"course_name": course_names.get(row.course) or row.course,
			"lecturer": row.lecturer,
			"lecturer_name": user_names.get(row.lecturer) if row.lecturer else None,
			"start_time": _format_datetime(row.start_time),
			"end_time": _format_datetime(row.end_time),
			"status": row.status,
		})

	for row in timetable_rows:
		start_time = str(row.start_time)[:8]
		end_time = str(row.end_time)[:8]
		windows.append({
			"source": "Timetable",
			"name": row.name,
			"title": course_names.get(row.course) or row.course,
			"course": row.course,
			"course_name": course_names.get(row.course) or row.course,
			"lecturer": row.lecturer,
			"lecturer_name": user_names.get(row.lecturer) if row.lecturer else None,
			"start_time": f"{row.date} {start_time[:5]}",
			"end_time": f"{row.date} {end_time[:5]}",
			"status": row.status,
		})

	return sorted(windows, key=lambda row: row["start_time"] or "")[:limit]


# ---------------------------------------------------------------
# FR-11: New — venue full detail API (includes all new fields)
# ---------------------------------------------------------------

@frappe.whitelist(methods=["GET"])
def get_venue_detail(venue: str):
	"""Return full venue details including all FR-11 fields and live status.

	Used by Flutter app and Desk pages for venue info cards and navigation.
	"""
	_ensure_venue_view_access()

	if not frappe.db.exists("Venue", venue):
		frappe.throw(_("Venue not found: {0}").format(venue), frappe.DoesNotExistError)

	doc = frappe.get_doc("Venue", venue)
	live_status = doc.compute_status()

	result = {
		"name":                  doc.name,
		"venue_name":            doc.venue_name,
		"venue_code":            doc.name,
		"venue_type":            doc.venue_type or "",
		"building_name":         doc.building_name or "",
		"floor_number":          doc.floor_number if doc.floor_number is not None else 0,
		"floor_label":           doc.get_floor_label(),
		"location":              doc.location or "",
		"capacity":              doc.capacity or 0,
		"resources":             doc.resources or "",
		"accessibility_features": doc.accessibility_features or "",
		"current_status":        live_status,
		"has_coordinates":       doc.has_coordinates(),
		"latitude":              float(doc.latitude) if doc.latitude else None,
		"longitude":             float(doc.longitude) if doc.longitude else None,
		"map_link":              doc.map_link or "",
		"navigation_notes":      doc.navigation_notes or "",
		"bookings":              _get_venue_booking_windows(venue, limit=5),
	}
	return result

#  ============================================================
# FR-22 — Nearby venues for the public page
# ============================================================
 
@frappe.whitelist(methods=["GET"], allow_guest=True)
def get_nearby_venues(venue: str, radius_m: int = 200, limit: int = 5):
    """Return up to `limit` venues within `radius_m` of the given venue.
 
    Used by the public /venue/<code> page to show "Other places nearby"
    so a visitor can find adjacent buildings without manually searching.
 
    Args:
        venue    -- the centre venue (its lat/lng define the search origin)
        radius_m -- search radius in metres (default 200, max 1000)
        limit    -- max results (default 5, max 20)
 
    Returns: list of dicts with venue_name, building_name, floor_label,
             distance_m, walking_time, latitude, longitude. Sorted by
             distance ascending. The origin venue itself is excluded.
 
    Security note: marked allow_guest because it's consumed by the public
    guest page. The fields returned are the same safe subset that
    get_public_venue_navigation already exposes — no sensitive data.
    """
    if not venue or not frappe.db.exists("Venue", venue):
        return []
 
    radius_m = min(int(radius_m or 200), 1000)
    limit    = min(int(limit or 5), 20)
 
    origin = frappe.db.get_value(
        "Venue", venue,
        ["latitude", "longitude"],
        as_dict=True,
    )
    if not origin or not origin.latitude or not origin.longitude:
        return []
 
    # Bounding-box prefilter — convert radius_m to lat/lng degrees
    # and pull only candidates roughly in the box. This avoids a
    # full-table scan when the venue list is large.
    deg_per_metre_lat = 1.0 / 111000.0
    deg_per_metre_lng = 1.0 / (111000.0 * max(0.01, math.cos(math.radians(origin.latitude))))
 
    lat_delta = radius_m * deg_per_metre_lat
    lng_delta = radius_m * deg_per_metre_lng
 
    candidates = frappe.db.sql("""
        SELECT name, venue_name, venue_type, building_name, floor_number,
               latitude, longitude, capacity, current_status
        FROM   `tabVenue`
        WHERE  name != %(venue)s
        AND    latitude  IS NOT NULL
        AND    longitude IS NOT NULL
        AND    latitude  BETWEEN %(min_lat)s AND %(max_lat)s
        AND    longitude BETWEEN %(min_lng)s AND %(max_lng)s
    """, {
        "venue":   venue,
        "min_lat": origin.latitude  - lat_delta,
        "max_lat": origin.latitude  + lat_delta,
        "min_lng": origin.longitude - lng_delta,
        "max_lng": origin.longitude + lng_delta,
    }, as_dict=True)
 
    results = []
    for c in candidates:
        d = _haversine_meters(
            origin.latitude, origin.longitude,
            c["latitude"], c["longitude"],
        )
        if d > radius_m:
            continue
        results.append({
            "name":          c["name"],
            "venue_name":    c["venue_name"],
            "venue_type":    c.get("venue_type") or "",
            "building_name": c.get("building_name") or "",
            "floor_label":   _floor_label(int(c.get("floor_number") or 0)),
            "distance_m":    round(d),
            "walking_time":  _format_walking_time(d),
            "latitude":      c["latitude"],
            "longitude":     c["longitude"],
        })
 
    results.sort(key=lambda x: x["distance_m"])
    return results[:limit]


# ============================================================
# FR-22 — Walking distance estimate (used by public page hero)
# ============================================================
 
@frappe.whitelist(methods=["GET"], allow_guest=True)
def estimate_walking_distance(from_lat: float, from_lng: float, to_venue: str):
    """Estimate walking distance and time from a point to a venue.
 
    The public page calls this when the visitor allows browser
    geolocation, so they see "About 3 min walk" before tapping
    "Get directions". Removes the surprise of "oh that's actually
    a 15-minute walk across campus."
 
    This is a straight-line haversine estimate — not actual routed
    distance. Adequate for campus-scale navigation. For routed
    distances we'd need Mapbox Directions API (paid per request).
    """
    if not to_venue or not frappe.db.exists("Venue", to_venue):
        return {"error": "Venue not found"}
 
    venue_loc = frappe.db.get_value(
        "Venue", to_venue,
        ["latitude", "longitude"],
        as_dict=True,
    )
    if not venue_loc or not venue_loc.latitude or not venue_loc.longitude:
        return {"error": "Venue has no GPS coordinates"}
 
    try:
        distance = _haversine_meters(
            float(from_lat), float(from_lng),
            venue_loc.latitude, venue_loc.longitude,
        )
    except (ValueError, TypeError):
        return {"error": "Invalid coordinates"}
 
    return {
        "distance_m":   round(distance),
        "walking_time": _format_walking_time(distance),
    }


# ============================================================
# FR-24 — QR codes for door signs
# ============================================================
 
@frappe.whitelist(methods=["GET"])
def get_venue_qr(venue: str, size: int = 256):
    """Return a base64-encoded PNG QR code pointing to /venue/<code>.
 
    Used by admins to print door stickers. Workflow:
      1. Open Venue form → click "Print QR Sign" custom button
      2. Frontend fetches this API
      3. Renders the QR + venue name in a printable layout
      4. Admin prints and sticks on the door
 
    Visitors scan the QR → land at the public /venue/<code> page →
    see building, floor, navigation notes, accessibility info, map.
 
    Args:
        venue -- the Venue docname
        size  -- QR pixel size (box_size × modules), default 256
 
    Returns:
        {qr_png_base64, target_url, venue_name}
    """
    frappe.has_permission("Venue", "read", throw=True)
 
    if not venue or not frappe.db.exists("Venue", venue):
        frappe.throw(_("Venue not found"), frappe.DoesNotExistError)
 
    # Construct the public URL — frappe.utils.get_url respects site_url
    target_url = frappe.utils.get_url(f"/venue/{venue}")
 
    # qrcode library is shipped with Frappe (used by Frappe for its own
    # 2FA QR codes), so this is a zero-dependency import.
    try:
        import qrcode
    except ImportError:
        frappe.throw(_("QR code generation requires the qrcode library"))
 
    qr = qrcode.QRCode(
        version=None,                                       # auto-fit
        error_correction=qrcode.constants.ERROR_CORRECT_M,  # ~15% redundancy
        box_size=max(4, min(int(size) // 32, 32)),
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
 
    img = qr.make_image(fill_color="#2c2c2a", back_color="#ffffff")
 
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
 
    venue_name = frappe.db.get_value("Venue", venue, "venue_name") or venue
 
    return {
        "qr_png_base64": f"data:image/png;base64,{png_b64}",
        "target_url":    target_url,
        "venue_name":    venue_name,
        "venue_code":    venue,
    }
# ---------------------------------------------------------------
# FR-19: New — venues with coordinates only (for map display)
# ---------------------------------------------------------------

@frappe.whitelist(methods=["GET"])
def get_venues_for_map(search: str = None, status: str = None):
	"""Return all venues that have GPS coordinates set.

	Used by the Flutter map screen and the venue navigation page.
	Only returns venues where both latitude and longitude are non-null.
	"""
	_ensure_venue_view_access()

	filters = [
		["latitude", "is", "set"],
		["longitude", "is", "set"],
	]
	or_filters = []
	if search:
		or_filters = [
			["venue_name", "like", f"%{search}%"],
			["building_name", "like", f"%{search}%"],
			["venue_code", "like", f"%{search}%"],
			["location", "like", f"%{search}%"],
		]
	if status:
		filters.append(["current_status", "=", status])

	rows = frappe.db.get_all(
		"Venue",
		filters=filters,
		or_filters=or_filters if or_filters else None,
		fields=[
			"name", "venue_name", "venue_type", "building_name",
			"floor_number", "location", "capacity", "resources",
			"accessibility_features", "current_status",
			"latitude", "longitude", "map_link", "navigation_notes",
		],
		order_by="building_name asc, venue_name asc",
	)

	result = []
	for row in rows:
		if not row.get("latitude") or not row.get("longitude"):
			continue
		result.append({
			**{k: (row[k] or "") for k in row if k not in ("latitude", "longitude", "floor_number")},
			"latitude":     float(row["latitude"]),
			"longitude":    float(row["longitude"]),
			"floor_number": int(row["floor_number"] or 0),
			"floor_label":  _floor_label(int(row["floor_number"] or 0)),
		})

	return result


def _floor_label(n):
	if n == 0:
		return "Ground floor"
	if n < 0:
		return f"Basement {abs(n)}" if abs(n) > 1 else "Basement"
	suffixes = {1: "st", 2: "nd", 3: "rd"}
	suffix = suffixes.get(n if n <= 3 else 0, "th")
	return f"{n}{suffix} floor"

# ───  Public navigation endpoint for guest (no login) ──────
@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_public_venue_navigation(venue: str):
	"""FR-24: Guest-readable subset of venue info for the public
	/venue/<code> page.
 
	Returns only navigation-relevant fields. Live status, current
	bookings, and the booking-window helper are deliberately
	excluded — those are private to logged-in users.
 
	Args:
	    venue -- the Venue docname (e.g. "LH-01"). Case-sensitive.
 
	Returns dict or raises 404 if the venue doesn't exist or has
	no GPS coordinates (we don't surface venues that can't actually
	be navigated to).
	"""
	if not venue or not frappe.db.exists("Venue", venue):
		frappe.local.response.http_status_code = 404
		return {"error": "Venue not found"}
 
	# Read with ignore_permissions because this endpoint is intentionally guest-accessible.
	# We control the field selection here to keep sensitive data out.
	doc = frappe.get_doc("Venue", venue)
 
	# Refuse to surface venues without GPS — these are unreachable
	# via navigation, so the public page can't help.
	if not (doc.latitude and doc.longitude):
		frappe.local.response.http_status_code = 404
		return {"error": "This venue has no navigation data set"}
 
	return {
		"name":              doc.name,
		"venue_name":        doc.venue_name,
		"venue_type":        doc.venue_type or "",
		"building_name":     doc.building_name or "",
		"floor_number":      doc.floor_number if doc.floor_number is not None else 0,
		"floor_label":       doc.get_floor_label(),
		"location":          doc.location or "",
		"capacity":          doc.capacity or 0,
		"resources":         doc.resources or "",
		"accessibility_features": doc.accessibility_features or "",
		"navigation_notes":  doc.navigation_notes or "",
		"latitude":          float(doc.latitude),
		"longitude":         float(doc.longitude),
		# Pre-built directions URL so the public page doesn't have to
		# assemble it client-side (also lets us swap the provider later
		# without changing the page).
		"directions_url":    get_venue_directions_link(doc.name),
	}

# ─── Venue Directions URL helper ───────────────────────
 
def get_venue_directions_link(venue: str, travel_mode: str = "walking") -> str:
	"""Return a Google Maps deep-link URL for walking directions.
 
	Used by:
	- The public venue page (embedded in the "Get directions" button)
	- Timetable entries (when showing "Where is this class?")
	- Emergency session notifications ("Find your new room")
	- Any future Flutter screen needing a directions handoff
 
	On mobile this URL auto-opens the user's preferred maps app
	(Google Maps on Android, Apple Maps on iOS via system fallback)
	with walking directions to the venue's coordinates.
 
	Returns an empty string if the venue has no GPS coordinates.
	"""
	if not venue or not frappe.db.exists("Venue", venue):
		return ""
 
	row = frappe.db.get_value(
		"Venue",
		venue,
		["latitude", "longitude", "venue_name"],
		as_dict=True,
	)
	if not row or not row.get("latitude") or not row.get("longitude"):
		return ""
 
	return (
		f"https://www.google.com/maps/dir/?api=1"
		f"&destination={row['latitude']},{row['longitude']}"
		f"&travelmode={travel_mode}"
	)
 
 
@frappe.whitelist(methods=["GET"])
def get_venue_directions(venue: str, travel_mode: str = "walking"):
	"""Whitelisted wrapper around get_venue_directions_link().
 
	Used by Flutter / Desk JS to fetch the directions URL for a
	specific venue. Returns {'url': '...'} or {'url': null} if no
	coordinates.
	"""
	_ensure_venue_view_access()
	url = get_venue_directions_link(venue, travel_mode)
	return {"url": url or None, "venue": venue, "travel_mode": travel_mode}
 

# ─── QR generator (admin only) ────────
@frappe.whitelist(methods=["GET"])
def generate_venue_qr(venue: str, size: int = 320, return_format: str = "data_url"):
	"""FR-24: Generate a QR code PNG for the public venue page.
 
	The QR encodes the public URL: <site>/venue/<venue-code>
	When scanned, the visitor lands on the guest navigation page
	and can tap "Get directions" to be walked to the room.
 
	Args:
	    venue          -- Venue docname
	    size           -- QR PNG size in pixels (default 320)
	    return_format  -- 'data_url' (default) returns a base64 data URL
	                       suitable for embedding in <img src=...>
	                      'binary' streams the PNG as a downloadable file
 
	Returns:
	    - data_url mode: {'data_url': 'data:image/png;base64,...', 'url': '...', 'venue': '...'}
	    - binary mode:   PNG bytes via frappe.local.response (browser downloads)
	"""
	_ensure_venue_view_access()
 
	if not venue or not frappe.db.exists("Venue", venue):
		frappe.throw(_("Venue not found: {0}").format(venue), frappe.DoesNotExistError)
 
	# Build the public URL — always points to the guest-accessible page
	# regardless of how the admin reached this endpoint
	site_url = frappe.utils.get_url()
	target_url = f"{site_url}/venue/{venue}"
 
	# qrcode is shipped with Frappe (used internally for some integrations).
	# If for some reason it's missing in your environment, install via:
	#   ./env/bin/pip install qrcode pillow
	try:
		import qrcode
	except ImportError:
		frappe.throw(_(
			"The 'qrcode' library is not installed. Run from your bench dir: "
			"./env/bin/pip install qrcode pillow"
		))
 
	# Build the QR — error correction Q so a small dirty/scratched code
	# still scans. Size = box_size * (modules + border).
	qr = qrcode.QRCode(
		version=None,                        # auto-pick smallest fit
		error_correction=qrcode.constants.ERROR_CORRECT_Q,
		box_size=max(int(size) // 35, 4),
		border=2,
	)
	qr.add_data(target_url)
	qr.make(fit=True)
 
	img = qr.make_image(fill_color="black", back_color="white")
 
	import io
	buf = io.BytesIO()
	img.save(buf, format="PNG")
	png_bytes = buf.getvalue()
 
	if return_format == "binary":
		frappe.local.response.filename = f"venue_{venue}_qr.png"
		frappe.local.response.filecontent = png_bytes
		frappe.local.response.type = "binary"
		return
 
	# Default — return a data URL for inline display
	import base64
	b64 = base64.b64encode(png_bytes).decode("ascii")
	return {
		"venue":    venue,
		"url":      target_url,
		"data_url": f"data:image/png;base64,{b64}",
		"size":     int(size),
	}

# ---------------------------------------------------------------
# Existing APIs (unchanged — kept for compatibility)
# ---------------------------------------------------------------

@frappe.whitelist(methods=["GET", "POST"])
def get_all_venues(search: str = None):
	"""Return all venues with full details including live status."""
	_ensure_venue_view_access()

	filters = []
	or_filters = []
	if search:
		or_filters = [
			["venue_name", "like", f"%{search}%"],
			["venue_code", "like", f"%{search}%"],
			["location", "like", f"%{search}%"],
			["building_name", "like", f"%{search}%"],
		]

	rows = frappe.db.get_all(
		"Venue",
		filters=filters,
		or_filters=or_filters if or_filters else None,
		fields=[
			"name", "venue_name", "venue_code", "venue_type",
			"building_name", "floor_number", "location",
			"capacity", "resources", "accessibility_features",
			"current_status", "latitude", "longitude",
		],
		order_by="building_name asc, venue_name asc",
	)
	for row in rows:
		row["bookings"] = _get_venue_booking_windows(row.name, limit=3)
		row["next_booking"] = row["bookings"][0] if row["bookings"] else None
		row["floor_label"] = _floor_label(int(row.get("floor_number") or 0))
		row["has_coordinates"] = bool(row.get("latitude") and row.get("longitude"))
	return rows


@frappe.whitelist(methods=["GET", "POST"])
def get_all_venue_statuses():
	"""Return the stored current_status for every venue (dict keyed by venue name)."""
	_ensure_venue_view_access()

	rows = frappe.db.get_all(
		"Venue",
		fields=["name", "venue_name", "current_status"],
		order_by="name asc",
	)
	return {r["name"]: r["current_status"] or "FREE" for r in rows}


@frappe.whitelist(methods=["GET", "POST"])
def get_venue_status(venue: str, at_time: str = None):
	"""Return the live status of a single venue."""
	_ensure_venue_view_access()

	if not frappe.db.exists("Venue", venue):
		frappe.throw(_("Venue not found: {0}").format(venue), frappe.DoesNotExistError)

	doc = frappe.get_doc("Venue", venue)
	live_status = doc.compute_status(at_time) #live status is computed on the fly, not stored in DB

	return {
		"venue":          venue,
		"venue_name":     doc.venue_name,
		"capacity":       doc.capacity,
		"resources":      doc.resources,
		"building_name":  doc.building_name or "",
		"floor_number":   doc.floor_number if doc.floor_number is not None else 0,
		"floor_label":    doc.get_floor_label(),
		"location":       doc.location or "",
		"current_status": live_status,
		"map_link":	   doc.map_link or "",
		"navigation_notes": doc.navigation_notes or "",
		"live_status":    live_status,
		"stored_status":  doc.current_status,
		"in_sync":        live_status == doc.current_status,
		"has_coordinates": doc.has_coordinates(),
		"latitude":       float(doc.latitude) if doc.latitude else None,
		"longitude":      float(doc.longitude) if doc.longitude else None,
		"bookings":       _get_venue_booking_windows(venue, at_time=at_time),
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_venue_dashboard(search: str = None, status: str = None, date: str = None):
	"""Return venues with status and booking windows for the Venue Dashboard page."""
	_ensure_venue_view_access()

	rows = get_all_venues(search=search)
	if status:
		rows = [row for row in rows if (row.current_status or "FREE") == status]

	if date:
		start = get_datetime(f"{date} 00:00:00")
		end = get_datetime(f"{add_days(date, 1)} 00:00:00")
		for row in rows:
			row["bookings"] = _get_venue_booking_windows(row.name, at_time=start, limit=50)
			row["bookings"] = [
				booking for booking in row["bookings"]
				if booking.get("start_time") and get_datetime(booking["start_time"]) < end
				and booking.get("end_time") and get_datetime(booking["end_time"]) > start
			]
			row["next_booking"] = row["bookings"][0] if row["bookings"] else None

	return rows


@frappe.whitelist(methods=["GET", "POST"])
def get_available_venues(start_time: str, end_time: str, expected_students: int = None):
	"""Return all venues with no conflict in [start_time, end_time)."""
	if not start_time or not end_time:
		frappe.throw(_("start_time and end_time are required"))

	filters = []
	if expected_students:
		filters.append(["capacity", ">=", int(expected_students)])

	all_venues = frappe.db.get_all(
		"Venue",
		filters=filters,
		fields=[
			"name", "venue_name", "venue_type", "building_name",
			"floor_number", "capacity", "resources", "current_status",
			"latitude", "longitude",
		],
		order_by="capacity asc",
	)

	blocked = _blocked_venues(start_time, end_time)
	available = [v for v in all_venues if v["name"] not in blocked]
	for v in available:
		v["floor_label"] = _floor_label(int(v.get("floor_number") or 0))
		v["has_coordinates"] = bool(v.get("latitude") and v.get("longitude"))
	return available


@frappe.whitelist(methods=["GET", "POST"])
def recommend_venue(
	expected_students: int,
	start_time: str,
	end_time: str,
	required_resources: str = None,
):
	"""Suggest best-fit venue: capacity ≥ students, resources match, no conflict, smallest fit first."""
	if not expected_students or not start_time or not end_time:
		frappe.throw(_("expected_students, start_time, and end_time are required"))

	candidates = frappe.db.get_all(
		"Venue",
		filters=[["capacity", ">=", int(expected_students)]],
		fields=[
			"name", "venue_name", "venue_type", "building_name",
			"floor_number", "capacity", "resources",
			"latitude", "longitude",
		],
		order_by="capacity asc",
	)

	if required_resources:
		needed = {r.strip().lower() for r in required_resources.split(",") if r.strip()}
		candidates = [v for v in candidates if _venue_has_resources(v.get("resources"), needed)]

	blocked = _blocked_venues(start_time, end_time)
	available = [v for v in candidates if v["name"] not in blocked]
	for v in available:
		v["floor_label"] = _floor_label(int(v.get("floor_number") or 0))
		v["has_coordinates"] = bool(v.get("latitude") and v.get("longitude"))
	return available

#        get_venue_status_history():
#          - Whitelisted GET API
#          - Returns the history for one venue, newest first
#          - Enriches triggered_by with the user's full name
#          - Used by Flutter app timeline and future analytics
# =============================================================

def log_venue_status_change(
	venue,
	to_status,
	from_status=None,
	trigger=None,
	reference_type=None,
	reference_name=None,
	note=None,
):
	"""Append one row to the Venue Status History child table (FR-14).

	Trigger labels (use exactly these strings for consistency):
	    "Emergency Session Confirmed"
	    "Emergency Session Cancelled"
	    "Emergency Session Completed"
	    "Emergency Session Expired"
	    "Emergency Session Created"
	    "Timetable Session Active"
	    "Timetable Session Ended"
	    "Scheduler Sync"
	    "Manual"

	Args:
	    venue          -- Venue document name (venue_code)
	    to_status      -- new status value: FREE / BOOKED / IN-USE / EXPIRED
	    from_status    -- previous status value (None on first log)
	    trigger        -- cause label from the list above
	    reference_type -- DocType e.g. "Emergency session", "Timetable", "Scheduler"
	    reference_name -- document name e.g. "EMS-0001"
	    note           -- optional free-text context
	"""
	try:
		frappe.db.sql("""
			INSERT INTO `tabVenue Status History`
			    (name, parent, parenttype, parentfield,
			     timestamp, from_status, to_status,
			     `trigger`, triggered_by,
			     reference_type, reference_name, note)
			VALUES
			    (%(name)s, %(parent)s, 'Venue', 'status_history',
			     %(timestamp)s, %(from_status)s, %(to_status)s,
			     %(trigger)s, %(triggered_by)s,
			     %(reference_type)s, %(reference_name)s, %(note)s)
		""", {
			"name":           frappe.generate_hash(length=10),
			"parent":         venue,
			"timestamp":      now_datetime(),
			"from_status":    from_status or "",
			"to_status":      to_status,
			"trigger":        trigger or "Scheduler Sync",
			"triggered_by":   frappe.session.user if frappe.session else "System",
			"reference_type": reference_type or "",
			"reference_name": reference_name or "",
			"note":           note or "",
		})
		frappe.db.commit()
	except Exception:
		# History logging must NEVER break the main session flow
		frappe.logger().warning(
			f"[TVMS] Failed to log status history for venue {venue}",
			exc_info=True,
		)


@frappe.whitelist(methods=["GET"])
def get_venue_status_history(venue: str, limit: int = 50):
	"""Return status change history for a venue, newest first (FR-14).

	Args:
	    venue -- Venue document name (venue_code)
	    limit -- max rows to return (default 50, hard max 500)

	Returns dict:
	    venue   -- venue name
	    total   -- total number of history rows (for pagination)
	    history -- list of rows, each with timestamp, from_status, to_status,
	               trigger, triggered_by, triggered_by_name, reference_type,
	               reference_name, note
	"""
	_ensure_venue_view_access()

	if not frappe.db.exists("Venue", venue):
		frappe.throw(_("Venue not found: {0}").format(venue), frappe.DoesNotExistError)

	limit = min(int(limit or 50), 500)

	rows = frappe.db.sql("""
		SELECT
		    timestamp,
		    from_status,
		    to_status,
		    `trigger`,
		    triggered_by,
		    reference_type,
		    reference_name,
		    note
		FROM `tabVenue Status History`
		WHERE parent     = %(venue)s
		  AND parenttype = 'Venue'
		ORDER BY timestamp DESC
		LIMIT %(limit)s
	""", {"venue": venue, "limit": limit}, as_dict=True)

	# Batch-resolve triggered_by emails → full names (one query, not N)
	user_names = {}
	for row in rows:
		user = row.get("triggered_by")
		if user and user not in user_names:
			user_names[user] = frappe.db.get_value("User", user, "full_name") or user

	for row in rows:
		row["triggered_by_name"] = user_names.get(row.get("triggered_by"), "")
		row["timestamp"] = str(row["timestamp"])[:16] if row.get("timestamp") else ""

	return {
		"venue":   venue,
		"total":   frappe.db.count("Venue Status History", {"parent": venue}),
		"history": rows,
	}

# ============================================================
#  — BULK QR STICKER GENERATOR
# ============================================================
#
 
# Layout specs: (cols, rows, label_width_mm, label_height_mm, qr_size_px)
_BULK_LAYOUTS = {
	"2up": (1, 2, 180, 130, 360),
	"4up": (2, 2,  90, 130, 280),
	"8up": (2, 4,  90,  65, 200),
}
 
 
@frappe.whitelist(methods=["POST"])
def bulk_print_venue_qr(venue_codes, layout: str = "4up"):
	"""Generate a single PDF containing QR stickers for many venues.
 
	Used by admins printing door signs in batches. Workflow:
	  1. Venue list view → multi-select venues → "Bulk QR" action
	  2. Choose layout (2up / 4up / 8up)
	  3. Browser downloads the PDF
	  4. Admin prints on A4 paper, then cuts along guide lines
 
	Args:
	    venue_codes -- list of Venue docnames OR a JSON-encoded list
	                   (Frappe sends arrays as JSON strings via form-data)
	    layout      -- one of "2up", "4up" (default), "8up"
 
	Returns: streams a PDF file via frappe.local.response.
 
	Performance: each QR is ~5-10ms to generate. A 100-venue batch
	takes ~1 second. Larger batches stay reasonable up to ~500.
	"""
	frappe.has_permission("Venue", "read", throw=True)
 
	# Frappe form_dict serialises arrays as JSON strings
	if isinstance(venue_codes, str):
		try:
			venue_codes = _json.loads(venue_codes)
		except (ValueError, TypeError):
			frappe.throw(_("venue_codes must be a list of venue names"))
 
	if not venue_codes:
		frappe.throw(_("Pick at least one venue"))
 
	if layout not in _BULK_LAYOUTS:
		layout = "4up"
 
	cols, rows, label_w_mm, label_h_mm, qr_px = _BULK_LAYOUTS[layout]
	per_page = cols * rows
 
	# Build the per-venue cards in one pass, then chunk by per_page
	try:
		import qrcode
	except ImportError:
		frappe.throw(_("QR code generation requires the qrcode library"))
 
	cards_html = []
	skipped = []
 
	for code in venue_codes:
		if not frappe.db.exists("Venue", code):
			skipped.append(code)
			continue
 
		venue_name = frappe.db.get_value("Venue", code, "venue_name") or code
		building   = frappe.db.get_value("Venue", code, "building_name") or ""
		target_url = frappe.utils.get_url(f"/venue/{code}")
 
		# Generate QR PNG inline as base64
		qr = qrcode.QRCode(
			version=None,
			error_correction=qrcode.constants.ERROR_CORRECT_M,
			box_size=max(3, min(qr_px // 32, 16)),
			border=2,
		)
		qr.add_data(target_url)
		qr.make(fit=True)
		img = qr.make_image(fill_color="#2c2c2a", back_color="#ffffff")
 
		buf = io.BytesIO()
		img.save(buf, format="PNG")
		png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
 
		cards_html.append(_render_card(
			venue_name=venue_name,
			venue_code=code,
			building=building,
			target_url=target_url,
			qr_data=f"data:image/png;base64,{png_b64}",
			layout=layout,
		))
 
	if not cards_html:
		frappe.throw(_("None of the venues you selected exist anymore"))
 
	# Chunk into pages
	pages_html = []
	for i in range(0, len(cards_html), per_page):
		page_cards = cards_html[i:i + per_page]
		# Pad final page so cells stay aligned even when not full
		while len(page_cards) < per_page:
			page_cards.append('<div class="card empty"></div>')
		pages_html.append(_render_page(page_cards, cols, rows, layout))
 
	html_doc = _render_document(
		title=_("Venue QR Stickers"),
		pages_html="".join(pages_html),
		layout=layout,
		cols=cols, rows=rows,
		label_w_mm=label_w_mm, label_h_mm=label_h_mm,
	)
 
	pdf_bytes = get_pdf(html_doc, {
		"page-size":     "A4",
		"margin-top":    "8mm",
		"margin-bottom": "8mm",
		"margin-left":   "8mm",
		"margin-right":  "8mm",
		"encoding":      "UTF-8",
	})
 
	filename = f"venue_qr_stickers_{layout}_{frappe.utils.nowdate()}.pdf"
	frappe.local.response.filename     = filename
	frappe.local.response.filecontent  = pdf_bytes
	frappe.local.response.type         = "pdf"
 
	# Frappe's response object swallows the return — anything we put here
	# only matters if response.type isn't binary. Leave as a sanity log:
	return {"generated": len(cards_html), "skipped": skipped, "layout": layout}
 
 
def _render_card(venue_name, venue_code, building, target_url, qr_data, layout):
	"""HTML for one sticker. Size hints scale via the layout class."""
	name_html  = frappe.utils.escape_html(venue_name)
	code_html  = frappe.utils.escape_html(venue_code)
	bldg_html  = frappe.utils.escape_html(building) if building else ""
	url_html   = frappe.utils.escape_html(target_url)
 
	bldg_block = f'<div class="card-bldg">{bldg_html}</div>' if bldg_html else ""
 
	# 8up gets a tighter layout, no URL printed
	url_block = "" if layout == "8up" else f'<div class="card-url">{url_html}</div>'
 
	return f"""
		<div class="card card-{layout}">
			<div class="card-content">
				<div class="card-name">{name_html}</div>
				<div class="card-code">{code_html}</div>
				{bldg_block}
				<img class="card-qr" src="{qr_data}">
				<div class="card-instruction">{_('Scan with phone camera for directions')}</div>
				{url_block}
			</div>
		</div>
	"""
 
 
def _render_page(cards_html, cols, rows, layout):
	"""Wrap cards in a single page-break-after div."""
	return f"""
		<div class="page page-{layout}">
			{"".join(cards_html)}
		</div>
	"""
 
 
def _render_document(title, pages_html, layout, cols, rows, label_w_mm, label_h_mm):
	"""Full HTML doc with CSS sized for the chosen layout."""
 
	# Per-layout font sizing
	if layout == "2up":
		name_size = "20pt"; code_size = "11pt"; instr_size = "9pt"; url_size = "7pt"; qr_max = "55mm"
	elif layout == "4up":
		name_size = "14pt"; code_size = "9pt"; instr_size = "7.5pt"; url_size = "6pt"; qr_max = "42mm"
	else:  # 8up
		name_size = "11pt"; code_size = "7.5pt"; instr_size = "6.5pt"; url_size = "6pt"; qr_max = "28mm"
 
	return f"""
		<!DOCTYPE html>
		<html>
		<head>
			<meta charset="utf-8">
			<title>{frappe.utils.escape_html(title)}</title>
			<style>
				@page {{
					size: A4;
					margin: 8mm;
				}}
				* {{ box-sizing: border-box; }}
				body {{
					font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
					margin: 0;
					padding: 0;
					color: #2c2c2a;
				}}
				.page {{
					display: grid;
					grid-template-columns: repeat({cols}, 1fr);
					grid-template-rows: repeat({rows}, 1fr);
					gap: 2mm;
					page-break-after: always;
					width: 100%;
					height: 277mm;   /* A4 height - margins */
				}}
				.page:last-child {{
					page-break-after: auto;
				}}
				.card {{
					border: 1.5px dashed #888780;
					border-radius: 4mm;
					padding: 3mm 4mm;
					display: flex;
					flex-direction: column;
					align-items: center;
					justify-content: center;
					text-align: center;
					overflow: hidden;
				}}
				.card.empty {{
					border: 1px dotted #d3d1c7;
					opacity: 0.3;
				}}
				.card-content {{
					display: flex;
					flex-direction: column;
					align-items: center;
					justify-content: center;
					gap: 1.5mm;
					width: 100%;
				}}
				.card-name {{
					font-size: {name_size};
					font-weight: 600;
					line-height: 1.1;
					margin: 0;
				}}
				.card-code {{
					font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
					font-size: {code_size};
					color: #888780;
					letter-spacing: 0.05em;
				}}
				.card-bldg {{
					font-size: {code_size};
					color: #5F5E5A;
					margin-top: -1mm;
				}}
				.card-qr {{
					max-width: {qr_max};
					max-height: {qr_max};
					margin: 1mm 0;
				}}
				.card-instruction {{
					font-size: {instr_size};
					color: #5F5E5A;
					line-height: 1.3;
				}}
				.card-url {{
					font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
					font-size: {url_size};
					color: #888780;
					word-break: break-all;
					max-width: 100%;
					margin-top: 1mm;
				}}
			</style>
		</head>
		<body>
			{pages_html}
		</body>
		</html>
	"""