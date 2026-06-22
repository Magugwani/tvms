// Placeholder home shell for Student, Lecturer, CR roles.
// Bottom navigation with 4 tabs. Real content goes in
// Phase 2+ — for now, each tab shows a placeholder card.
 
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
 
import '../../auth/providers/auth_provider.dart';
 
class StudentShell extends ConsumerStatefulWidget {
  const StudentShell({super.key});
 
  @override
  ConsumerState<StudentShell> createState() => _StudentShellState();
}
 
class _StudentShellState extends ConsumerState<StudentShell> {
  int _tab = 0;
 
  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final user = authState is AuthAuthenticated ? authState.user : null;
 
    final tabs = const [
      _TabPlaceholder(
        icon: Icons.calendar_today,
        title: 'My Timetable',
        subtitle: 'Your weekly schedule will appear here.',
      ),
      _TabPlaceholder(
        icon: Icons.notifications_outlined,
        title: 'Notifications',
        subtitle: 'Schedule changes, emergencies, and updates.',
      ),
      _TabPlaceholder(
        icon: Icons.place_outlined,
        title: 'Venues',
        subtitle: 'Find rooms and their locations on campus.',
      ),
      _ProfileTab(),
    ];
 
    return Scaffold(
      appBar: AppBar(
        title: Text(_tab == 0 ? 'TVMS' : _tabTitles[_tab]),
        actions: [
          if (_tab == 0)
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: () {/* phase 2 */},
            ),
        ],
      ),
      body: tabs[_tab],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.calendar_today_outlined),
            selectedIcon: Icon(Icons.calendar_today), label: 'Timetable'),
          NavigationDestination(icon: Icon(Icons.notifications_outlined),
            selectedIcon: Icon(Icons.notifications), label: 'Notifications'),
          NavigationDestination(icon: Icon(Icons.place_outlined),
            selectedIcon: Icon(Icons.place), label: 'Venues'),
          NavigationDestination(icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
 
  static const _tabTitles = [
    'TVMS', 'Notifications', 'Venues', 'Profile',
  ];
}
 
// ─── Placeholder body ───
class _TabPlaceholder extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
 
  const _TabPlaceholder({
    required this.icon,
    required this.title,
    required this.subtitle,
  });
 
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 80, height: 80,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primaryContainer,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Icon(icon, size: 36,
                color: Theme.of(context).colorScheme.primary),
            ),
            const SizedBox(height: 20),
            Text(title,
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            Text(subtitle,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Colors.grey[600],
              ),
            ),
            const SizedBox(height: 32),
            const Chip(
              label: Text('Coming soon'),
              padding: EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            ),
          ],
        ),
      ),
    );
  }
}
 
// ─── Profile tab — shows logged-in user info ───
class _ProfileTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final user = authState is AuthAuthenticated ? authState.user : null;
    if (user == null) return const SizedBox.shrink();
 
    final initials = user.fullName.isNotEmpty
        ? user.fullName.trim().split(' ').map((s) => s.isNotEmpty ? s[0] : '').take(2).join()
        : 'U';
 
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        // ─── Avatar + name ───
        Card(
          elevation: 0,
          color: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(color: Colors.grey.shade200),
          ),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 28,
                  backgroundColor: Theme.of(context).colorScheme.primary,
                  child: Text(
                    initials.toUpperCase(),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(user.fullName,
                        style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w500,
                        ),
                      ),
                      Text(user.email,
                        style: TextStyle(
                          fontSize: 13, color: Colors.grey[600],
                        ),
                      ),
                      const SizedBox(height: 4),
                      Wrap(
                        spacing: 4,
                        children: user.roles.map((r) => Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.primaryContainer,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Text(
                            r == 'Class Representative (CR)' ? 'CR' : r,
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w500,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                          ),
                        )).toList(),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
 
        // ─── Logout ───
        SizedBox(
          height: 50,
          child: OutlinedButton.icon(
            icon: const Icon(Icons.logout, color: Colors.red),
            label: const Text('Sign out',
              style: TextStyle(color: Colors.red),
            ),
            style: OutlinedButton.styleFrom(
              side: const BorderSide(color: Colors.red),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            onPressed: () async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: const Text('Sign out?'),
                  content: const Text('You\'ll need to log back in.'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Cancel')),
                    TextButton(onPressed: () => Navigator.pop(ctx, true),
                      child: const Text('Sign out',
                        style: TextStyle(color: Colors.red)),
                    ),
                  ],
                ),
              );
              if (confirm == true) {
                await ref.read(authProvider.notifier).logout();
              }
            },
          ),
        ),
      ],
    );
  }
}