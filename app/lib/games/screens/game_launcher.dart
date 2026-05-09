import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../models/question.dart';
import '../services/countries_service.dart';
import '../services/meals_service.dart';
import '../services/round_builder.dart';
import 'quiz_screen.dart';

enum GameKind { guessTheFlag, cuisineQuiz }

class GameLauncher extends StatefulWidget {
  final GameKind kind;
  const GameLauncher({super.key, required this.kind});

  String get _title => switch (kind) {
        GameKind.guessTheFlag => 'Guess the Flag',
        GameKind.cuisineQuiz => 'Cuisine Quiz',
      };

  @override
  State<GameLauncher> createState() => _GameLauncherState();
}

class _GameLauncherState extends State<GameLauncher> {
  Object? _error;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    try {
      final GameRound round;
      if (widget.kind == GameKind.guessTheFlag) {
        final countries = await CountriesService.instance.loadAll();
        round = RoundBuilder.buildFlagRound(countries: countries);
      } else {
        final meals = await MealsService.instance.loadAll();
        round = RoundBuilder.buildCuisineRound(mealsByArea: meals);
      }
      if (!mounted) return;
      final replay = await Navigator.of(context).pushReplacement<bool, void>(
        MaterialPageRoute(builder: (_) => QuizScreen(title: widget._title, round: round)),
      );
      if (!mounted) return;
      if (replay == true) {
        // Replay: rebuild a fresh round.
        Navigator.of(context).pushReplacement(MaterialPageRoute(
          builder: (_) => GameLauncher(kind: widget.kind),
        ));
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(title: Text(widget._title)),
      body: Center(
        child: _error == null
            ? const Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(color: AppColors.brandGreen),
                  SizedBox(height: 16),
                  Text('Loading questions…',
                      style: TextStyle(fontSize: 16, color: AppColors.textSecondary)),
                ],
              )
            : Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.cloud_off_rounded,
                        size: 48, color: AppColors.textSecondary),
                    const SizedBox(height: 12),
                    const Text(
                      "Couldn't load this game",
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      _error.toString(),
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
                    ),
                    const SizedBox(height: 16),
                    FilledButton(
                      style: FilledButton.styleFrom(backgroundColor: AppColors.brandGreen),
                      onPressed: () {
                        setState(() => _error = null);
                        _start();
                      },
                      child: const Text('Try again'),
                    ),
                  ],
                ),
              ),
      ),
    );
  }
}
