// Riverpod state for authentication. Single source of truth
// for whether the user is logged in, and who they are.
 
import 'package:flutter_riverpod/flutter_riverpod.dart';
 
import '../data/auth_repository.dart';
import '../models/user_model.dart';
 
// ────────────────────────────────────────────────────────
// Repository provider
// ────────────────────────────────────────────────────────
 
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(),
);
// ────────────────────────────────────────────────────────
// Auth state — sealed class hierarchy
// ────────────────────────────────────────────────────────
 
sealed class AuthState {
  const AuthState();
}
 
/// Starting up — checking saved credentials.
class AuthInitial extends AuthState {
  const AuthInitial();
}
 
/// Background work in progress.
class AuthLoading extends AuthState {
  const AuthLoading();
}
 
/// Logged in.
class AuthAuthenticated extends AuthState {
  final UserModel user;
  const AuthAuthenticated(this.user);
}
 
/// Not logged in (or just logged out).
class AuthUnauthenticated extends AuthState {
  final String? message;  // optional message to show on login screen
  const AuthUnauthenticated([this.message]);
}
 
/// Login failed — show on login screen.
class AuthError extends AuthState {
  final String message;
  const AuthError(this.message);
}
 
// ────────────────────────────────────────────────────────
// Notifier
// ────────────────────────────────────────────────────────
 
class AuthNotifier extends StateNotifier<AuthState> {
  final AuthRepository _repo;
 
  AuthNotifier(this._repo) : super(const AuthInitial()) {
    _bootstrap();
  }
 
  /// On app start, check if we have a stored token. If so,
  /// verify it with the server. If valid → authenticated.
  /// If not → unauthenticated.
  Future<void> _bootstrap() async {
    state = const AuthInitial();
 
    final hasCredentials = await _repo.hasStoredCredentials();
    if (!hasCredentials) {
      state = const AuthUnauthenticated();
      return;
    }
 
    // Verify the saved token still works
    final user = await _repo.getCurrentUser();
    if (user != null) {
      state = AuthAuthenticated(user);
    } else {
      state = const AuthUnauthenticated('Your session expired. Please log in again.');
    }
  }
 
  /// Login flow used by the login screen.
  Future<void> login({
    required String username,
    required String password,
  }) async {
    state = const AuthLoading();
    try {
      final response = await _repo.login(
        username: username, password: password,
      );
      state = AuthAuthenticated(response.user);
    } catch (e) {
      state = AuthError(e.toString());
    }
  }
 
  /// Logout flow.
  Future<void> logout() async {
    state = const AuthLoading();
    await _repo.logout();
    state = const AuthUnauthenticated();
  }
}
 
// ────────────────────────────────────────────────────────
// The provider
// ────────────────────────────────────────────────────────
 
final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final repo = ref.watch(authRepositoryProvider);
  return AuthNotifier(repo);
});