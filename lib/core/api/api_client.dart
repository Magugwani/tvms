// Thin wrapper around package:http. Handles:
//   - prepending the API base URL
//   - attaching the stored Authorization header
//   - parsing Frappe's JSON response envelope ({"message": ...})
//   - mapping HTTP status codes to typed exceptions
//   - timeout handling
//
// All other code in the app calls into ApiClient methods
// rather than http.* directly, so we have one place to add
// retry logic, logging, etc. later.
 
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
 
import '../config/app_config.dart';
import '../storage/secure_storage.dart';
import 'api_exceptions.dart';
 
class ApiClient {
  ApiClient._();
  static final ApiClient _instance = ApiClient._();
  factory ApiClient() => _instance;
 
  /// GET request — returns the parsed "message" field of Frappe's
  /// response envelope. Pass auth = false for public endpoints.
  Future<dynamic> get(
    String path, {
    Map<String, String>? queryParams,
    bool auth = true,
    Duration? timeout,
  }) async {
    final uri = _buildUri(path, queryParams);
    final headers = await _buildHeaders(auth: auth);
 
    try {
      final response = await http
          .get(uri, headers: headers)
          .timeout(timeout ?? AppConfig.apiTimeout);
      return _processResponse(response);
    } on SocketException {
      throw NetworkException();
    } on TimeoutException {
      throw TimeoutException();
    } on http.ClientException catch (e) {
      throw NetworkException(e.message);
    }
  }
 
  /// POST request with a JSON body (or no body).
  Future<dynamic> post(
    String path, {
    Map<String, dynamic>? body,
    bool auth = true,
    Duration? timeout,
  }) async {
    final uri = _buildUri(path);
    final headers = await _buildHeaders(auth: auth, hasBody: true);
 
    try {
      final response = await http
          .post(
            uri,
            headers: headers,
            body: body != null ? json.encode(body) : null,
          )
          .timeout(timeout ?? AppConfig.apiTimeout);
      return _processResponse(response);
    } on SocketException {
      throw NetworkException();
    } on TimeoutException {
      throw TimeoutException();
    } on http.ClientException catch (e) {
      throw NetworkException(e.message);
    }
  }
 
  // ────────────────────────────────────────────────────────
  // Internal helpers
  // ────────────────────────────────────────────────────────
 
  Uri _buildUri(String path, [Map<String, String>? queryParams]) {
    final base = AppConfig.apiBaseUrl;
    final full = '$base$path';
    if (queryParams == null || queryParams.isEmpty) {
      return Uri.parse(full);
    }
    return Uri.parse(full).replace(queryParameters: queryParams);
  }
 
  Future<Map<String, String>> _buildHeaders({
    required bool auth,
    bool hasBody = false,
  }) async {
    final headers = <String, String>{
      'Accept': 'application/json',
      if (hasBody) 'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': 'no-csrf',  // disables CSRF for API calls
    };
 
    if (auth) {
      final authHeader = await SecureStorage.getAuthHeader();
      if (authHeader != null && authHeader.isNotEmpty) {
        headers['Authorization'] = authHeader;
      }
    }
 
    return headers;
  }
 
  /// Frappe wraps responses as `{"message": <actual data>}`.
  /// This unwraps it and maps errors to typed exceptions.
  dynamic _processResponse(http.Response response) {
    final code = response.statusCode;
    final bodyText = response.body;
 
    Map<String, dynamic>? bodyJson;
    try {
      if (bodyText.isNotEmpty) {
        bodyJson = json.decode(bodyText) as Map<String, dynamic>;
      }
    } catch (_) {
      // Not JSON — fall through with bodyJson = null
    }
 
    // Handle errors first
    if (code >= 400) {
      final message = _extractErrorMessage(bodyJson, bodyText, code);
 
      if (code == 401) throw UnauthorizedException(message);
      if (code == 403) throw ForbiddenException(message);
      if (code == 404) throw NotFoundException(message);
      if (code == 400 || code == 422) throw ValidationException(message, statusCode: code);
      if (code >= 500) throw ServerException(message, code);
      throw ApiClientErrorException(message, code);
    }
 
    // Success — unwrap Frappe envelope
    if (bodyJson != null && bodyJson.containsKey('message')) {
      return bodyJson['message'];
    }
 
    // Some endpoints return direct JSON without the envelope
    return bodyJson ?? bodyText;
  }
 
  String _extractErrorMessage(
    Map<String, dynamic>? bodyJson,
    String bodyText,
    int code,
  ) {
    if (bodyJson == null) {
      return 'HTTP $code';
    }
 
    // Frappe error formats encountered:
    //   {"exception": "...", "exc_type": "..."}
    //   {"_server_messages": "[\"...\"]"}
    //   {"message": "human readable"}
    //   {"error": "..."}
 
    if (bodyJson['_server_messages'] != null) {
      try {
        final messages = json.decode(bodyJson['_server_messages'] as String) as List;
        if (messages.isNotEmpty) {
          final first = messages.first;
          if (first is String) {
            try {
              // The string is itself a JSON object
              final parsed = json.decode(first) as Map<String, dynamic>;
              return (parsed['message'] as String?) ?? first;
            } catch (_) {
              return first;
            }
          }
        }
      } catch (_) {}
    }
 
    if (bodyJson['exception'] != null) {
      final ex = bodyJson['exception'].toString();
      // "frappe.exceptions.AuthenticationError: Invalid login" → "Invalid login"
      final colon = ex.indexOf(':');
      return colon >= 0 ? ex.substring(colon + 1).trim() : ex;
    }
 
    if (bodyJson['message'] != null) return bodyJson['message'].toString();
    if (bodyJson['error']   != null) return bodyJson['error'].toString();
 
    return 'HTTP $code';
  }
}
 
/// Catch-all for HTTP 4xx codes not covered by specific exceptions above.
class ApiClientErrorException extends ApiException {
  ApiClientErrorException(String message, int? statusCode)
      : super(message, statusCode: statusCode);
}