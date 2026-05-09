import 'package:flutter/material.dart';

import '../photos/screens/photo_galleries_screen.dart';
import '../photos/services/identity.dart';
import '../theme/app_colors.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  String? _name;

  @override
  void initState() {
    super.initState();
    _loadName();
  }

  Future<void> _loadName() async {
    final n = await Identity.instance.getUserName();
    if (!mounted) return;
    setState(() => _name = n);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        children: [
          _profileHeader(),
          const SizedBox(height: 24),
          _section('MEMORIES'),
          _settingsCard([
            _row(
              icon: Icons.photo_library_outlined,
              title: 'Photo galleries',
              subtitle: 'Auto-tagged with face recognition',
              onTap: () async {
                await Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => const PhotoGalleriesScreen(),
                ));
                if (mounted) _loadName();
              },
            ),
            _row(
              icon: Icons.access_time_rounded,
              title: 'Past trips',
              subtitle: 'Relive them anytime',
              onTap: () => _comingSoon('Past trips'),
            ),
          ]),
          const SizedBox(height: 24),
          _section('PREFERENCES'),
          _settingsCard([
            _row(
              icon: Icons.menu_book_outlined,
              title: 'Language',
              subtitle: 'English',
              onTap: () => _comingSoon('Language'),
            ),
            _row(
              icon: Icons.text_fields_rounded,
              title: 'Easy mode',
              subtitle: 'Larger fonts and voice readout',
              onTap: () => _comingSoon('Easy mode'),
            ),
            _row(
              icon: Icons.notifications_none_rounded,
              title: 'Notifications',
              subtitle: 'All channels enabled',
              onTap: () => _comingSoon('Notifications'),
            ),
          ]),
          const SizedBox(height: 24),
          _section('ACCOUNT'),
          _settingsCard([
            _row(
              icon: Icons.face_outlined,
              title: 'Re-take selfie',
              subtitle: 'Replace your enrolled face',
              onTap: () async {
                await Identity.instance.clear();
                if (!mounted) return;
                await Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => const PhotoGalleriesScreen(),
                ));
                _loadName();
              },
            ),
          ]),
        ],
      ),
    );
  }

  Widget _profileHeader() {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 28,
            backgroundColor: AppColors.brandGreen.withValues(alpha: 0.12),
            child: Text(
              (_name ?? 'You').characters.first.toUpperCase(),
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: AppColors.brandGreen,
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _name ?? 'Hello',
                  style: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                const Text(
                  'Travel Seasons traveller',
                  style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _section(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w800,
          color: AppColors.textSecondary,
          letterSpacing: 0.8,
        ),
      ),
    );
  }

  Widget _settingsCard(List<Widget> children) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(children: _interleaveDividers(children)),
    );
  }

  List<Widget> _interleaveDividers(List<Widget> rows) {
    if (rows.isEmpty) return rows;
    final out = <Widget>[];
    for (var i = 0; i < rows.length; i++) {
      out.add(rows[i]);
      if (i != rows.length - 1) {
        out.add(const Divider(height: 1, color: AppColors.divider, indent: 64));
      }
    }
    return out;
  }

  Widget _row({
    required IconData icon,
    required String title,
    required String subtitle,
    VoidCallback? onTap,
  }) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: AppColors.textPrimary, size: 22),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.textPrimary)),
                  const SizedBox(height: 2),
                  Text(subtitle,
                      style:
                          const TextStyle(fontSize: 13, color: AppColors.textSecondary, height: 1.3)),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: AppColors.textTertiary),
          ],
        ),
      ),
    );
  }

  void _comingSoon(String name) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$name — coming soon'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}
