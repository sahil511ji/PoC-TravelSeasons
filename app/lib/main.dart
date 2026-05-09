import 'package:flutter/material.dart';

import 'screens/main_scaffold.dart';
import 'theme/app_theme.dart';

void main() {
  runApp(const TravelSeasonsApp());
}

class TravelSeasonsApp extends StatelessWidget {
  const TravelSeasonsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Travel Seasons',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: const MainScaffold(),
    );
  }
}
