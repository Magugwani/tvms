# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TVMSSettings(Document):
    pass
@frappe.whitelist(methods=["GET"])
def get_mapbox_token():
    """Return Mapbox public token for map pages.
    Safe to expose — public tokens are rate-limited by domain in Mapbox dashboard."""
    settings = frappe.get_single("TVMS Settings")
    return {"token": settings.mapbox_token or ""}