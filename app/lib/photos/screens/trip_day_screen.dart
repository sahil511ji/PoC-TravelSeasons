import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../models/photo.dart';
import '../models/trip.dart';
import '../models/trip_day.dart';
import '../services/api_client.dart';
import '../services/identity.dart';
import '../widgets/recap_video_card.dart';
import 'photo_viewer_screen.dart';

class TripDayScreen extends StatefulWidget {
  final Trip trip;
  final List<TripDaySummary> days;
  final int initialIndex;

  const TripDayScreen({
    super.key,
    required this.trip,
    required this.days,
    this.initialIndex = 0,
  });

  @override
  State<TripDayScreen> createState() => _TripDayScreenState();
}

class _TripDayScreenState extends State<TripDayScreen> {
  late int _index = widget.initialIndex;
  String _filter = 'all';
  String? _userId;
  final Map<String, TripDay?> _cache = {};
  // photos keyed by "<dayId>|<filter>"
  final Map<String, List<Photo>?> _photoCache = {};
  Object? _error;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    _userId = await Identity.instance.getUserId();
    await _load();
  }

  TripDaySummary get _currentSummary => widget.days[_index];

  String _photoKey(String dayId) => '$dayId|$_filter';

  Future<void> _load() async {
    final summary = _currentSummary;
    setState(() => _error = null);
    try {
      _cache[summary.id] ??= await ApiClient.instance.getTripDay(summary.id);
      final key = _photoKey(summary.id);
      _photoCache[key] ??= await ApiClient.instance.listTripPhotos(
        widget.trip.id,
        filter: _filter,
        userId: _filter == 'me' ? _userId : null,
      );
      if (!mounted) return;
      setState(() {});
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final summary = _currentSummary;
    final day = _cache[summary.id];

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(title: Text(widget.trip.name)),
      body: SafeArea(
        child: Column(
          children: [
            _dayPicker(),
            _filterChips(),
            Expanded(child: _body(day)),
          ],
        ),
      ),
    );
  }

  Widget _dayPicker() {
    return SizedBox(
      height: 56,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        itemCount: widget.days.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final d = widget.days[i];
          final selected = i == _index;
          return GestureDetector(
            onTap: () {
              setState(() => _index = i);
              _load();
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: selected ? AppColors.brandGreen : Colors.white,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: selected ? AppColors.brandGreen : AppColors.border,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'Day ${i + 1}',
                    style: TextStyle(
                      color: selected ? Colors.white : AppColors.textPrimary,
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                    ),
                  ),
                  if (d.theme != null) ...[
                    const SizedBox(width: 6),
                    Text(
                      '· ${d.theme}',
                      style: TextStyle(
                        color: selected ? Colors.white70 : AppColors.textSecondary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _filterChips() {
    const labels = <String, String>{
      'all': 'All',
      'me': 'Photos of you',
      'group': 'Group',
    };
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: SizedBox(
        height: 36,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: labels.length,
          separatorBuilder: (_, __) => const SizedBox(width: 8),
          itemBuilder: (_, i) {
            final key = labels.keys.elementAt(i);
            final label = labels[key]!;
            final selected = _filter == key;
            return GestureDetector(
              onTap: () {
                if (_filter == key) return;
                setState(() => _filter = key);
                _load();
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: selected ? AppColors.textPrimary : Colors.white,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: selected ? AppColors.textPrimary : AppColors.border,
                  ),
                ),
                child: Text(
                  label,
                  style: TextStyle(
                    color: selected ? Colors.white : AppColors.textPrimary,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _body(TripDay? day) {
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_rounded, size: 48, color: AppColors.textSecondary),
              const SizedBox(height: 12),
              Text(_error.toString(),
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
              const SizedBox(height: 12),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: AppColors.brandGreen),
                onPressed: _load,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }
    if (day == null) {
      return const Center(child: CircularProgressIndicator(color: AppColors.brandGreen));
    }

    final allPhotos = _photoCache[_photoKey(day.id)] ?? const <Photo>[];
    // Group photos by itinerary item id
    final Map<String, List<Photo>> grouped = {for (final it in day.items) it.id: <Photo>[]};
    final List<Photo> unsorted = [];
    for (final p in allPhotos) {
      final iid = p.itineraryItemId;
      if (iid != null && grouped.containsKey(iid)) {
        grouped[iid]!.add(p);
      } else {
        unsorted.add(p);
      }
    }
    for (final list in grouped.values) {
      list.sort((a, b) => (a.takenAt ?? '').compareTo(b.takenAt ?? ''));
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          if (day.latestVideo != null) ...[
            RecapVideoCard(
              video: day.latestVideo!,
              dayTitle: day.theme ?? day.date,
            ),
            const SizedBox(height: 16),
          ],
          for (final item in day.items)
            if ((grouped[item.id]?.isNotEmpty ?? false))
              _itemSection(item.title, item.startTime, item.endTime, grouped[item.id]!, allPhotos),
          if (unsorted.isNotEmpty)
            _itemSection('Other photos', null, null, unsorted, allPhotos),
          if (allPhotos.isEmpty)
            Padding(
              padding: const EdgeInsets.all(32),
              child: Text(
                switch (_filter) {
                  'me' => "No photos of you yet for this day.\nEnroll a selfie or wait until processing finishes.",
                  'group' => 'No group photos (≥2 matched people) for this day.',
                  _ => 'No photos yet for this day.',
                },
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.textSecondary),
              ),
            ),
        ],
      ),
    );
  }

  Widget _itemSection(String title, String? start, String? end, List<Photo> photos, List<Photo> allPhotos) {
    final timeStr = (start != null && end != null) ? '$start – $end' : '';
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(title,
                      style: const TextStyle(
                          fontSize: 17, fontWeight: FontWeight.w800, color: AppColors.textPrimary)),
                ),
                if (timeStr.isNotEmpty)
                  Text(timeStr, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                const SizedBox(width: 8),
                Text('${photos.length} photos',
                    style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
              ],
            ),
          ),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 3, mainAxisSpacing: 4, crossAxisSpacing: 4),
            itemCount: photos.length,
            itemBuilder: (_, i) {
              final p = photos[i];
              return GestureDetector(
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => PhotoViewerScreen(
                    photos: allPhotos,
                    initialIndex: allPhotos.indexOf(p),
                  ),
                )),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: CachedNetworkImage(
                    imageUrl: p.url, fit: BoxFit.cover,
                    placeholder: (_, __) => Container(color: AppColors.surfaceMuted),
                    errorWidget: (_, __, ___) => Container(
                      color: AppColors.surfaceMuted,
                      child: const Icon(Icons.broken_image_outlined),
                    ),
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}
