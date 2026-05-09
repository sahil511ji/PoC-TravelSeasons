import 'json_cache.dart';

class Country {
  final String name;
  final String cca2;
  final String? capital;
  final String region;

  Country({required this.name, required this.cca2, this.capital, required this.region});

  String get flagUrl => 'https://flagcdn.com/w320/${cca2.toLowerCase()}.png';
}

class CountriesService {
  CountriesService._();
  static final CountriesService instance = CountriesService._();

  static const _url =
      'https://restcountries.com/v3.1/all?fields=name,cca2,capital,region';

  List<Country>? _memo;

  Future<List<Country>> loadAll() async {
    if (_memo != null) return _memo!;
    final data = await JsonCache.instance.fetch(url: _url, cacheKey: 'countries_v1');
    final list = (data as List).map<Country?>((raw) {
      final map = raw as Map<String, dynamic>;
      final name = (map['name']?['common'] ?? '').toString();
      final cca2 = (map['cca2'] ?? '').toString();
      final region = (map['region'] ?? '').toString();
      final capRaw = map['capital'];
      final capital = (capRaw is List && capRaw.isNotEmpty) ? capRaw.first.toString() : null;
      if (name.isEmpty || cca2.isEmpty) return null;
      return Country(name: name, cca2: cca2, capital: capital, region: region);
    }).whereType<Country>().toList();
    _memo = list;
    return list;
  }
}
