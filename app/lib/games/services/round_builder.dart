import 'dart:math';

import '../models/question.dart';
import 'countries_service.dart';
import 'meals_service.dart';

class RoundBuilder {
  RoundBuilder._();

  static GameRound buildFlagRound({
    required List<Country> countries,
    int questionCount = 5,
    int? seed,
  }) {
    final rng = Random(seed);
    final pool = List<Country>.from(countries)..shuffle(rng);
    final picks = pool.take(questionCount).toList();

    final questions = <Question>[];
    for (final correct in picks) {
      final distractors = (List<Country>.from(countries)
            ..removeWhere((c) => c.cca2 == correct.cca2)
            ..shuffle(rng))
          .take(3)
          .toList();
      final options = [correct, ...distractors]..shuffle(rng);
      final correctIndex = options.indexWhere((c) => c.cca2 == correct.cca2);
      questions.add(Question(
        prompt: 'Which country does this flag belong to?',
        imageUrl: correct.flagUrl,
        options: options.map((c) => c.name).toList(),
        correctIndex: correctIndex,
      ));
    }

    return GameRound(
      gameId: 'guess_the_flag',
      roundId: DateTime.now().millisecondsSinceEpoch.toString(),
      questions: questions,
    );
  }

  static GameRound buildCuisineRound({
    required Map<String, List<Meal>> mealsByArea,
    int questionCount = 5,
    int? seed,
  }) {
    final rng = Random(seed);
    final areas = mealsByArea.keys.toList();
    if (areas.length < 4) {
      throw StateError('Need at least 4 cuisines to build a round.');
    }

    final allMeals = mealsByArea.entries
        .expand((e) => e.value)
        .toList()
      ..shuffle(rng);

    final usedMealIds = <String>{};
    final questions = <Question>[];

    for (final meal in allMeals) {
      if (questions.length == questionCount) break;
      if (usedMealIds.contains(meal.id)) continue;
      usedMealIds.add(meal.id);

      final wrongAreas = (List<String>.from(areas)..remove(meal.area)..shuffle(rng))
          .take(3)
          .toList();
      final options = [meal.area, ...wrongAreas]..shuffle(rng);
      final correctIndex = options.indexOf(meal.area);

      questions.add(Question(
        prompt: 'Where is "${meal.name}" from?',
        imageUrl: meal.thumbUrl,
        options: options,
        correctIndex: correctIndex,
      ));
    }

    return GameRound(
      gameId: 'cuisine_quiz',
      roundId: DateTime.now().millisecondsSinceEpoch.toString(),
      questions: questions,
    );
  }
}
