# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Program(Document):
    def validate(self):
        self._normalise_code()
        self._validate_duration()
        self._inherit_faculty()

    def _normalise_code(self):
        if self.program_code:
            self.program_code = self.program_code.strip().upper()

    def _validate_duration(self):
        if self.duration is not None and not (1 <= int(self.duration) <= 8):
            frappe.throw(_("Duration must be between 1 and 8 years"))

    def _inherit_faculty(self):
        """If faculty is blank, copy it from the linked Department."""
        if not self.faculty and self.department:
            dept_faculty = frappe.db.get_value("Departments", self.department, "faculty")
            if dept_faculty:
                self.faculty = dept_faculty

    def on_update(self):
        self._refresh_department_programs()

    def on_trash(self):
        self._refresh_department_programs()

    def _refresh_department_programs(self):
        """Re-sync the parent Department's programs_offered child table."""
        if not self.department:
            return
        try:
            dept = frappe.get_doc("Departments", self.department)
            dept.save(ignore_permissions=True)
        except Exception:
            frappe.logger().warning(
                f"[TVMS] Could not refresh Department.programs_offered for {self.department}",
                exc_info=True,
            )


@frappe.whitelist(methods=["GET", "POST"])
def get_all_programs(department: str = None, status: str = None):
    """List programs for dropdowns on Timetable, Course, and the public page."""
    frappe.has_permission("Program", "read", throw=True)

    filters = {}
    if department:
        filters["department"] = department
    if status:
        filters["status"] = status

    return frappe.db.get_all(
        "Program",
        filters=filters,
        fields=[
            "name", "program_code", "program_name", "department",
            "faculty", "level_of_study", "duration", "status",
        ],
        order_by="program_name asc",
    )


@frappe.whitelist(methods=["GET", "POST"])
def get_program_years(program: str):
    """Return the list of year labels valid for a program (used by Timetable year_level select).

    A 3-year program returns ["1", "2", "3"]; a 4-year returns ["1","2","3","4"].
    """
    frappe.has_permission("Program", "read", throw=True)

    if not frappe.db.exists("Program", program):
        frappe.throw(_("Program not found: {0}").format(program), frappe.DoesNotExistError)

    duration = frappe.db.get_value("Program", program, "duration") or 3
    return [str(n) for n in range(1, int(duration) + 1)]