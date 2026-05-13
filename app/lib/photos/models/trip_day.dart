import 'itinerary_item.dart';

class VideoRender {
  final String id;
  final int version;
  final String status;
  final String? mp4Url;
  final int? durationSeconds;

  VideoRender({
    required this.id,
    required this.version,
    required this.status,
    this.mp4Url,
    this.durationSeconds,
  });

  factory VideoRender.fromJson(Map<String, dynamic> j) => VideoRender(
        id: j['id'] as String,
        version: (j['version'] as num?)?.toInt() ?? 1,
        status: j['status'] as String,
        mp4Url: j['mp4_url'] as String?,
        durationSeconds: (j['duration_seconds'] as num?)?.toInt(),
      );
}

class TripDaySummary {
  final String id;
  final String date;
  final String? theme;
  final int photoCount;
  final bool hasApprovedVideo;

  TripDaySummary({
    required this.id,
    required this.date,
    this.theme,
    required this.photoCount,
    required this.hasApprovedVideo,
  });

  factory TripDaySummary.fromJson(Map<String, dynamic> j) => TripDaySummary(
        id: j['id'] as String,
        date: j['date'] as String,
        theme: j['theme'] as String?,
        photoCount: (j['photo_count'] as num?)?.toInt() ?? 0,
        hasApprovedVideo: j['has_approved_video'] as bool? ?? false,
      );
}

class TripDay {
  final String id;
  final String tripId;
  final String date;
  final String? theme;
  final String? weather;
  final String? tourManager;
  final String? voiceoverScript;
  final List<ItineraryItem> items;
  final int photoCount;
  final VideoRender? latestVideo;

  TripDay({
    required this.id,
    required this.tripId,
    required this.date,
    this.theme,
    this.weather,
    this.tourManager,
    this.voiceoverScript,
    required this.items,
    required this.photoCount,
    this.latestVideo,
  });

  factory TripDay.fromJson(Map<String, dynamic> j) => TripDay(
        id: j['id'] as String,
        tripId: j['trip_id'] as String,
        date: j['date'] as String,
        theme: j['theme'] as String?,
        weather: j['weather'] as String?,
        tourManager: j['tour_manager'] as String?,
        voiceoverScript: j['voiceover_script'] as String?,
        items: ((j['items'] as List?) ?? [])
            .map((it) => ItineraryItem.fromJson(it as Map<String, dynamic>))
            .toList(),
        photoCount: (j['photo_count'] as num?)?.toInt() ?? 0,
        latestVideo: j['latest_video'] == null
            ? null
            : VideoRender.fromJson(j['latest_video'] as Map<String, dynamic>),
      );
}
