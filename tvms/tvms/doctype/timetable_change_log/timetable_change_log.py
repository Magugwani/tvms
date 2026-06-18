# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TimetableChangeLog(Document):
    """Standalone doctype — one row per change action on a Timetable entry.

    All row creation happens via tvms.tvms.doctype.timetable.timetable.log_change()
    which is called from Timetable.on_update / on_trash. Admins should never
    create rows manually — the data is intended to be immutable.
    """
    pass