class TripMember {
  final String id;
  final String name;
  final String? selfieUrl;

  TripMember({required this.id, required this.name, this.selfieUrl});

  factory TripMember.fromJson(Map<String, dynamic> j) => TripMember(
        id: j['id'] as String,
        name: j['name'] as String,
        selfieUrl: j['selfie_url'] as String?,
      );
}

class Trip {
  final String id;
  final String name;
  final String? startDate;
  final String? endDate;
  final int photoCount;
  final List<TripMember> members;

  Trip({
    required this.id,
    required this.name,
    this.startDate,
    this.endDate,
    required this.photoCount,
    required this.members,
  });

  factory Trip.fromJson(Map<String, dynamic> j) => Trip(
        id: j['id'] as String,
        name: j['name'] as String,
        startDate: j['start_date'] as String?,
        endDate: j['end_date'] as String?,
        photoCount: (j['photo_count'] as num?)?.toInt() ?? 0,
        members: ((j['members'] as List?) ?? [])
            .map((m) => TripMember.fromJson(m as Map<String, dynamic>))
            .toList(),
      );
}
