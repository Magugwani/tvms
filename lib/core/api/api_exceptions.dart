// Typed exception hierarchy for API errors. Letting the UI
// switch on exception type produces clearer error messages
// than passing strings around.
 
abstract class ApiException implements Exception {
  final String message;
  final int? statusCode;
 
  ApiException(this.message, {this.statusCode});
 
  @override
  String toString() => message;
}
 
/// 401 — token missing, expired, or invalid.
/// The UI should route to login.
class UnauthorizedException extends ApiException {
  UnauthorizedException([String message = 'Session expired. Please log in again.'])
      : super(message, statusCode: 401);
}
 
/// 403 — user is logged in but lacks permission.
class ForbiddenException extends ApiException {
  ForbiddenException([String message = 'You don\'t have permission for this action.'])
      : super(message, statusCode: 403);
}
 
/// 404 — endpoint or resource not found.
class NotFoundException extends ApiException {
  NotFoundException([String message = 'Resource not found.'])
      : super(message, statusCode: 404);
}
 
/// 400 / 422 — server rejected the input (validation error).
class ValidationException extends ApiException {
  ValidationException(String message, {int? statusCode})
      : super(message, statusCode: statusCode);
}
 
/// 5xx — server error. Could be temporary.
class ServerException extends ApiException {
  ServerException([String message = 'Server error. Please try again.', int? statusCode])
      : super(message, statusCode: statusCode);
}
 
/// No internet, server unreachable, DNS failure, etc.
class NetworkException extends ApiException {
  NetworkException([String message = 'Cannot reach server. Check your connection.'])
      : super(message);
}
 
/// Request took too long.
class TimeoutException extends ApiException {
  TimeoutException([String message = 'Request timed out.'])
      : super(message);
}