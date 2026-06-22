// Central list of all backend endpoint paths. Edit this file
// if any endpoint name changes — every part of the app uses
// these constants instead of hardcoding strings.
 
class ApiEndpoints {
  ApiEndpoints._();
 
  static const String _api = '/api/method';
 
  // ────────────────────────────────────────────────────────
  // Authentication
  // ────────────────────────────────────────────────────────
 
  static const String mobileLogin =
      '$_api/tvms.tvms.api.auth.mobile_login';
  static const String mobileLogout =
      '$_api/tvms.tvms.api.auth.mobile_logout';
  static const String refreshToken =
      '$_api/tvms.tvms.api.auth.refresh_token';
  static const String me =
      '$_api/tvms.tvms.api.auth.me';
  static const String changePassword =
      '$_api/tvms.tvms.api.auth.change_password';
 
  // ────────────────────────────────────────────────────────
  // Profile (self-service)
  // ────────────────────────────────────────────────────────
 
  static const String getMyProfile =
      '$_api/tvms.tvms.api.enrollment.get_my_profile';
  static const String updateMyPhone =
      '$_api/tvms.tvms.api.enrollment.update_my_phone';
 
  // ────────────────────────────────────────────────────────
  // Timetable
  // ────────────────────────────────────────────────────────
 
  static const String getPublishedWeekTimetable =
      '$_api/tvms.tvms.doctype.timetable.timetable.get_published_week_timetable';
  static const String getProgramTimetableGroups =
      '$_api/tvms.tvms.doctype.timetable.timetable.get_program_timetable_groups';
  static const String getInstitutionalHeader =
      '$_api/tvms.tvms.doctype.timetable.timetable.get_institutional_header';
  static const String getMyProgramSegment =
      '$_api/tvms.tvms.doctype.timetable.timetable.get_my_program_segment';
 
  // ────────────────────────────────────────────────────────
  // Notifications
  // ────────────────────────────────────────────────────────
 
  static const String getMyNotifications =
      '$_api/tvms.tvms.doctype.tvms_notifications.tvms_notifications.get_my_notifications';
  static const String markNotificationRead =
      '$_api/tvms.tvms.doctype.tvms_notifications.tvms_notifications.mark_read';
  static const String markAllNotificationsRead =
      '$_api/tvms.tvms.doctype.tvms_notifications.tvms_notifications.mark_all_read';
 
  // ────────────────────────────────────────────────────────
  // Emergency Sessions
  // ────────────────────────────────────────────────────────
 
  static const String listActiveEmergencySessions =
      '$_api/tvms.tvms.doctype.emergency_session.emergency_session.list_active_emergency_sessions';
  static const String forwardEmergencyNotification =
      '$_api/tvms.tvms.doctype.emergency_session.emergency_session.forward_notification';
  static const String postponeEmergencySession =
      '$_api/tvms.tvms.doctype.emergency_session.emergency_session.postpone_session';
 
  // ────────────────────────────────────────────────────────
  // Notification Preferences
  // ────────────────────────────────────────────────────────
 
  static const String getMyPreferences =
      '$_api/tvms.tvms.doctype.tvms_notification_preference.tvms_notification_preference.get_my_preferences';
  static const String updateMyPreferences =
      '$_api/tvms.tvms.doctype.tvms_notification_preference.tvms_notification_preference.update_my_preferences';
 
  // ────────────────────────────────────────────────────────
  // Push Notification Tokens (FCM)
  // ────────────────────────────────────────────────────────
 
  static const String registerDeviceToken =
      '$_api/tvms.tvms.api.push_notifications.register_device_token';
  static const String unregisterDeviceToken =
      '$_api/tvms.tvms.api.push_notifications.unregister_device_token';
  static const String listMyDevices =
      '$_api/tvms.tvms.api.push_notifications.list_my_devices';
 
  // ────────────────────────────────────────────────────────
  // Venues
  // ────────────────────────────────────────────────────────
 
  static const String listVenues =
      '$_api/tvms.tvms.doctype.venue.venue.list_venues';
  static const String getNearbyVenues =
      '$_api/tvms.tvms.doctype.venue.venue.get_nearby_venues';
  static const String getVenueQr =
      '$_api/tvms.tvms.doctype.venue.venue.get_venue_qr';
}