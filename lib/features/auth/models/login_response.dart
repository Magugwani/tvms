// Maps the mobile_login response to a Dart object.
// Server returns: { api_key, api_secret, auth_header, user, logged_in_at }
 
import 'user_model.dart';
 
class LoginResponse {
  final String apiKey;
  final String apiSecret;
  final String authHeader;
  final UserModel user;
  final String? loggedInAt;
 
  const LoginResponse({
    required this.apiKey,
    required this.apiSecret,
    required this.authHeader,
    required this.user,
    this.loggedInAt,
  });
 
  factory LoginResponse.fromJson(Map<String, dynamic> json) {
    return LoginResponse(
      apiKey:     json['api_key']?.toString() ?? '',
      apiSecret:  json['api_secret']?.toString() ?? '',
      authHeader: json['auth_header']?.toString() ?? '',
      user:       UserModel.fromJson(
                    (json['user'] as Map<String, dynamic>?) ?? const {},
                  ),
      loggedInAt: json['logged_in_at']?.toString(),
    );
  }
}