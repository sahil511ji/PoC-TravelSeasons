class EnrolledUser {
  final String id;
  final String name;
  final String? email;
  final bool hasSelfie;
  final String? selfieUrl;

  EnrolledUser({
    required this.id,
    required this.name,
    this.email,
    required this.hasSelfie,
    this.selfieUrl,
  });

  factory EnrolledUser.fromJson(Map<String, dynamic> j) => EnrolledUser(
        id: j['id'] as String,
        name: j['name'] as String,
        email: j['email'] as String?,
        hasSelfie: j['has_selfie'] as bool? ?? false,
        selfieUrl: j['selfie_url'] as String?,
      );
}
