import 'json_cache.dart';

class Meal {
  final String id;
  final String name;
  final String thumbUrl;
  final String area;

  Meal({required this.id, required this.name, required this.thumbUrl, required this.area});
}

class MealsService {
  MealsService._();
  static final MealsService instance = MealsService._();

  static const _cuisines = <String>[
    'Indian',
    'Italian',
    'Mexican',
    'Japanese',
    'Chinese',
    'French',
    'Thai',
    'Greek',
    'Spanish',
    'British',
    'American',
    'Turkish',
  ];

  Map<String, List<Meal>>? _memo;

  List<String> get cuisines => List.unmodifiable(_cuisines);

  Future<Map<String, List<Meal>>> loadAll() async {
    if (_memo != null) return _memo!;
    final result = <String, List<Meal>>{};
    for (final area in _cuisines) {
      final data = await JsonCache.instance.fetch(
        url: 'https://www.themealdb.com/api/json/v1/1/filter.php?a=$area',
        cacheKey: 'meals_$area',
      );
      final raw = (data as Map<String, dynamic>)['meals'];
      if (raw is! List) continue;
      final meals = raw.map<Meal?>((m) {
        final map = m as Map<String, dynamic>;
        final id = (map['idMeal'] ?? '').toString();
        final name = (map['strMeal'] ?? '').toString();
        final thumb = (map['strMealThumb'] ?? '').toString();
        if (id.isEmpty || name.isEmpty || thumb.isEmpty) return null;
        return Meal(id: id, name: name, thumbUrl: thumb, area: area);
      }).whereType<Meal>().toList();
      if (meals.isNotEmpty) result[area] = meals;
    }
    _memo = result;
    return result;
  }
}
