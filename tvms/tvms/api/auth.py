# Copyright (c) 2026, Magugwani and contributors
# For license information, please see license.txt
#
# ============================================================
# Mobile-app authentication endpoints
# ============================================================

# DESIGN: We use Frappe's native api_key/api_secret token system
# instead of building JWT. Reasons:
#
#   - Same security model as Frappe's own mobile clients and ERPNext
#   - Zero external dependencies (no PyJWT, no signing keys)
#   - Per-user revocable tokens — admin can disable a user and every
#     active session dies immediately
#   - Frappe validates the token on every request internally
#
# FLOW for Flutter app:
#
#   1. App POSTs username + password to mobile_login
#   2. Server validates with frappe.auth.LoginManager (same path as
#      the web login — gets rate limiting, password attempt tracking,
#      account lockout, etc., for free)
#   3. Server generates (or rotates) api_key + api_secret pair on the
#      User doc
#   4. Server returns the pair + user profile JSON
#   5. App stores api_key:api_secret in secure storage (Keychain on
#      iOS, Keystore on Android)
#   6. App sends `Authorization: token <key>:<secret>` on every
#      subsequent request — Frappe validates natively
#
# To revoke: admin opens the User, clicks "Generate Keys" again, and
# the old secret is overwritten. The app gets 401 on next call and
# re-prompts for password.

import frappe
from frappe import _
from frappe.auth import LoginManager
from frappe.utils.password import update_password
from frappe.utils import now_datetime


# ============================================================
# Constants
# ============================================================

# Roles a mobile user is expected to have. Login is rejected for
# users without ANY of these — e.g. a System Manager who doesn't
# also have a TVMS role can't log into the app (they have Desk).
MOBILE_ROLES = {
    "Lecturer",
    "Class Representative (CR)",
    "Student",
    "Department Admin",
}


# ============================================================
# Helpers
# ============================================================

def _ensure_api_credentials(user: str) -> tuple:
    """Get or generate the (api_key, api_secret) pair for a user.

    Frappe stores api_secret hashed in the password store, so we can't
    read an existing secret. We always rotate the secret on login —
    this means the previous logged-in device automatically loses access
    when a new login happens, which is exactly what you want for
    mobile sessions.

    Returns: (api_key, api_secret) — both strings
    """
    user_doc = frappe.get_doc("User", user)

    # api_key is plain text and reusable across logins
    if not user_doc.api_key:
        user_doc.api_key = frappe.generate_hash(length=15)

    # api_secret is rotated on every login
    api_secret = frappe.generate_hash(length=15)
    user_doc.api_secret = api_secret

    # Save the key (Frappe automatically hashes api_secret into the
    # password store when this attribute is set)
    user_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return user_doc.api_key, api_secret


def _user_profile(user: str) -> dict:
    """Build the user profile object returned after login.

    Includes the role-derived `primary_role` field that the Flutter
    app uses to choose its starting screen and navigation.
    """
    user_doc = frappe.get_doc("User", user)
    roles = [r.role for r in user_doc.roles]

    # Determine primary role for UX routing — order matters
    if "System Manager" in roles or "Administrator" in roles or "Department Admin" in roles:
        primary_role = "admin"
    elif "Lecturer" in roles:
        primary_role = "lecturer"
    elif "Class Representative (CR)" in roles:
        primary_role = "cr"
    elif "Student" in roles:
        primary_role = "student"
    else:
        primary_role = "viewer"

    return {
        "user":         user_doc.name,
        "full_name":    user_doc.full_name or user_doc.name,
        "email":        user_doc.email,
        "user_image":   user_doc.user_image or None,
        "roles":        roles,
        "primary_role": primary_role,
        "enabled":      user_doc.enabled,
        "language":     user_doc.language or "en",
        "time_zone":    user_doc.time_zone or "Africa/Dar_es_Salaam",
    }


def _validate_mobile_user(user: str):
    """Reject users without any mobile role.

    Prevents System Manager-only accounts from creating mobile sessions
    — they should use Desk, not the app.
    """
    roles = set(frappe.get_roles(user))
    if not (MOBILE_ROLES & roles):
        frappe.throw(
            _("This account does not have access to the mobile app. "
              "Please contact your administrator."),
            frappe.PermissionError,
        )


# ============================================================
# Public endpoints
# ============================================================

@frappe.whitelist(allow_guest=True, methods=["POST"])
def mobile_login(usr: str, pwd: str):
    """Mobile app login — exchange username + password for an API token.

    Args:
        usr -- username (email or system username) — Frappe convention
        pwd -- password — Frappe convention

    Returns:
        {
            "api_key":      "xxxxxxxxxxxxxxx",
            "api_secret":   "yyyyyyyyyyyyyyy",
            "user":         { ...profile dict... },
            "auth_header":  "token xxxxxxxxxxxxxxx:yyyyyyyyyyyyyyy"
        }

    The auth_header field is a convenience — the Flutter app stores it
    verbatim and sends it as the Authorization header on every request.

    Raises:
        AuthenticationError -- wrong password / account disabled
        PermissionError     -- user has no mobile role
    """
    if not usr or not pwd:
        frappe.throw(_("Both username and password are required"))

    # Use Frappe's LoginManager — this gives us:
    #   - Password attempt rate limiting
    #   - Account lockout after N failed attempts
    #   - User enabled/disabled checking
    #   - Login attempt audit trail
    #   - Same code path as the standard web login
    lm = LoginManager()
    lm.authenticate(user=usr, pwd=pwd)
    lm.post_login()

    user = lm.user

    # Reject users with no mobile-app roles
    _validate_mobile_user(user)

    # Generate / rotate the API token pair
    api_key, api_secret = _ensure_api_credentials(user)

    # Build the response — include both raw tokens and a pre-built
    # header value so the app doesn't have to assemble it.
    auth_header = f"token {api_key}:{api_secret}"

    return {
        "api_key":     api_key,
        "api_secret":  api_secret,
        "auth_header": auth_header,
        "user":        _user_profile(user),
        "logged_in_at": str(now_datetime())[:16],
    }


@frappe.whitelist(methods=["POST"])
def mobile_logout():
    """Mobile app logout — invalidate the current device's tokens.

    Called when the user taps "Log out" in the app. Rotates the
    api_secret so the now-cached token in the app no longer works.

    The next call from this device will get a 401 and trigger a
    re-login prompt — which is the correct behaviour.

    Note: this does NOT log other devices out. If the user has the
    app installed on both phone and tablet, logging out on phone
    only kills the phone's session. To kill all sessions, an admin
    must disable then re-enable the User in Desk.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Not logged in"), frappe.AuthenticationError)

    # Rotate the api_secret so the cached token in the calling app dies
    user_doc = frappe.get_doc("User", user)
    user_doc.api_secret = frappe.generate_hash(length=15)
    user_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"logged_out": True}


@frappe.whitelist(methods=["POST"])
def refresh_token():
    """Rotate the current user's api_secret without requiring password.

    Used by long-running mobile sessions — the app calls this every
    24 hours or so to get a fresh token, preventing one stale token
    from being usable indefinitely if intercepted.

    Returns the new (api_key, api_secret) pair. The app overwrites
    its stored credentials with the new ones.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Not logged in"), frappe.AuthenticationError)

    api_key, api_secret = _ensure_api_credentials(user)

    return {
        "api_key":     api_key,
        "api_secret":  api_secret,
        "auth_header": f"token {api_key}:{api_secret}",
    }


@frappe.whitelist(methods=["GET", "POST"])
def me():
    """Return the current user's profile.

    Called by the Flutter app on startup to:
        1. Verify the stored token still works
        2. Refresh user info (name, roles, photo)
        3. Decide which home screen to show based on primary_role

    Returns 401 if the token is invalid — the app's HTTP interceptor
    catches this and redirects to the login screen.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Not logged in"), frappe.AuthenticationError)

    return {"user": _user_profile(user)}


@frappe.whitelist(methods=["POST"])
def change_password(old_password: str, new_password: str):
    """Allow the user to change their own password from the mobile app.

    Validates old password via LoginManager (gives us the same rate
    limiting and lockout protection as login), then updates to new.

    After changing the password, the api_secret is also rotated so the
    user must re-login on this device. This prevents "I changed my
    password on phone but old phone is still logged in" scenarios.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Not logged in"), frappe.AuthenticationError)
    if not old_password or not new_password:
        frappe.throw(_("Both old and new passwords are required"))
    if len(new_password) < 8:
        frappe.throw(_("New password must be at least 8 characters"))

    # Verify old password with the same authenticate path
    lm = LoginManager()
    lm.authenticate(user=user, pwd=old_password)

    # Update password (this hashes it correctly)
    update_password(user=user, pwd=new_password)

    # Rotate api_secret — forces re-login on this device with new password
    user_doc = frappe.get_doc("User", user)
    user_doc.api_secret = frappe.generate_hash(length=15)
    user_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"changed": True, "must_re_login": True}