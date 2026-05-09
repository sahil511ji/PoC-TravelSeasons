class Question {
  final String prompt;
  final String? imageUrl;
  final List<String> options;
  final int correctIndex;

  Question({
    required this.prompt,
    this.imageUrl,
    required this.options,
    required this.correctIndex,
  });

  String get correctAnswer => options[correctIndex];
}

class GameRound {
  final String gameId;
  final String roundId;
  final List<Question> questions;
  final List<int?> userAnswers;

  GameRound({
    required this.gameId,
    required this.roundId,
    required this.questions,
  }) : userAnswers = List<int?>.filled(questions.length, null);

  int get correctCount =>
      List.generate(questions.length, (i) => i)
          .where((i) => userAnswers[i] == questions[i].correctIndex)
          .length;

  int get total => questions.length;

  bool get isComplete => userAnswers.every((a) => a != null);
}
