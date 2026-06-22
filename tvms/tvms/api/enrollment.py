# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt
#
# ============================================================
# tvms/tvms/api/enrollment.py
# ============================================================
#
# CSV-based user enrollment for TVMS. Two import paths:
#   - import_students(): batch import students from registrar CSV
#   - import_lecturers(): batch import lecturers from HR CSV
#
# Plus individual user management:
#   - add_individual_student / add_individual_lecturer
#   - promote_to_cr / demote_from_cr
#   - promote_to_dept_admin / demote_from_dept_admin
#   - enable_user / disable_user
#   - reset_user_password
#
# Plus self-service for non-admin users:
#   - get_my_profile (read-only profile data)
#   - update_my_phone (allowed self-edit)
#   - update_my_photo (allowed self-edit)
#
# DESIGN DECISIONS (decided with user):
#   - One role per CSV row (Student vs Lecturer)
#   - CR and Department Admin roles assigned by admin via UI (not CSV)
#   - Default mode is UPSERT (update existing, add new)
#   - Sync mode is OPTIONAL toggle that also disables users not in CSV
#   - Welcome emails sent on user creation (not update)
#   - Year of study computed from IndexNumber (IT/2023/001 → entry year 2023)

import csv
import io
import re
import secrets
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import now_datetime, getdate, today


# ============================================================
# Constants
# ============================================================

# Roles assigned automatically based on batch type
ROLE_STUDENT          = "Student"
ROLE_LECTURER         = "Lecturer"
ROLE_CR               = "Class Representative (CR)"
ROLE_DEPT_ADMIN       = "Department Admin"

# Default roles every TVMS user gets (so they can access the mobile app)
DEFAULT_ROLES = ["TVMS User"]   # Frappe role we'll create separately

# Expected CSV columns
STUDENT_CSV_COLUMNS = [
    "FirstName", "LastName", "IndexNumber", "Gender",
    "DateOfBirth", "Email", "Phone", "ProgrammeCode", "AcademicYear",
]
LECTURER_CSV_COLUMNS = [
    "FirstName", "LastName", "IDNumber", "Email", "Phone",
    "DepartmentCode", "StaffNumber",
]


# ============================================================
# Permission helpers
# ============================================================

def _require_admin():
    """Only admins can manage enrollments."""
    roles = set(frappe.get_roles())
    if not {"System Manager", "Administrator", "Department Admin"}.intersection(roles):
        frappe.throw(_("Only administrators can manage user enrollment"), frappe.PermissionError)


# ============================================================
# CSV parsing & validation
# ============================================================

def _parse_csv(file_content: bytes, expected_columns: list) -> list:
    """Parse CSV bytes into a list of dicts. Validates column headers.

    Returns list of row dicts. Raises ValidationError if columns are wrong.
    """
    try:
        text = file_content.decode("utf-8-sig")  # Handles Excel BOM
    except UnicodeDecodeError:
        try:
            text = file_content.decode("latin-1")
        except Exception:
            frappe.throw(_("Could not decode CSV. Save as UTF-8 and retry."))

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        frappe.throw(_("CSV file is empty"))

    # Check that all expected columns are present
    actual = set(reader.fieldnames or [])
    expected = set(expected_columns)
    missing = expected - actual
    if missing:
        frappe.throw(
            _("CSV is missing required columns: {0}").format(", ".join(sorted(missing)))
        )

    return rows


def _validate_email(email: str) -> bool:
    """Basic email format check."""
    if not email or "@" not in email:
        return False
    return bool(re.match(r"^[\w.+\-]+@[\w\-]+\.[\w\-.]+$", email.strip()))


def _compute_year_of_study(index_number: str, academic_year: str) -> int:
    """Derive year of study from IndexNumber + AcademicYear.

    Index format: NIT/BIT/2023/2157 → entry year = 2023
                  (4 components: INSTITUTION/PROGRAMME/YEAR/NUMBER)
    Academic year: 2025/2026 → current academic year = 2025

    Year of study = current_academic_year - entry_year + 1

    Falls back to 1 if either field is malformed.
    """
    try:
        # Extract entry year from index — the 4-digit year component.
        # Pattern handles both 3-component (LEGACY/2023/001) and
        # 4-component (NIT/BIT/2023/2157) formats by matching any
        # /YYYY/ within the index.
        match = re.search(r"/(\d{4})/", index_number or "")
        if not match:
            return 1
        entry_year = int(match.group(1))

        # Extract start year from academic_year (first component)
        ay_match = re.search(r"(\d{4})", academic_year or "")
        if not ay_match:
            return 1
        current_year = int(ay_match.group(1))

        year_of_study = current_year - entry_year + 1
        return max(1, min(year_of_study, 6))  # Clamp 1-6
    except Exception:
        return 1


def _year_level_label(year_num: int) -> str:
    """Convert 1..6 → 'First Year (1)', 'Second Year (2)', etc.

    Must match the Select options in Timetable.year_level field.
    """
    labels = {
        1: "First Year (1)",
        2: "Second Year (2)",
        3: "Third Year (3)",
        4: "Fourth Year (4)",
        5: "Fifth Year (5)",
        6: "Sixth Year (6)",
    }
    return labels.get(year_num, "First Year (1)")


# ============================================================
# Generate a temporary password
# ============================================================

def _generate_temp_password() -> str:
    """Generate a 12-char temporary password.

    User receives this in welcome email, must change on first login.
    """
    return secrets.token_urlsafe(9)  # ~12 chars


# ============================================================
# Welcome email
# ============================================================


def _send_welcome_email(user_email: str, full_name: str, temp_password: str,
                        role_label: str):
    """Queue a welcome email to be sent in the background.
 
    Uses frappe.sendmail with delayed=True so the import doesn't
    block waiting for SMTP. Emails get sent by Frappe's email
    queue worker within ~30 seconds.
    """
    try:
        login_url = frappe.utils.get_url("/login")
        institution = frappe.db.get_single_value("TVMS Settings", "company") or "the University"
 
        subject = _("Welcome to {0} — TVMS account ready").format(institution)
        message = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 580px; margin: 0 auto;">
            <h2 style="color: #1976d2;">Welcome, {frappe.utils.escape_html(full_name)}</h2>
 
            <p>Your TVMS (Timetable and Venue Management System) account
            at {frappe.utils.escape_html(institution)} is ready.</p>
 
            <div style="background: #f5f5f5; padding: 16px; border-radius: 8px; margin: 16px 0;">
                <p style="margin: 4px 0;"><strong>Role:</strong> {frappe.utils.escape_html(role_label)}</p>
                <p style="margin: 4px 0;"><strong>Username:</strong> {frappe.utils.escape_html(user_email)}</p>
                <p style="margin: 4px 0;"><strong>Temporary password:</strong>
                    <code style="background: #fff; padding: 2px 6px; border: 1px solid #ddd; border-radius: 4px;">
                        {frappe.utils.escape_html(temp_password)}
                    </code>
                </p>
            </div>
 
            <p style="margin: 24px 0;">
                <a href="{login_url}" style="background: #1976d2; color: #fff; padding: 10px 24px;
                    text-decoration: none; border-radius: 6px; font-weight: 500;">
                    Sign in to TVMS
                </a>
            </p>
 
            <p style="color: #666; font-size: 13px;">
                <strong>Please change your password on first login</strong>
                for security. You can also sign in using your Google
                account if your email matches.
            </p>
 
            <p style="color: #999; font-size: 12px; margin-top: 32px;">
                If you didn't expect this email, please contact your
                department administrator.
            </p>
        </div>
        """
 
        # IMPORTANT: delayed=True queues the email instead of sending
        # synchronously. This is the key change for import performance.
        frappe.sendmail(
            recipients=[user_email],
            subject=subject,
            message=message,
            delayed=True,         # <-- WAS False, NOW True
            now=False,            # do not send immediately, queue it
        )
    except Exception:
        frappe.logger().warning(
            f"[Enrollment] Welcome email queue failed for {user_email}",
            exc_info=True,
        )


# ============================================================
# Core: create/update a single User
# ============================================================

def _upsert_user(
    email: str,
    first_name: str,
    last_name: str,
    role: str,
    phone: str = None,
    program: str = None,
    year_level: str = None,
    department: str = None,
    extra_bio: str = "",
    send_welcome: bool = True,
) -> tuple:
    """Create or update a single Frappe User. Returns (action, user_id).

    action is one of: "CREATED", "UPDATED", "SKIPPED"

    The bio field is used to store program/year/department metadata
    that TVMS code reads (notification engine, jump-to-my-timetable).
    """
    full_name = f"{first_name.strip()} {last_name.strip()}".strip()

    # Build bio string for TVMS internal use
    bio_parts = []
    if program:    bio_parts.append(f"program={program}")
    if year_level: bio_parts.append(f"year_level={year_level}")
    if department: bio_parts.append(f"department={department}")
    if extra_bio:  bio_parts.append(extra_bio)
    bio = " | ".join(bio_parts)

    existing = frappe.db.exists("User", email)

    if existing:
        # Update path
        user_doc = frappe.get_doc("User", email)

        changed = False
        if user_doc.first_name != first_name:
            user_doc.first_name = first_name
            changed = True
        if user_doc.last_name != last_name:
            user_doc.last_name = last_name
            changed = True
        if phone and user_doc.mobile_no != phone:
            user_doc.mobile_no = phone
            changed = True
        if user_doc.bio != bio:
            user_doc.bio = bio
            changed = True

        # Ensure the role is still assigned
        existing_roles = {r.role for r in user_doc.roles}
        if role not in existing_roles:
            user_doc.append("roles", {"role": role})
            changed = True

        if changed:
            user_doc.save(ignore_permissions=True)
            return ("UPDATED", email)
        else:
            return ("SKIPPED", email)

    else:
        # Create path
        temp_password = _generate_temp_password()

        user_doc = frappe.get_doc({
            "doctype":       "User",
            "email":         email,
            "first_name":    first_name,
            "last_name":     last_name,
            "full_name":     full_name,
            "mobile_no":     phone or None,
            "bio":           bio,
            "enabled":       1,
            "send_welcome_email":  0,  # We send our own
            "user_type":     "System User",
            "new_password":  temp_password,
            "force_password_change": 1,
            "roles":         [{"role": role}],
        })
        user_doc.insert(ignore_permissions=True)

        if send_welcome:
            _send_welcome_email(email, full_name, temp_password, role)

        return ("CREATED", email)


# ============================================================
# PREVIEW endpoint — validate CSV without writing
# ============================================================

@frappe.whitelist(methods=["POST"])
def preview_student_csv(csv_content: str):
    """Validate a student CSV and return what would happen on import.

    Returns:
        {
            "total":   123,
            "valid":   118,
            "errors":  [{"row": 5, "field": "Email", "message": "..."}],
            "preview": [first 10 rows as they would be imported],
        }
    """
    _require_admin()

    rows = _parse_csv(csv_content.encode("utf-8"), STUDENT_CSV_COLUMNS)

    errors = []
    valid_count = 0
    preview = []

    for i, row in enumerate(rows, start=2):  # row 2 = first data row (1 is header)
        row_errors = []

        # Validate required fields
        if not row.get("FirstName", "").strip():
            row_errors.append({"row": i, "field": "FirstName", "message": "Required"})
        if not row.get("LastName", "").strip():
            row_errors.append({"row": i, "field": "LastName", "message": "Required"})
        if not _validate_email(row.get("Email", "")):
            row_errors.append({"row": i, "field": "Email", "message": "Invalid email format"})
        if not row.get("IndexNumber", "").strip():
            row_errors.append({"row": i, "field": "IndexNumber", "message": "Required"})

        # Validate ProgrammeCode exists
        prog_code = row.get("ProgrammeCode", "").strip()
        if prog_code and not frappe.db.exists("Program", prog_code):
            row_errors.append({
                "row": i, "field": "ProgrammeCode",
                "message": f"Program '{prog_code}' not found in system",
            })

        if row_errors:
            errors.extend(row_errors)
        else:
            valid_count += 1

            if len(preview) < 10:
                # Compute year of study for preview
                year_num = _compute_year_of_study(
                    row.get("IndexNumber", ""), row.get("AcademicYear", "")
                )
                preview.append({
                    "row":         i,
                    "email":       row["Email"].strip(),
                    "full_name":   f"{row['FirstName'].strip()} {row['LastName'].strip()}",
                    "index":       row["IndexNumber"].strip(),
                    "program":     prog_code,
                    "year_level":  _year_level_label(year_num),
                    "exists":      frappe.db.exists("User", row["Email"].strip()) and "UPDATE" or "CREATE",
                })

    return {
        "total":   len(rows),
        "valid":   valid_count,
        "errors":  errors[:50],  # cap errors shown
        "error_count": len(errors),
        "preview": preview,
    }
#  preview_lecturer_csv() is similar to preview_student_csv() but for lecturers.
@frappe.whitelist(methods=["GET", "POST"])
def preview_lecturer_csv(csv_content: str):
    """Validate a lecturer CSV and return what would happen on import.
 
    Returns:
        {
            "total":   25,
            "valid":   23,
            "errors":  [{"row": 5, "field": "Email", "message": "..."}],
            "preview": [first 10 rows as they would be imported],
        }
    """
    _require_admin()
 
    rows = _parse_csv(csv_content.encode("utf-8"), LECTURER_CSV_COLUMNS)
 
    errors = []
    valid_count = 0
    preview = []
 
    for i, row in enumerate(rows, start=2):
        row_errors = []
 
        if not row.get("FirstName", "").strip():
            row_errors.append({"row": i, "field": "FirstName", "message": "Required"})
        if not row.get("LastName", "").strip():
            row_errors.append({"row": i, "field": "LastName", "message": "Required"})
        if not _validate_email(row.get("Email", "")):
            row_errors.append({"row": i, "field": "Email", "message": "Invalid email format"})
 
        # Validate DepartmentCode exists (optional field but checked when present)
        dept_code = row.get("DepartmentCode", "").strip()
        if dept_code and not frappe.db.exists("Departments", dept_code):
            row_errors.append({
                "row": i, "field": "DepartmentCode",
                "message": f"Department '{dept_code}' not found in system",
            })
 
        if row_errors:
            errors.extend(row_errors)
        else:
            valid_count += 1
 
            if len(preview) < 10:
                preview.append({
                    "row":         i,
                    "email":       row["Email"].strip(),
                    "full_name":   f"{row['FirstName'].strip()} {row['LastName'].strip()}",
                    "index":       row.get("IDNumber", "").strip(),  # IDNumber shown as "index"
                    "program":     dept_code,                          # Department shown as "program" col
                    "year_level":  row.get("StaffNumber", "").strip(),  # StaffNumber shown as "year"
                    "exists":      "UPDATE" if frappe.db.exists("User", row["Email"].strip()) else "CREATE",
                })
 
    return {
        "total":       len(rows),
        "valid":       valid_count,
        "errors":      errors[:50],
        "error_count": len(errors),
        "preview":     preview,
    }

# ============================================================
# IMPORT — actually create users
# ============================================================

@frappe.whitelist(methods=["POST"])
def import_students(csv_content: str, sync_mode: int = 0,
                    send_welcome_emails: int = 1):
    """Import a batch of students from CSV.

    Creates a TVMS Enrollment Batch row to track this import.
    Returns the batch name + summary stats.

    Args:
        csv_content -- raw CSV text
        sync_mode -- if 1, disables students NOT in this CSV
        send_welcome_emails -- if 1, sends welcome email to new users
    """
    _require_admin()

    sync_mode = bool(int(sync_mode or 0))
    send_welcome = bool(int(send_welcome_emails or 0))

    # Create the batch audit row
    batch = frappe.get_doc({
        "doctype":             "TVMS Enrollment Batch",
        "batch_type":          "STUDENT",
        "imported_at":         now_datetime(),
        "imported_by":         frappe.session.user,
        "status":              "IN PROGRESS",
        "sync_mode":           1 if sync_mode else 0,
        "send_welcome_emails": 1 if send_welcome else 0,
    })
    batch.insert(ignore_permissions=True)
    frappe.db.commit()

    # Parse CSV
    try:
        rows = _parse_csv(csv_content.encode("utf-8"), STUDENT_CSV_COLUMNS)
    except Exception as e:
        batch.status = "FAILED"
        batch.summary = f"Parse failed: {str(e)}"
        batch.save(ignore_permissions=True)
        frappe.db.commit()
        raise

    batch.total_rows = len(rows)
    batch.save(ignore_permissions=True)

    # Track emails seen (for sync mode)
    emails_in_csv = set()

    created = 0
    updated = 0
    skipped = 0
    failed = 0
    error_log = []

    for i, row in enumerate(rows, start=2):
        try:
            email = row.get("Email", "").strip().lower()
            if not _validate_email(email):
                raise ValueError(f"Invalid email: {email}")

            first_name = row.get("FirstName", "").strip()
            last_name = row.get("LastName", "").strip()
            if not first_name or not last_name:
                raise ValueError("FirstName and LastName are required")

            index = row.get("IndexNumber", "").strip()
            if not index:
                raise ValueError("IndexNumber is required")

            program = row.get("ProgrammeCode", "").strip() or None
            if program and not frappe.db.exists("Program", program):
                raise ValueError(f"Program '{program}' not found")

            year_num = _compute_year_of_study(
                index, row.get("AcademicYear", "")
            )
            year_level = _year_level_label(year_num)

            extra_bio = f"index={index}"

            action, user_id = _upsert_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=ROLE_STUDENT,
                phone=row.get("Phone", "").strip() or None,
                program=program,
                year_level=year_level,
                extra_bio=extra_bio,
                send_welcome=send_welcome,
            )

            emails_in_csv.add(email)

            if action == "CREATED":   created += 1
            elif action == "UPDATED": updated += 1
            else:                     skipped += 1

        except Exception as e:
            failed += 1
            error_log.append(f"Row {i}: {str(e)}")
            frappe.logger().warning(
                f"[Enrollment] Row {i} failed: {str(e)}",
                exc_info=True,
            )

    # Sync mode: disable students not in this CSV
    users_disabled = 0
    if sync_mode:
        existing_students = frappe.db.sql("""
            SELECT u.name FROM `tabUser` u
            INNER JOIN `tabHas Role` hr ON hr.parent = u.name
            WHERE hr.role = %s AND u.enabled = 1
        """, [ROLE_STUDENT], as_dict=True)

        for s in existing_students:
            if s["name"] not in emails_in_csv:
                try:
                    frappe.db.set_value("User", s["name"], "enabled", 0)
                    users_disabled += 1
                except Exception as e:
                    error_log.append(f"Disable {s['name']}: {str(e)}")

    # Finalize batch
    batch.reload()
    batch.rows_created = created
    batch.rows_updated = updated
    batch.rows_skipped = skipped
    batch.rows_failed = failed
    batch.users_disabled = users_disabled

    if failed == 0:
        batch.status = "COMPLETED"
    elif created + updated > 0:
        batch.status = "PARTIAL"
    else:
        batch.status = "FAILED"

    batch.summary = (
        f"Created {created} new users, updated {updated} existing, "
        f"skipped {skipped} (no changes), failed {failed}."
        + (f" Disabled {users_disabled} graduates." if sync_mode else "")
    )
    if error_log:
        batch.error_log = "\n".join(error_log[:100])  # Cap log size

    batch.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "batch_name":     batch.name,
        "status":         batch.status,
        "total":          len(rows),
        "created":        created,
        "updated":        updated,
        "skipped":        skipped,
        "failed":         failed,
        "users_disabled": users_disabled,
        "summary":        batch.summary,
        "error_count":    len(error_log),
    }


@frappe.whitelist(methods=["POST"])
def import_lecturers(csv_content: str, sync_mode: int = 0,
                     send_welcome_emails: int = 1):
    """Import lecturers from CSV. Similar pattern to import_students."""
    _require_admin()

    sync_mode = bool(int(sync_mode or 0))
    send_welcome = bool(int(send_welcome_emails or 0))

    batch = frappe.get_doc({
        "doctype":             "TVMS Enrollment Batch",
        "batch_type":          "LECTURER",
        "imported_at":         now_datetime(),
        "imported_by":         frappe.session.user,
        "status":              "IN PROGRESS",
        "sync_mode":           1 if sync_mode else 0,
        "send_welcome_emails": 1 if send_welcome else 0,
    })
    batch.insert(ignore_permissions=True)
    frappe.db.commit()

    try:
        rows = _parse_csv(csv_content.encode("utf-8"), LECTURER_CSV_COLUMNS)
    except Exception as e:
        batch.status = "FAILED"
        batch.summary = f"Parse failed: {str(e)}"
        batch.save(ignore_permissions=True)
        frappe.db.commit()
        raise

    batch.total_rows = len(rows)
    batch.save(ignore_permissions=True)

    emails_in_csv = set()
    created = updated = skipped = failed = 0
    error_log = []

    for i, row in enumerate(rows, start=2):
        try:
            email = row.get("Email", "").strip().lower()
            if not _validate_email(email):
                raise ValueError(f"Invalid email: {email}")

            first_name = row.get("FirstName", "").strip()
            last_name = row.get("LastName", "").strip()
            if not first_name or not last_name:
                raise ValueError("FirstName and LastName are required")

            dept = row.get("DepartmentCode", "").strip() or None
            if dept and not frappe.db.exists("Departments", dept):
                raise ValueError(f"Department '{dept}' not found")

            staff_no = row.get("StaffNumber", "").strip()
            id_no = row.get("IDNumber", "").strip()
            extra_bio_parts = []
            if id_no:    extra_bio_parts.append(f"id_number={id_no}")
            if staff_no: extra_bio_parts.append(f"staff={staff_no}")
            extra_bio = " | ".join(extra_bio_parts)

            action, _ = _upsert_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=ROLE_LECTURER,
                phone=row.get("Phone", "").strip() or None,
                department=dept,
                extra_bio=extra_bio,
                send_welcome=send_welcome,
            )
            emails_in_csv.add(email)

            if action == "CREATED":   created += 1
            elif action == "UPDATED": updated += 1
            else:                     skipped += 1

        except Exception as e:
            failed += 1
            error_log.append(f"Row {i}: {str(e)}")

    users_disabled = 0
    if sync_mode:
        existing = frappe.db.sql("""
            SELECT u.name FROM `tabUser` u
            INNER JOIN `tabHas Role` hr ON hr.parent = u.name
            WHERE hr.role = %s AND u.enabled = 1
        """, [ROLE_LECTURER], as_dict=True)

        for l in existing:
            if l["name"] not in emails_in_csv:
                try:
                    frappe.db.set_value("User", l["name"], "enabled", 0)
                    users_disabled += 1
                except Exception as e:
                    error_log.append(f"Disable {l['name']}: {str(e)}")

    batch.reload()
    batch.rows_created = created
    batch.rows_updated = updated
    batch.rows_skipped = skipped
    batch.rows_failed = failed
    batch.users_disabled = users_disabled
    batch.status = "COMPLETED" if failed == 0 else ("PARTIAL" if created + updated > 0 else "FAILED")
    batch.summary = (
        f"Created {created} new lecturers, updated {updated}, "
        f"skipped {skipped}, failed {failed}."
        + (f" Disabled {users_disabled} departed staff." if sync_mode else "")
    )
    if error_log:
        batch.error_log = "\n".join(error_log[:100])

    batch.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "batch_name":     batch.name,
        "status":         batch.status,
        "total":          len(rows),
        "created":        created,
        "updated":        updated,
        "skipped":        skipped,
        "failed":         failed,
        "users_disabled": users_disabled,
        "summary":        batch.summary,
        "error_count":    len(error_log),
    }


# ============================================================
# Individual user management (admin tools)
# ============================================================

@frappe.whitelist(methods=["POST"])
def add_individual_student(
    email: str, first_name: str, last_name: str,
    index_number: str, program: str, academic_year: str,
    phone: str = None, send_welcome: int = 1,
):
    """Admin-only: add a single student for mid-semester additions."""
    _require_admin()

    if frappe.db.exists("User", email):
        frappe.throw(_("User {0} already exists").format(email))

    year_num = _compute_year_of_study(index_number, academic_year)
    year_level = _year_level_label(year_num)

    action, _ = _upsert_user(
        email=email.strip().lower(),
        first_name=first_name, last_name=last_name,
        role=ROLE_STUDENT,
        phone=phone, program=program, year_level=year_level,
        extra_bio=f"index={index_number}",
        send_welcome=bool(int(send_welcome or 0)),
    )
    frappe.db.commit()
    return {"action": action, "email": email}


@frappe.whitelist(methods=["POST"])
def add_individual_lecturer(
    email: str, first_name: str, last_name: str,
    id_number: str = None, department: str = None, phone: str = None,
    staff_number: str = None, send_welcome: int = 1,
):
    """Admin-only: add a single lecturer."""
    _require_admin()

    if frappe.db.exists("User", email):
        frappe.throw(_("User {0} already exists").format(email))

    extra_bio_parts = []
    if id_number:    extra_bio_parts.append(f"id_number={id_number}")
    if staff_number: extra_bio_parts.append(f"staff={staff_number}")
    extra_bio = " | ".join(extra_bio_parts)

    action, _ = _upsert_user(
        email=email.strip().lower(),
        first_name=first_name, last_name=last_name,
        role=ROLE_LECTURER,
        phone=phone, department=department,
        extra_bio=extra_bio,
        send_welcome=bool(int(send_welcome or 0)),
    )
    frappe.db.commit()
    return {"action": action, "email": email}


@frappe.whitelist(methods=["POST"])
def promote_to_cr(email: str):
    """Admin-only: add CR role to an existing Student."""
    _require_admin()
    return _add_role_to_user(email, ROLE_CR, "Student")


@frappe.whitelist(methods=["POST"])
def demote_from_cr(email: str):
    """Admin-only: remove CR role."""
    _require_admin()
    return _remove_role_from_user(email, ROLE_CR)


@frappe.whitelist(methods=["POST"])
def promote_to_dept_admin(email: str):
    """Admin-only: add Department Admin role to a Lecturer."""
    _require_admin()
    return _add_role_to_user(email, ROLE_DEPT_ADMIN, "Lecturer")


@frappe.whitelist(methods=["POST"])
def demote_from_dept_admin(email: str):
    """Admin-only: remove Department Admin role."""
    _require_admin()
    return _remove_role_from_user(email, ROLE_DEPT_ADMIN)


def _add_role_to_user(email: str, role: str, required_base_role: str = None) -> dict:
    """Helper: add a role to a user, checking they have the required base role."""
    if not frappe.db.exists("User", email):
        frappe.throw(_("User {0} not found").format(email))

    user = frappe.get_doc("User", email)
    existing_roles = {r.role for r in user.roles}

    if required_base_role and required_base_role not in existing_roles:
        frappe.throw(_("User must have role {0} first").format(required_base_role))

    if role in existing_roles:
        return {"action": "ALREADY_ASSIGNED", "email": email}

    user.append("roles", {"role": role})
    user.save(ignore_permissions=True)
    frappe.db.commit()
    return {"action": "ROLE_ADDED", "email": email, "role": role}


def _remove_role_from_user(email: str, role: str) -> dict:
    """Helper: remove a role from a user."""
    if not frappe.db.exists("User", email):
        frappe.throw(_("User {0} not found").format(email))

    user = frappe.get_doc("User", email)
    user.roles = [r for r in user.roles if r.role != role]
    user.save(ignore_permissions=True)
    frappe.db.commit()
    return {"action": "ROLE_REMOVED", "email": email, "role": role}


@frappe.whitelist(methods=["POST"])
def enable_user(email: str):
    """Admin-only: enable a user account."""
    _require_admin()
    if not frappe.db.exists("User", email):
        frappe.throw(_("User not found"))
    frappe.db.set_value("User", email, "enabled", 1)
    frappe.db.commit()
    return {"action": "ENABLED", "email": email}


@frappe.whitelist(methods=["POST"])
def disable_user(email: str):
    """Admin-only: disable a user account."""
    _require_admin()
    if not frappe.db.exists("User", email):
        frappe.throw(_("User not found"))
    frappe.db.set_value("User", email, "enabled", 0)
    frappe.db.commit()
    return {"action": "DISABLED", "email": email}


@frappe.whitelist(methods=["POST"])
def reset_user_password(email: str, send_email: int = 1):
    """Admin-only: reset a user's password and optionally email them.

    Generates a new temporary password, forces password change on
    next login, optionally emails the new credentials.
    """
    _require_admin()
    if not frappe.db.exists("User", email):
        frappe.throw(_("User not found"))

    new_password = _generate_temp_password()
    user_doc = frappe.get_doc("User", email)
    user_doc.new_password = new_password
    user_doc.force_password_change = 1
    user_doc.save(ignore_permissions=True)
    frappe.db.commit()

    if bool(int(send_email or 0)):
        # Find their primary role for the email
        roles = [r.role for r in user_doc.roles]
        role_label = next(
            (r for r in roles if r in [ROLE_STUDENT, ROLE_LECTURER, ROLE_CR, ROLE_DEPT_ADMIN]),
            "TVMS User",
        )
        _send_welcome_email(
            user_email=email,
            full_name=user_doc.full_name or email,
            temp_password=new_password,
            role_label=role_label,
        )

    return {"action": "PASSWORD_RESET", "email": email, "email_sent": bool(int(send_email or 0))}


@frappe.whitelist(methods=["GET", "POST"])
def list_users(role: str = None, program: str = None, year_level: str = None,
               department: str = None, enabled: int = None, search: str = None,
               limit: int = 100):
    """List TVMS users with filters. Admin-only."""
    _require_admin()

    limit = min(int(limit or 100), 500)

    # Build filters
    filters = []
    if enabled is not None and enabled != "":
        filters.append(["enabled", "=", int(enabled)])
    if search:
        filters.append(["full_name", "like", f"%{search}%"])

    # Get users with their roles
    users = frappe.db.sql(f"""
        SELECT DISTINCT u.name, u.full_name, u.email, u.mobile_no,
               u.enabled, u.bio, u.last_login, u.creation
        FROM   `tabUser` u
        INNER JOIN `tabHas Role` hr ON hr.parent = u.name
        WHERE  hr.role IN ('Student', 'Lecturer', 'Class Representative (CR)', 'Department Admin')
        {("AND hr.role = %(role)s") if role else ""}
        {("AND u.enabled = %(enabled)s") if enabled is not None and enabled != "" else ""}
        {("AND (u.full_name LIKE %(search)s OR u.email LIKE %(search)s)") if search else ""}
        ORDER BY u.full_name ASC
        LIMIT {limit}
    """, {
        "role":     role,
        "enabled":  enabled,
        "search":   f"%{search}%" if search else None,
    }, as_dict=True)

    # Enrich with roles
    user_emails = [u["name"] for u in users]
    if user_emails:
        roles_rows = frappe.db.sql("""
            SELECT parent, role FROM `tabHas Role`
            WHERE parent IN %(emails)s
            AND role IN ('Student', 'Lecturer', 'Class Representative (CR)', 'Department Admin')
        """, {"emails": tuple(user_emails)}, as_dict=True)

        roles_map = {}
        for r in roles_rows:
            roles_map.setdefault(r["parent"], []).append(r["role"])

        for u in users:
            u["roles"] = roles_map.get(u["name"], [])
            # Parse bio for program/year/department display
            u["program"]    = _parse_bio_field(u.get("bio"), "program")
            u["year_level"] = _parse_bio_field(u.get("bio"), "year_level")
            u["department"] = _parse_bio_field(u.get("bio"), "department")

    # Post-filter by program/year/department if specified
    if program:
        users = [u for u in users if u.get("program") == program]
    if year_level:
        users = [u for u in users if u.get("year_level") == year_level]
    if department:
        users = [u for u in users if u.get("department") == department]

    return users


def _parse_bio_field(bio: str, field: str) -> str:
    """Extract a value from the bio string format 'program=X | year_level=Y'."""
    if not bio:
        return ""
    match = re.search(rf"{field}\s*=\s*([^|]+)", bio)
    return match.group(1).strip() if match else ""


# ============================================================
# Self-service (any logged-in user)
# ============================================================

@frappe.whitelist(methods=["GET", "POST"])
def get_my_profile():
    """Return the current user's profile (read-only fields included)."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Not logged in"), frappe.AuthenticationError)

    user_doc = frappe.get_doc("User", user)

    return {
        "email":       user_doc.email,
        "full_name":   user_doc.full_name,
        "first_name":  user_doc.first_name,
        "last_name":   user_doc.last_name,
        "phone":       user_doc.mobile_no or "",
        "user_image":  user_doc.user_image or None,
        "roles":       [r.role for r in user_doc.roles],
        "program":     _parse_bio_field(user_doc.bio, "program"),
        "year_level":  _parse_bio_field(user_doc.bio, "year_level"),
        "department":  _parse_bio_field(user_doc.bio, "department"),
        "language":    user_doc.language or "en",
        "time_zone":   user_doc.time_zone or "Africa/Dar_es_Salaam",
    }


@frappe.whitelist(methods=["POST"])
def update_my_phone(phone: str):
    """User updates their own phone number."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Not logged in"), frappe.AuthenticationError)

    if phone and not re.match(r"^[\d\s+\-()]+$", phone):
        frappe.throw(_("Invalid phone number format"))

    frappe.db.set_value("User", user, "mobile_no", phone or None)
    frappe.db.commit()
    return {"updated": True}