import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

class PlaceholderScreen extends StatelessWidget {
  final String title;
  const PlaceholderScreen({super.key, required this.title});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(
        child: Text(
          '$title\n(coming soon)',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 18, color: AppColors.textSecondary),
        ),
      ),
    );
  }
}
