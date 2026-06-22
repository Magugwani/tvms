// After login, this widget picks which shell to display based
// on the user's primary_role.
 
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
 
import '../../auth/providers/auth_provider.dart';
import 'admin_shell.dart';
import 'student_shell.dart';
 
class HomeShell extends ConsumerWidget {
  const HomeShell({super.key});
 
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
 
    if (authState is! AuthAuthenticated) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
 
    final user = authState.user;
 
    // Route to the right shell based on primary role
    if (user.isAdmin) {
      return const AdminShell();
    } else {
      return const StudentShell();
    }
  }
}