import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'app_colors.dart';

class AppTheme {
  AppTheme._();

  static ThemeData light() {
    final base = ThemeData.light(useMaterial3: true);
    final textTheme = GoogleFonts.interTextTheme(base.textTheme).apply(
      bodyColor: AppColors.textPrimary,
      displayColor: AppColors.textPrimary,
    );

    return base.copyWith(
      scaffoldBackgroundColor: AppColors.surface,
      colorScheme: base.colorScheme.copyWith(
        primary: AppColors.brandGreen,
        secondary: AppColors.accentGold,
        surface: AppColors.surfaceCard,
        onPrimary: Colors.white,
      ),
      textTheme: textTheme.copyWith(
        bodyMedium: textTheme.bodyMedium?.copyWith(fontSize: 16),
        bodySmall: textTheme.bodySmall?.copyWith(fontSize: 14),
        labelLarge: textTheme.labelLarge?.copyWith(fontSize: 16),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.surface,
        foregroundColor: AppColors.textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
      ),
      iconTheme: const IconThemeData(color: AppColors.textPrimary, size: 24),
      dividerTheme: const DividerThemeData(
        color: AppColors.divider,
        thickness: 1,
        space: 1,
      ),
    );
  }
}
