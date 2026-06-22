// Placeholder admin shell. Built out properly in a later
// phase — for now shows the logged-in admin's info and
// some "coming soon" action cards.
 
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
 
import '../../auth/providers/auth_provider.dart';
 
class AdminShell extends ConsumerWidget {
  const AdminShell({super.key});
 
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final user = authState is AuthAuthenticated ? authState.user : null;
    if (user == null) return const SizedBox.shrink();
 
    return Scaffold(
      appBar: AppBar(
        title: const Text('TVMS Admin'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: const Text('Sign out?'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Cancel')),
                    TextButton(onPressed: () => Navigator.pop(ctx, true),
                      child: const Text('Sign out',
                        style: TextStyle(color: Colors.red))),
                  ],
                ),
              );
              if (confirm == true) {
                await ref.read(authProvider.notifier).logout();
              }
            },
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          // ─── Welcome header ───
          Card(
            elevation: 0,
            color: Theme.of(context).colorScheme.primary,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Welcome,',
                    style: TextStyle(
                      color: Colors.white70,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(user.fullName,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text('Signed in as ${user.primaryRole}',
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
 
          // ─── Admin action cards ───
          Text('Quick Actions',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 12),
 
          _ActionCard(
            icon: Icons.upload_file,
            title: 'Enrollment',
            subtitle: 'Import students and lecturers',
          ),
          _ActionCard(
            icon: Icons.calendar_today,
            title: 'Timetable Management',
            subtitle: 'Schedule classes and venues',
          ),
          _ActionCard(
            icon: Icons.warning_amber,
            title: 'Emergency Sessions',
            subtitle: 'Manage cancellations and changes',
          ),
          _ActionCard(
            icon: Icons.analytics_outlined,
            title: 'Reports & Analytics',
            subtitle: 'Utilization, peak hours, summaries',
          ),
          _ActionCard(
            icon: Icons.people_outline,
            title: 'User Management',
            subtitle: 'Roles, permissions, accounts',
          ),
 
          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.blue.shade50,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.blue.shade200),
            ),
            child: Row(
              children: [
                Icon(Icons.info_outline,
                  color: Colors.blue.shade700, size: 20,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'For full admin access, use the web app on your computer.',
                    style: TextStyle(
                      color: Colors.blue.shade900,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
 
class _ActionCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
 
  const _ActionCard({
    required this.icon,
    required this.title,
    required this.subtitle,
  });
 
  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: Colors.white,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: ListTile(
        leading: Container(
          width: 44, height: 44,
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(10),
          ),
          alignment: Alignment.center,
          child: Icon(icon, size: 22,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
        title: Text(title,
          style: const TextStyle(
            fontSize: 15, fontWeight: FontWeight.w500,
          ),
        ),
        subtitle: Text(subtitle,
          style: TextStyle(fontSize: 12, color: Colors.grey[600]),
        ),
        trailing: const Chip(
          label: Text('Soon', style: TextStyle(fontSize: 10)),
          padding: EdgeInsets.zero,
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        onTap: () {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Coming in a later phase')),
          );
        },
      ),
    );
  }
}