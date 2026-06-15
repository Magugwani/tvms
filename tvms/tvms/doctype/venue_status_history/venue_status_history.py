# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class VenueStatusHistory(Document):
    # Child doctype — no controller logic needed.
    # All writes are handled by log_venue_status_change() in venue.py.
    pass