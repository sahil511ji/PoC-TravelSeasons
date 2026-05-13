class FaceTag {
  final String id;
  final String? userId;
  final String? name;
  final double? confidence;
  final String source;
  final List<double> bbox;

  FaceTag({
    required this.id,
    this.userId,
    this.name,
    this.confidence,
    required this.source,
    required this.bbox,
  });

  factory FaceTag.fromJson(Map<String, dynamic> j) => FaceTag(
        id: j['id'] as String,
        userId: j['user_id'] as String?,
        name: j['name'] as String?,
        confidence: (j['confidence'] as num?)?.toDouble(),
        source: j['source'] as String? ?? 'auto',
        bbox: ((j['bbox'] as List?) ?? [])
            .map((v) => (v as num).toDouble())
            .toList(),
      );
}

class Photo {
  final String id;
  final String url;
  final String status;
  final int? width;
  final int? height;
  final String uploadedAt;
  final String? takenAt;
  final String? itineraryItemId;
  final List<FaceTag> faces;

  Photo({
    required this.id,
    required this.url,
    required this.status,
    this.width,
    this.height,
    required this.uploadedAt,
    this.takenAt,
    this.itineraryItemId,
    required this.faces,
  });

  factory Photo.fromJson(Map<String, dynamic> j) => Photo(
        id: j['id'] as String,
        url: j['url'] as String,
        status: j['status'] as String,
        width: (j['width'] as num?)?.toInt(),
        height: (j['height'] as num?)?.toInt(),
        uploadedAt: j['uploaded_at'] as String,
        takenAt: j['taken_at'] as String?,
        itineraryItemId: j['itinerary_item_id'] as String?,
        faces: ((j['faces'] as List?) ?? [])
            .map((f) => FaceTag.fromJson(f as Map<String, dynamic>))
            .toList(),
      );
}
