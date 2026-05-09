import 'package:flutter/material.dart';

import '../profile/profile_screen.dart';
import '../theme/app_colors.dart';
import 'games_screen.dart';
import 'home_screen.dart';
import 'placeholder_screen.dart';

class MainScaffold extends StatefulWidget {
  const MainScaffold({super.key});

  @override
  State<MainScaffold> createState() => _MainScaffoldState();
}

class _MainScaffoldState extends State<MainScaffold> {
  int _index = 0;

  static const _tabs = <_NavTab>[
    _NavTab('Discover', Icons.home_outlined, Icons.home_rounded),
    _NavTab('My Trips', Icons.work_outline_rounded, Icons.work_rounded),
    _NavTab('Documents', Icons.description_outlined, Icons.description_rounded),
    _NavTab('Games', Icons.sports_esports_outlined, Icons.sports_esports_rounded),
    _NavTab('Profile', Icons.person_outline_rounded, Icons.person_rounded),
  ];

  Widget _bodyFor(int i) {
    switch (i) {
      case 0:
        return const HomeScreen();
      case 3:
        return const GamesScreen();
      case 4:
        return const ProfileScreen();
      default:
        return PlaceholderScreen(title: _tabs[i].label);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: List.generate(_tabs.length, _bodyFor),
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: AppColors.divider, width: 1)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 64,
            child: Row(
              children: List.generate(_tabs.length, (i) {
                final tab = _tabs[i];
                final selected = i == _index;
                final color = selected ? AppColors.brandGreen : AppColors.textTertiary;
                return Expanded(
                  child: InkWell(
                    onTap: () => setState(() => _index = i),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(selected ? tab.activeIcon : tab.icon, color: color, size: 26),
                        const SizedBox(height: 4),
                        Text(
                          tab.label,
                          style: TextStyle(
                            color: color,
                            fontSize: 12,
                            fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}

class _NavTab {
  final String label;
  final IconData icon;
  final IconData activeIcon;
  const _NavTab(this.label, this.icon, this.activeIcon);
}
