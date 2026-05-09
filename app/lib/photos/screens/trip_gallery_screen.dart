import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../models/photo.dart';
import '../models/trip.dart';
import '../services/api_client.dart';
import '../services/identity.dart';
import 'photo_viewer_screen.dart';

class TripGalleryScreen extends StatefulWidget {
  final Trip trip;
  const TripGalleryScreen({super.key, required this.trip});

  @override
  State<TripGalleryScreen> createState() => _TripGalleryScreenState();
}

class _TripGalleryScreenState extends State<TripGalleryScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tab = TabController(length: 3, vsync: this)
    ..addListener(() => setState(() {}));

  static const _filters = ['all', 'me', 'group'];

  final Map<String, List<Photo>?> _byFilter = {'all': null, 'me': null, 'group': null};
  final Map<String, Object?> _errors = {};

  String? _userId;
  bool _idLoaded = false;

  @override
  void initState() {
    super.initState();
    _loadIdentity();
  }

  Future<void> _loadIdentity() async {
    _userId = await Identity.instance.getUserId();
    if (!mounted) return;
    setState(() => _idLoaded = true);
    _loadFilter('all');
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  Future<void> _loadFilter(String filter) async {
    if (!_idLoaded) return;
    setState(() {
      _errors.remove(filter);
    });
    try {
      final photos = await ApiClient.instance.listTripPhotos(
        widget.trip.id,
        filter: filter,
        userId: _userId,
      );
      if (!mounted) return;
      setState(() => _byFilter[filter] = photos);
    } catch (e) {
      if (!mounted) return;
      setState(() => _errors[filter] = e);
    }
  }

  void _onTabChange() {
    final filter = _filters[_tab.index];
    if (_byFilter[filter] == null) _loadFilter(filter);
  }

  @override
  Widget build(BuildContext context) {
    if (_tab.indexIsChanging == false) _onTabChange();
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        title: Text(widget.trip.name),
        bottom: TabBar(
          controller: _tab,
          labelColor: AppColors.brandGreen,
          unselectedLabelColor: AppColors.textSecondary,
          indicatorColor: AppColors.brandGreen,
          labelStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
          tabs: const [
            Tab(text: 'All'),
            Tab(text: 'Photos of you'),
            Tab(text: 'Group'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tab,
        children: _filters.map(_buildPhotoGrid).toList(),
      ),
    );
  }

  Widget _buildPhotoGrid(String filter) {
    if (_errors.containsKey(filter)) {
      return _errorView(filter);
    }
    final photos = _byFilter[filter];
    if (photos == null) {
      return const Center(child: CircularProgressIndicator(color: AppColors.brandGreen));
    }
    if (photos.isEmpty) {
      return _emptyView(filter);
    }
    return RefreshIndicator(
      onRefresh: () => _loadFilter(filter),
      child: GridView.builder(
        padding: const EdgeInsets.all(8),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 3,
          mainAxisSpacing: 6,
          crossAxisSpacing: 6,
        ),
        itemCount: photos.length,
        itemBuilder: (_, i) => _photoTile(photos, i),
      ),
    );
  }

  Widget _photoTile(List<Photo> photos, int i) {
    final p = photos[i];
    return GestureDetector(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => PhotoViewerScreen(photos: photos, initialIndex: i),
      )),
      child: Stack(
        fit: StackFit.expand,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: CachedNetworkImage(
              imageUrl: p.url,
              fit: BoxFit.cover,
              placeholder: (_, __) => Container(color: AppColors.surfaceMuted),
              errorWidget: (_, __, ___) => Container(
                color: AppColors.surfaceMuted,
                child: const Icon(Icons.broken_image_outlined, color: AppColors.textTertiary),
              ),
            ),
          ),
          if (p.status != 'done')
            Positioned(
              top: 6,
              left: 6,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.7),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  p.status,
                  style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _emptyView(String filter) {
    final msg = switch (filter) {
      'me' => "You're not in any photos yet — give it a moment after the team uploads.",
      'group' => 'No group photos yet.',
      _ => 'No photos in this trip yet.',
    };
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Text(
          msg,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 15, color: AppColors.textSecondary),
        ),
      ),
    );
  }

  Widget _errorView(String filter) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_rounded, size: 48, color: AppColors.textSecondary),
            const SizedBox(height: 8),
            const Text("Couldn't load photos",
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(_errors[filter].toString(),
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
            const SizedBox(height: 12),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: AppColors.brandGreen),
              onPressed: () => _loadFilter(filter),
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}
