import 'package:flutter/foundation.dart';
import 'dart:io' show Platform;
 
class AppConfig {
  AppConfig._();
 
  // ────────────────────────────────────────────────────────
  // API base URLs — environment-aware
  // ────────────────────────────────────────────────────────
 
  /// URL used when running on web (Chrome). Uses your nip.io
  /// HTTPS setup so the SSL cert matches.
  static const String webApiBaseUrl =
      'https://tvms.127.0.0.1.nip.io';
 
  /// URL used when running on Android. Replace the IP with
  /// YOUR machine's LAN IP. Find it with:
  ///   hostname -I | awk '{print $1}'
  ///
  /// The phone needs to reach this address over your Wi-Fi.
  /// HTTPS is intentionally not used here because mkcert's
  /// local CA isn't installed on the phone.
  static const String androidApiBaseUrl =
      'http://192.168.1.106:8000';  

  /// Production URL — replace when you deploy. Used in release
  /// builds regardless of platform.
  static const String prodApiBaseUrl =
      'https://tvms.127.0.0.1.nip.io';
 
  /// Returns the right base URL for the current platform.
  static String get apiBaseUrl {
    // In release builds we always use prod
    if (kReleaseMode) return prodApiBaseUrl;
 
    // Web: use the HTTPS nip.io URL
    if (kIsWeb) return webApiBaseUrl;
 
    // Native (Android): use the LAN IP
    if (Platform.isAndroid) return androidApiBaseUrl;
 
    // Fallback for iOS / desktop dev
    return webApiBaseUrl;
  }
 
  // ────────────────────────────────────────────────────────
  // App-wide constants
  // ────────────────────────────────────────────────────────
 
  /// Default timeout for API requests.
  static const Duration apiTimeout = Duration(seconds: 30);
 
  /// Longer timeout for imports and heavy operations.
  static const Duration apiLongTimeout = Duration(minutes: 5);
 
  /// App display name.
  static const String appName = 'TVMS';
 
  /// App long name (shown on login screen and similar).
  static const String appLongName =
      'Timetable & Venue Management System';
 
  /// Institution name shown in UI when no setting is provided.
  static const String defaultInstitutionName =
      'National Institute of Transport';
}