import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../models/trip.dart';
import '../services/api_client.dart';
import '../services/identity.dart';
import 'selfie_enrollment_screen.dart';
import 'trip_day_screen.dart';
import 'trip_gallery_screen.dart';

class PhotoGalleriesScreen extends StatefulWidget {
  const PhotoGalleriesScreen({super.key});

  @override
  State<PhotoGalleriesScreen> createState() => _PhotoGalleriesScreenState();
}

class _PhotoGalleriesScreenState extends State<PhotoGalleriesScreen> {
  bool _checking = true;
  bool _enrolled = false;
  List<Trip>? _trips;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    setState(() {
      _checking = true;
      _error = null;
    });
    try {
      final enrolled = await Identity.instance.isEnrolled();
      _enrolled = enrolled;
      if (!enrolled) {
        if (!mounted) return;
        setState(() => _checking = false);
        await _showEnrollment();
        return;
      }
      final trips = await ApiClient.instance.listTrips();
      _trips = trips;
    } catch (e) {
      _error = e;
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _showEnrollment() async {
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => const SelfieEnrollmentScreen(),
      ),
    );
    if (ok == true) {
      await _bootstrap();
    } else if (mounted) {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(title: const Text('Photo galleries')),
      body: _body(),
    );
  }

  Widget _body() {
    if (_checking) {
      return const Center(child: CircularProgressIndicator(color: AppColors.brandGreen));
    }
    if (!_enrolled) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.face_outlined, size: 64, color: AppColors.textTertiary),
              const SizedBox(height: 12),
              const Text("You're not enrolled yet.",
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 16),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: AppColors.brandGreen),
                onPressed: _showEnrollment,
                child: const Text('Add your selfie'),
              ),
            ],
          ),
        ),
      );
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_rounded, size: 56, color: AppColors.textSecondary),
              const SizedBox(height: 12),
              const Text("Couldn't load trips",
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              Text(_error.toString(),
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
              const SizedBox(height: 16),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: AppColors.brandGreen),
                onPressed: _bootstrap,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }
    final trips = _trips ?? [];
    if (trips.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text('No trips yet. Ask the team to add your trip.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16, color: AppColors.textSecondary)),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _bootstrap,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        itemCount: trips.length,
        separatorBuilder: (_, __) => const SizedBox(height: 12),
        itemBuilder: (_, i) => _tripCard(trips[i]),
      ),
    );
  }

  Widget _tripCard(Trip trip) {
    final cover = trip.members.isNotEmpty ? trip.members.first.selfieUrl : null;
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () async {
          // Prefer the day-aware view if the trip has any trip_days. Fallback
          // to the flat gallery for trips without itinerary entered.
          final days = await ApiClient.instance.listTripDays(trip.id);
          if (!mounted) return;
          final route = MaterialPageRoute(
            builder: (_) => days.isEmpty
                ? TripGalleryScreen(trip: trip)
                : TripDayScreen(trip: trip, days: days),
          );
          await Navigator.of(context).push(route);
          if (mounted) _bootstrap();
        },
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.border),
          ),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: SizedBox(
                  width: 64,
                  height: 64,
                  child: cover != null
                      ? CachedNetworkImage(
                          imageUrl: cover,
                          fit: BoxFit.cover,
                          placeholder: (_, __) => Container(color: AppColors.surfaceMuted),
                          errorWidget: (_, __, ___) =>
                              Container(color: AppColors.surfaceMuted, child: const Icon(Icons.image_outlined)),
                        )
                      : Container(
                          color: AppColors.surfaceMuted,
                          child: const Icon(Icons.image_outlined, color: AppColors.textTertiary),
                        ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      trip.name,
                      style: const TextStyle(
                          fontSize: 17, fontWeight: FontWeight.w700, color: AppColors.textPrimary),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${trip.photoCount} photos · ${trip.members.length} members',
                      style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: AppColors.textTertiary),
            ],
          ),
        ),
      ),
    );
  }
}
