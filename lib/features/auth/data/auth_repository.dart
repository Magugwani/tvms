// All API calls related to auth go through this class. The
// UI layer never touches the http client directly.
 
import '../../../core/api/api_client.dart';
import '../../../core/api/api_endpoints.dart';
import '../../../core/storage/secure_storage.dart';
import '../models/login_response.dart';
import '../models/user_model.dart';
 
class AuthRepository {
  final ApiClient _api;
 
  AuthRepository({ApiClient? api}) : _api = api ?? ApiClient();
 
  /// POST mobile_login → save credentials → return user
  Future<LoginResponse> login({
    required String username,
    required String password,
  }) async {
    final result = await _api.post(
      ApiEndpoints.mobileLogin,
      body: {'usr': username, 'pwd': password},
      auth: false,                // login is the bootstrap, no token yet
    );
 
    final response = LoginResponse.fromJson(
      result as Map<String, dynamic>,
    );
 
    // Save credentials for subsequent requests
    await SecureStorage.saveCredentials(
      authHeader: response.authHeader,
      apiKey:     response.apiKey,
      apiSecret:  response.apiSecret,
      userEmail:  response.user.email,
    );
 
    return response;
  }
 
  /// POST mobile_logout → clear local credentials.
  /// Always succeeds locally even if the server call fails.
  Future<void> logout() async {
    try {
      await _api.post(ApiEndpoints.mobileLogout);
    } catch (_) {
      // Best effort on server, but we always clear locally
    } finally {
      await SecureStorage.clearAll();
    }
  }
 
  /// GET me() → returns fresh profile. Used on app startup to
  /// verify the saved token is still valid.
  Future<UserModel?> getCurrentUser() async {
    try {
      final result = await _api.post(ApiEndpoints.me);
      return UserModel.fromJson(result as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }
 
  /// Quick check at startup: do we have stored credentials?
  Future<bool> hasStoredCredentials() async {
    return SecureStorage.hasCredentials();
  }
 
  /// POST change_password
  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    await _api.post(
      ApiEndpoints.changePassword,
      body: {
        'old_password': oldPassword,
        'new_password': newPassword,
      },
    );
  }
}