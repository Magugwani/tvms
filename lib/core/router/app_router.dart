// go_router setup with auth-aware redirects:
//   - Unauthenticated → /login (regardless of path)
//   - Authenticated → /home (if visiting /login)
//   - Loading → splash screen
//
// The redirect runs on every navigation, so when the auth
// provider state changes, the router updates automatically.
 
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
 
import '../../features/auth/providers/auth_provider.dart';
import '../../features/auth/ui/login_screen.dart';
import '../../features/home/ui/home_shell.dart';
import 'route_paths.dart';
 
final goRouterProvider = Provider<GoRouter>((ref) {
  // Watch auth state — refresh router when it changes
  final authNotifier = ref.watch(authProvider.notifier);
 
  return GoRouter(
    initialLocation: RoutePaths.splash,
    refreshListenable: GoRouterRefreshStream(
      authNotifier.stream,
    ),
    routes: [
      GoRoute(
        path: RoutePaths.splash,
        builder: (_, __) => const _SplashScreen(),
      ),
      GoRoute(
        path: RoutePaths.login,
        builder: (_, __) => const LoginScreen(),
      ),
      GoRoute(
        path: RoutePaths.home,
        builder: (_, __) => const HomeShell(),
      ),
    ],
    redirect: (context, state) {
      final auth = ref.read(authProvider);
      final isLoading = auth is AuthInitial || auth is AuthLoading;
      final isLoggedIn = auth is AuthAuthenticated;
 
      // Don't redirect while loading
      if (isLoading) {
        return state.matchedLocation == RoutePaths.splash
            ? null : RoutePaths.splash;
      }
 
      // Not logged in → login screen
      if (!isLoggedIn) {
        return state.matchedLocation == RoutePaths.login
            ? null : RoutePaths.login;
      }
 
      // Logged in but at login/splash → home
      if (state.matchedLocation == RoutePaths.login ||
          state.matchedLocation == RoutePaths.splash) {
        return RoutePaths.home;
      }
 
      // Otherwise let it through
      return null;
    },
  );
});
 
/// Bridges Riverpod's stream into go_router's refresh listener.
class GoRouterRefreshStream extends ChangeNotifier {
  GoRouterRefreshStream(Stream<dynamic> stream) {
    notifyListeners();
    _sub = stream.asBroadcastStream().listen((_) => notifyListeners());
  }
 
  late final dynamic _sub;
 
  @override
  void dispose() {
    _sub.cancel();
    super.dispose();
  }
}
 
// ─── Splash shown briefly during auth bootstrap ───
class _SplashScreen extends StatelessWidget {
  const _SplashScreen();
 
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 80, height: 80,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary,
                borderRadius: BorderRadius.circular(20),
              ),
              alignment: Alignment.center,
              child: const Icon(Icons.schedule,
                color: Colors.white, size: 40,
              ),
            ),
            const SizedBox(height: 24),
            const CircularProgressIndicator(strokeWidth: 2.5),
            const SizedBox(height: 16),
            Text('Loading TVMS...',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Colors.grey[600],
              ),
            ),
          ],
        ),
      ),
    );
  }
}