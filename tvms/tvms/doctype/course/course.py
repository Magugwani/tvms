# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Course(Document):
    def validate(self):
        self._normalise_code()
        self._validate_year_within_program()
        self._validate_expected_students()

    def _normalise_code(self):
        if self.course_code:
            self.course_code = self.course_code.strip().upper()

    def _validate_year_within_program(self):
        """Year cannot exceed the program's duration."""
        if not self.program or not self.year:
            return
        duration = frappe.db.get_value("Program", self.program, "duration")
        if duration and int(self.year) > int(duration):
            frappe.throw(
                _("Year {0} is invalid for program {1} (max {2} years)").format(
                    self.year, self.program, duration
                )
            )

    def _validate_expected_students(self):
        if self.expected_students is not None and int(self.expected_students) < 0:
            frappe.throw(_("Expected students cannot be negative"))


@frappe.whitelist(methods=["GET", "POST"])
def get_courses_by_program(program: str = None, year: str = None, status: str = "Active"):
    """List courses for dropdowns on Timetable forms — filterable by program and year.

    The Timetable add/edit form uses this when the admin picks a program → year:
    the course dropdown then shows only courses for that exact program-year.
    """
    frappe.has_permission("Course", "read", throw=True)

    filters = {}
    if program:
        filters["program"] = program
    if year:
        filters["year"] = str(year)
    if status:
        filters["status"] = status

    return frappe.db.get_all(
        "Course",
        filters=filters,
        fields=["name", "course_code", "course_name", "program", "year", "credits", "expected_students"],
        order_by="course_code asc",
    )