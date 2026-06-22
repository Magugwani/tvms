# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Departments(Document):
    def validate(self):
        self._normalise_code()
        self._refresh_programs_offered()

    def _normalise_code(self):
        if self.department_code:
            self.department_code = self.department_code.strip().upper()

    def _refresh_programs_offered(self):
        """Rebuild the programs_offered child table from current Program records.

        The child rows are read-only; they reflect Program docs whose department field
        points at this department. This runs on every save so the table stays in sync.
        """
        self.programs_offered = []
        if not self.name:
            return
        programs = frappe.db.get_all(
            "Program",
            filters={"department": self.name},
            fields=["name", "program_code", "program_name", "level_of_study", "duration", "status"],
            order_by="program_name asc",
        )
        for p in programs:
            self.append("programs_offered", {
                "program": p["name"],
                "program_code": p["program_code"] or "",
                "program_name": p["program_name"] or "",
                "level_of_study": p["level_of_study"] or "",
                "duration": p["duration"] or 0,
                "status": p["status"] or "",
            })


@frappe.whitelist(methods=["GET", "POST"])
def get_all_departments(status: str = None):
    """List departments for dropdowns and the timetable page filters."""
    frappe.has_permission("Departments", "read", throw=True)
    filters = {}
    if status:
        filters["status"] = status
    return frappe.db.get_all(
        "Departments",
        filters=filters,
        fields=["name", "department_code", "department_name", "faculty", "status"],
        order_by="department_name asc",
    )