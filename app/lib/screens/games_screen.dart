import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../games/screens/game_launcher.dart';
import '../theme/app_colors.dart';

class GamesScreen extends StatelessWidget {
  const GamesScreen({super.key});

  void _openGame(BuildContext context, GameKind kind) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => GameLauncher(kind: kind),
    ));
  }

  void _showComingSoon(BuildContext context, String name) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$name — coming after the PoC'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () {},
        ),
        title: const Column(
          children: [
            Text(
              'Travel games',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
            ),
            SizedBox(height: 2),
            Text(
              'Travel the world from your couch',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: AppColors.brandGreen,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: () {},
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          _buildStatsRow(),
          const SizedBox(height: 24),
          _sectionLabel('EMBEDDED VIA 3RD-PARTY SDK'),
          const SizedBox(height: 10),
          _buildSdkPlaceholder(),
          const SizedBox(height: 20),
          _buildFeaturedGameCard(
            context: context,
            imageUrl:
                'https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=900',
            title: 'Guess the Flag',
            subtitle: 'Recognise 5 country flags · earn credits when you score 4+',
            onTap: () => _openGame(context, GameKind.guessTheFlag),
          ),
          const SizedBox(height: 20),
          _sectionLabel('TRAVEL-THEMED'),
          const SizedBox(height: 10),
          _buildGameGrid(context),
        ],
      ),
    );
  }

  Widget _buildStatsRow() {
    return Row(
      children: [
        Expanded(child: _statCard('12', 'DAY STREAK')),
        const SizedBox(width: 10),
        Expanded(child: _statCard('348', 'BEST SCORE')),
        const SizedBox(width: 10),
        Expanded(child: _statCard('7', 'GAMES\nPLAYED TODAY')),
      ],
    );
  }

  Widget _statCard(String value, String label) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          Text(
            value,
            style: const TextStyle(
              fontSize: 26,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
              height: 1,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              color: AppColors.textSecondary,
              letterSpacing: 0.6,
              height: 1.3,
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionLabel(String text) {
    return Row(
      children: [
        const Icon(Icons.circle, size: 5, color: AppColors.textTertiary),
        const SizedBox(width: 6),
        Text(
          text,
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            color: AppColors.textSecondary,
            letterSpacing: 0.8,
          ),
        ),
      ],
    );
  }

  Widget _buildSdkPlaceholder() {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 20),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border, style: BorderStyle.solid),
      ),
      child: const Column(
        children: [
          Icon(Icons.sports_esports_outlined, size: 32, color: AppColors.textSecondary),
          SizedBox(height: 12),
          Text(
            'Game SDK iframe slot',
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Candidate SDKs: GameDistribution, Famobi, Unity\nWebGL, Cocos. Final pick at build time - this\nprototype tile is a placeholder.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
              height: 1.45,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFeaturedGameCard({
    required BuildContext context,
    required String imageUrl,
    required String title,
    required String subtitle,
    VoidCallback? onTap,
  }) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          child: AspectRatio(
            aspectRatio: 16 / 9,
            child: Stack(
          fit: StackFit.expand,
          children: [
            CachedNetworkImage(
              imageUrl: imageUrl,
              fit: BoxFit.cover,
              placeholder: (_, __) => Container(color: AppColors.surfaceMuted),
              errorWidget: (_, __, ___) => Container(color: AppColors.surfaceMuted),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.05),
                    Colors.black.withValues(alpha: 0.65),
                  ],
                  stops: const [0.4, 1.0],
                ),
              ),
            ),
            Positioned(
              top: 12,
              left: 12,
              child: Row(
                children: [
                  _badge('TODAY\'S PICK', color: AppColors.hotDealOrange),
                  const SizedBox(width: 6),
                  _badge('5 MIN', color: Colors.white, textColor: AppColors.textPrimary),
                ],
              ),
            ),
            Positioned(
              left: 14,
              right: 14,
              bottom: 14,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildGameGrid(BuildContext context) {
    final games = <_GameTile>[
      _GameTile(
        title: 'Cuisine quiz',
        subtitle: 'Where is this dish from?',
        duration: '4 MIN',
        imageUrl:
            'https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=600',
        onTap: () => _openGame(context, GameKind.cuisineQuiz),
      ),
      _GameTile(
        title: 'Capital match',
        subtitle: 'Country to capital',
        duration: '3 MIN',
        imageUrl:
            'https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=600',
        onTap: () => _showComingSoon(context, 'Capital match'),
      ),
      _GameTile(
        title: 'Wonder spot',
        subtitle: 'Identify world wonders',
        duration: '5 MIN',
        imageUrl:
            'https://images.unsplash.com/photo-1587474260584-136574528ed5?w=600',
        onTap: () => _showComingSoon(context, 'Wonder spot'),
      ),
      _GameTile(
        title: 'Currency match',
        subtitle: 'Spot the currency',
        duration: '3 MIN',
        imageUrl:
            'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600',
        onTap: () => _showComingSoon(context, 'Currency match'),
      ),
    ];

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: games.length,
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 0.95,
      ),
      itemBuilder: (_, i) => _gameTileCard(games[i]),
    );
  }

  Widget _gameTileCard(_GameTile g) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(14),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: g.onTap,
          child: Stack(
        fit: StackFit.expand,
        children: [
          CachedNetworkImage(
            imageUrl: g.imageUrl,
            fit: BoxFit.cover,
            placeholder: (_, __) => Container(color: AppColors.surfaceMuted),
            errorWidget: (_, __, ___) => Container(color: AppColors.surfaceMuted),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.0),
                  Colors.black.withValues(alpha: 0.7),
                ],
                stops: const [0.5, 1.0],
              ),
            ),
          ),
          Positioned(
            top: 10,
            left: 10,
            child: _badge(g.duration, color: Colors.white, textColor: AppColors.textPrimary),
          ),
          Positioned(
            left: 12,
            right: 12,
            bottom: 12,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  g.title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  g.subtitle,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ],
          ),
        ),
      ),
    );
  }

  Widget _badge(String text, {required Color color, Color textColor = Colors.white}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: textColor,
          fontSize: 11,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}

class _GameTile {
  final String title;
  final String subtitle;
  final String duration;
  final String imageUrl;
  final VoidCallback? onTap;
  _GameTile({
    required this.title,
    required this.subtitle,
    required this.duration,
    required this.imageUrl,
    this.onTap,
  });
}
