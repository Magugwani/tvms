# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

"""Guest-accessible web page at /venue/<code>.

Frappe website routing: /venue/LH-01 → tvms/www/venue.py + venue.html
The {venue_code} placeholder is wired up in hooks.py via website_route_rules.
"""

import frappe
from frappe import _


no_cache = 1


def get_context(context):
	"""Render the public venue navigation page.

	Reads the venue code from frappe.form_dict (populated by the
	hooks.py route rule) and calls the public navigation API to
	fetch the safe-to-expose fields.
	"""
	venue_code = frappe.form_dict.get("venue_code") or frappe.form_dict.get("venue")

	# Fallback to URL path parsing if the route rule didn't bind
	if not venue_code:
		path = (frappe.local.request.path or "").rstrip("/")
		if path.startswith("/venue/"):
			venue_code = path[len("/venue/"):].split("/")[0]

	if not venue_code:
		context.venue = None
		context.error_message = _("No venue specified in the URL.")
		return

	from tvms.tvms.doctype.venue.venue import get_public_venue_navigation
	result = get_public_venue_navigation(venue_code)

	if not result or result.get("error"):
		context.venue = None
		context.error_message = result.get("error") if result else _("Could not load venue")
		context.venue_code_searched = venue_code
		return

	context.venue = result
	context.error_message = None

	# Mapbox token for the embedded preview map (token is already
	# domain-restricted in your Mapbox dashboard from the FR-20 setup)
	try:
		settings = frappe.get_single("TVMS Settings")
		context.mapbox_token = settings.get_password(
			"mapbox_token", raise_exception=False
		) or ""
	except Exception:
		context.mapbox_token = ""

	context.metatags = {
		"title":       f"{result['venue_name']} · TVMS",
		"description": f"How to find {result['venue_name']} on campus",
	}