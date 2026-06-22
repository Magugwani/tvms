/ Wrapper around flutter_secure_storage. Stores the api_key/
// api_secret pair from mobile_login so we can re-attach the
// Authorization header on every request, and stays valid
// across app restarts.
 
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
 
class SecureStorage {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
 
  // ── Keys ───────────────────────────────────────────────
  static const _kAuthHeader = 'auth_header';
  static const _kApiKey     = 'api_key';
  static const _kApiSecret  = 'api_secret';
  static const _kUserEmail  = 'user_email';
 
  // ── Save the entire credential bundle from login ──────
  static Future<void> saveCredentials({
    required String authHeader,
    required String apiKey,
    required String apiSecret,
    required String userEmail,
  }) async {
    await Future.wait([
      _storage.write(key: _kAuthHeader, value: authHeader),
      _storage.write(key: _kApiKey, value: apiKey),
      _storage.write(key: _kApiSecret, value: apiSecret),
      _storage.write(key: _kUserEmail, value: userEmail),
    ]);
  }
 
  // ── Read the auth header for outgoing requests ────────
  static Future<String?> getAuthHeader() async {
    return _storage.read(key: _kAuthHeader);
  }
 
  static Future<String?> getUserEmail() async {
    return _storage.read(key: _kUserEmail);
  }
 
  // ── Did we previously log in? ─────────────────────────
  static Future<bool> hasCredentials() async {
    final header = await getAuthHeader();
    return header != null && header.isNotEmpty;
  }
 
  // ── Clear everything on logout ────────────────────────
  static Future<void> clearAll() async {
    await _storage.deleteAll();
  }
}