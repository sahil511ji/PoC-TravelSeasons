import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _tripTypeIndex = 0;
  int _filterIndex = 0;

  static const _filters = ['All', 'Hot deals', 'Trending', 'Senior special'];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Stack(
          children: [
            ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 100),
              children: [
                _buildHeader(),
                const SizedBox(height: 16),
                _buildSearchBar(),
                const SizedBox(height: 16),
                _buildBirthdayBanner(),
                const SizedBox(height: 20),
                _buildTripTypeToggle(),
                const SizedBox(height: 16),
                _buildFilterChips(),
                const SizedBox(height: 24),
                _buildSectionHeader('Upcoming departures', 'See all'),
                const SizedBox(height: 12),
                _buildTripCard(),
              ],
            ),
            Positioned(
              right: 16,
              bottom: 16,
              child: _buildAskSageButton(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: [
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Good morning',
                style: TextStyle(
                  fontSize: 15,
                  color: AppColors.textSecondary,
                  fontWeight: FontWeight.w500,
                ),
              ),
              SizedBox(height: 2),
              Text(
                'Nitin',
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.w800,
                  color: AppColors.textPrimary,
                  height: 1.1,
                ),
              ),
            ],
          ),
        ),
        _circleIconButton(Icons.language_rounded),
        const SizedBox(width: 10),
        _circleIconButton(Icons.notifications_none_rounded, hasDot: true),
        const SizedBox(width: 10),
        _circleIconButton(Icons.account_balance_wallet_outlined),
      ],
    );
  }

  Widget _circleIconButton(IconData icon, {bool hasDot = false}) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            color: Colors.white,
            shape: BoxShape.circle,
            border: Border.all(color: AppColors.border, width: 1),
          ),
          child: Icon(icon, size: 22, color: AppColors.textPrimary),
        ),
        if (hasDot)
          Positioned(
            top: 8,
            right: 10,
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: AppColors.notificationDot,
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 1.5),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildSearchBar() {
    return Container(
      height: 52,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(28),
      ),
      child: Row(
        children: [
          const Icon(Icons.search_rounded, color: AppColors.textTertiary, size: 22),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'Where would you like to go?',
              style: TextStyle(
                fontSize: 16,
                color: AppColors.textTertiary,
              ),
            ),
          ),
          Icon(Icons.mic_none_rounded, color: AppColors.brandGreen, size: 22),
        ],
      ),
    );
  }

  Widget _buildBirthdayBanner() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
      decoration: BoxDecoration(
        color: AppColors.accentGoldLight,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('🎂', style: TextStyle(fontSize: 26)),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Happy birthday, Nitin!',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF6B4A12),
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  "From all of us at Travel Seasons – here's a\nspecial voucher in your wallet today.",
                  style: TextStyle(
                    fontSize: 13,
                    color: Color(0xFF6B4A12),
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: Color(0xFF6B4A12)),
        ],
      ),
    );
  }

  Widget _buildTripTypeToggle() {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          _toggleSegment('Group tours', 0),
          _toggleSegment('FIT (private)', 1),
        ],
      ),
    );
  }

  Widget _toggleSegment(String label, int index) {
    final selected = _tripTypeIndex == index;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _tripTypeIndex = index),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: selected ? Colors.white : Colors.transparent,
            borderRadius: BorderRadius.circular(9),
            boxShadow: selected
                ? [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.06),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: selected ? AppColors.textPrimary : AppColors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFilterChips() {
    return SizedBox(
      height: 36,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: _filters.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final selected = _filterIndex == i;
          final label = _filters[i];
          return GestureDetector(
            onTap: () => setState(() => _filterIndex = i),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: selected ? AppColors.textPrimary : Colors.white,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: selected ? AppColors.textPrimary : AppColors.border,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (label == 'Hot deals') ...[
                    const Text('🔥', style: TextStyle(fontSize: 14)),
                    const SizedBox(width: 6),
                  ],
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: selected ? Colors.white : AppColors.textPrimary,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildSectionHeader(String title, String action) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
        Text(
          action,
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: AppColors.brandGreen,
          ),
        ),
      ],
    );
  }

  Widget _buildTripCard() {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceCard,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Stack(
            children: [
              ClipRRect(
                borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
                child: AspectRatio(
                  aspectRatio: 16 / 11,
                  child: CachedNetworkImage(
                    imageUrl: 'https://images.unsplash.com/photo-1582719471384-894fbb16e074?w=900',
                    fit: BoxFit.cover,
                    placeholder: (_, __) => Container(color: AppColors.surfaceMuted),
                    errorWidget: (_, __, ___) =>
                        Container(color: AppColors.surfaceMuted, child: const Icon(Icons.landscape, size: 48)),
                  ),
                ),
              ),
              Positioned(
                top: 12,
                left: 12,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: AppColors.badgeDark,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.access_time_rounded, color: Colors.white, size: 14),
                      SizedBox(width: 4),
                      Text(
                        'Filling fast',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Positioned(
                top: 12,
                right: 12,
                child: Container(
                  width: 36,
                  height: 36,
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.favorite_border_rounded, size: 20, color: AppColors.textPrimary),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Land of the Thunder Dragon',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    _metaItem(Icons.location_on_outlined, 'Bhutan'),
                    const SizedBox(width: 14),
                    _metaItem(Icons.calendar_today_outlined, '12 – 19 Oct'),
                    const SizedBox(width: 14),
                    _metaItem(Icons.person_outline_rounded, '8…'),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _metaItem(IconData icon, String text) {
    return Row(
      children: [
        Icon(icon, size: 16, color: AppColors.brandGreen),
        const SizedBox(width: 4),
        Text(
          text,
          style: const TextStyle(
            fontSize: 13,
            color: AppColors.textSecondary,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildAskSageButton() {
    return Material(
      color: AppColors.brandGreen,
      borderRadius: BorderRadius.circular(28),
      elevation: 6,
      shadowColor: AppColors.brandGreen.withValues(alpha: 0.4),
      child: InkWell(
        borderRadius: BorderRadius.circular(28),
        onTap: () {},
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 18, vertical: 12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.star_outline_rounded, color: Colors.white, size: 20),
              SizedBox(width: 8),
              Text(
                'Ask Sage',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
