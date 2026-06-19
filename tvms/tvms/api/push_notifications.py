
# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt
#
# ============================================================
# Push Notifications — FR-41
# ============================================================
#
import json
import time
 
import requests
 
import frappe
from frappe import _
 
 
# ============================================================
# Public entrypoint — used by all other modules
# ============================================================
 
def send_push_to_user(user: str, title: str, body: str, data: dict = None):
	"""Send a push notification to all active devices registered for a user.
 
	Args:
	    user  -- Frappe User name (email)
	    title -- short, displayed on lock screen / notification tray
	    body  -- longer description
	    data  -- optional dict; serialised as JSON and delivered as the
	             FCM `data` payload — the mobile app reads this to
	             route the user to the right screen on tap
 
	Returns: dict with counts of successful/failed sends, or None
	         if push is not configured.
 
	Never raises — failures are logged. The notification flow MUST
	continue even if push delivery fails.
	"""
	settings = _get_settings()
	if not settings.get("enabled"):
		return None
 
	# Find all active device tokens for this user
	tokens = frappe.db.get_all(
		"TVMS Device Token",
		filters={
			"user":   user,
			"active": 1,
		},
		fields=["name", "token", "platform"],
	)
 
	if not tokens:
		return {"sent": 0, "failed": 0, "reason": "no_devices"}
 
	results = {"sent": 0, "failed": 0, "removed": 0}
 
	for device in tokens:
		try:
			ok = _send_fcm_message(
				token=device["token"],
				title=title,
				body=body,
				data=data or {},
				server_key=settings["server_key"],
			)
			if ok:
				results["sent"] += 1
				# Best-effort: record last-used timestamp
				try:
					frappe.db.set_value(
						"TVMS Device Token", device["name"],
						"last_used", frappe.utils.now_datetime(),
					)
				except Exception:
					pass
			else:
				results["failed"] += 1
				# Invalid tokens get marked inactive so we stop trying
				_deactivate_token(device["name"])
				results["removed"] += 1
		except Exception:
			results["failed"] += 1
			frappe.logger().warning(
				f"[TVMS push] FCM send failed for {user} / {device['name']}",
				exc_info=True,
			)
 
	return results
 
 
# ============================================================
# Device registration — called by mobile apps after login
# ============================================================
 
@frappe.whitelist(methods=["POST"])
def register_device_token(token: str, platform: str = "android", device_name: str = None):
	"""Mobile clients call this after logging in to register their FCM token.
 
	One row per (user, token) pair — if the same token registers again,
	we reactivate the existing row rather than create a duplicate.
 
	Args:
	    token       -- the FCM token from the device (or APNs token; FCM
	                   accepts both because it relays to APNs internally)
	    platform    -- "android" / "ios" / "web"
	    device_name -- optional human-readable label for the user to recognise
 
	Returns: the registered token row's name.
	"""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Login required to register a device"), frappe.PermissionError)
 
	if not token or len(token) < 32:
		frappe.throw(_("Invalid device token"))
 
	# Reactivate existing row if this user+token combo already exists
	existing = frappe.db.get_value(
		"TVMS Device Token",
		{"user": user, "token": token},
		"name",
	)
	if existing:
		frappe.db.set_value("TVMS Device Token", existing, {
			"active":      1,
			"platform":    platform,
			"device_name": device_name or "",
			"last_used":   frappe.utils.now_datetime(),
		})
		return {"name": existing, "reused": True}
 
	doc = frappe.get_doc({
		"doctype":     "TVMS Device Token",
		"user":        user,
		"token":       token,
		"platform":    platform,
		"device_name": device_name or "",
		"active":      1,
		"registered_at": frappe.utils.now_datetime(),
		"last_used":   frappe.utils.now_datetime(),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name, "reused": False}
 
 
@frappe.whitelist(methods=["POST"])
def unregister_device_token(token: str):
	"""Called on logout or when the user disables push in their app settings."""
	user = frappe.session.user
 
	name = frappe.db.get_value(
		"TVMS Device Token",
		{"user": user, "token": token},
		"name",
	)
	if name:
		frappe.db.set_value("TVMS Device Token", name, "active", 0)
		frappe.db.commit()
 
	return {"deactivated": bool(name)}
 
 
@frappe.whitelist(methods=["GET"])
def list_my_devices():
	"""Mobile app uses this to show 'my registered devices' in settings."""
	user = frappe.session.user
	return frappe.db.get_all(
		"TVMS Device Token",
		filters={"user": user, "active": 1},
		fields=["name", "platform", "device_name", "registered_at", "last_used"],
		order_by="last_used desc",
	)
 
 
# ============================================================
# Internal — FCM HTTP send
# ============================================================
 
def _send_fcm_message(token: str, title: str, body: str, data: dict, server_key: str) -> bool:
	"""Send one FCM message. Returns True on success, False on invalid token.
 
	Uses the legacy HTTP API for simplicity. FCM has migrated to a newer
	HTTP v1 API that uses OAuth, but the legacy server-key approach still
	works and is dramatically simpler to set up — fine for our scale.
	"""
	url = "https://fcm.googleapis.com/fcm/send"
	headers = {
		"Authorization": f"key={server_key}",
		"Content-Type":  "application/json",
	}
 
	# FCM accepts `notification` (auto-displayed by OS) and `data`
	# (delivered to app for custom handling). We send both so the
	# notification shows up even when the app is killed, AND the app
	# can route the user to the right screen when tapped.
	payload = {
		"to": token,
		"notification": {
			"title": title[:256],
			"body":  _strip_html(body)[:512],
		},
		"data": {k: str(v) for k, v in data.items()},
		"priority":     "high",
		"content_available": True,    # iOS background delivery
	}
 
	try:
		response = requests.post(
			url,
			data=json.dumps(payload),
			headers=headers,
			timeout=10,
		)
	except requests.RequestException:
		return False
 
	if response.status_code != 200:
		return False
 
	try:
		result = response.json()
	except ValueError:
		return False
 
	# FCM returns failure detail in the response body even on 200
	if result.get("failure", 0) > 0:
		errors = [r.get("error") for r in result.get("results", []) if r.get("error")]
		# These specific errors mean the token is dead — deactivate it
		dead = {"NotRegistered", "InvalidRegistration", "MismatchSenderId"}
		if any(e in dead for e in errors):
			return False
 
	return result.get("success", 0) > 0
 
 
def _strip_html(text: str) -> str:
	"""FCM notification body is plain text — strip HTML tags."""
	import re
	if not text:
		return ""
	# Cheap-and-cheerful: replace tags with spaces, collapse whitespace
	stripped = re.sub(r"<[^>]+>", " ", text)
	stripped = re.sub(r"\s+", " ", stripped).strip()
	return stripped
 
 
def _deactivate_token(name: str):
	"""Mark a token as inactive — typically after FCM returns NotRegistered."""
	try:
		frappe.db.set_value("TVMS Device Token", name, "active", 0)
	except Exception:
		pass
 
 
# ============================================================
# Settings cache — read TVMS Settings once per request
# ============================================================
 
_SETTINGS_CACHE = {"value": None, "fetched_at": 0}
_SETTINGS_TTL_SECONDS = 60
 
 
def _get_settings():
	"""Return push config from TVMS Settings, cached for 60 seconds.
 
	Cached because every notification dispatch calls this — re-reading
	TVMS Settings from DB on every push would multiply DB load.
	"""
	now = time.time()
	if _SETTINGS_CACHE["value"] is not None and (now - _SETTINGS_CACHE["fetched_at"]) < _SETTINGS_TTL_SECONDS:
		return _SETTINGS_CACHE["value"]
 
	try:
		settings = frappe.get_single("TVMS Settings")
		server_key = settings.get_password("fcm_server_key", raise_exception=False) or ""
 
		value = {
			"enabled":    bool(getattr(settings, "push_enabled", 0)) and bool(server_key),
			"server_key": server_key,
		}
	except Exception:
		value = {"enabled": False, "server_key": ""}
 
	_SETTINGS_CACHE["value"]      = value
	_SETTINGS_CACHE["fetched_at"] = now
	return value