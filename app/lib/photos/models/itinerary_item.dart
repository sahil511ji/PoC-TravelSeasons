class ItineraryItem {
  final String id;
  final int position;
  final String? startTime;
  final String? endTime;
  final String title;
  final String? description;
  final int importance;
  final int photoCount;

  ItineraryItem({
    required this.id,
    required this.position,
    this.startTime,
    this.endTime,
    required this.title,
    this.description,
    required this.importance,
    required this.photoCount,
  });

  factory ItineraryItem.fromJson(Map<String, dynamic> j) => ItineraryItem(
        id: j['id'] as String,
        position: (j['position'] as num?)?.toInt() ?? 0,
        startTime: j['start_time'] as String?,
        endTime: j['end_time'] as String?,
        title: j['title'] as String,
        description: j['description'] as String?,
        importance: (j['importance'] as num?)?.toInt() ?? 5,
        photoCount: (j['photo_count'] as num?)?.toInt() ?? 0,
      );
}
