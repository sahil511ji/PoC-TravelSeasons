import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../models/question.dart';

class ReviewScreen extends StatelessWidget {
  final String title;
  final GameRound round;

  const ReviewScreen({super.key, required this.title, required this.round});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(title: Text('$title · review')),
      body: ListView.builder(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
        itemCount: round.questions.length,
        itemBuilder: (_, i) {
          final q = round.questions[i];
          final pickedIdx = round.userAnswers[i];
          final correct = pickedIdx == q.correctIndex;
          return Container(
            margin: const EdgeInsets.only(bottom: 16),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      correct ? Icons.check_circle_rounded : Icons.cancel_rounded,
                      color: correct ? AppColors.brandGreen : const Color(0xFFE03131),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Question ${i + 1}',
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textSecondary,
                        letterSpacing: 0.6,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  q.prompt,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                ),
                if (q.imageUrl != null) ...[
                  const SizedBox(height: 12),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: AspectRatio(
                      aspectRatio: 16 / 10,
                      child: CachedNetworkImage(
                        imageUrl: q.imageUrl!,
                        fit: round.gameId == 'guess_the_flag' ? BoxFit.contain : BoxFit.cover,
                        placeholder: (_, __) => Container(color: AppColors.surfaceMuted),
                        errorWidget: (_, __, ___) => Container(color: AppColors.surfaceMuted),
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                _row('Correct answer', q.correctAnswer, AppColors.brandGreen),
                const SizedBox(height: 4),
                _row(
                  'Your answer',
                  pickedIdx == null ? '—' : q.options[pickedIdx],
                  correct ? AppColors.brandGreen : const Color(0xFFE03131),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _row(String label, String value, Color color) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 120,
          child: Text(
            label,
            style: const TextStyle(fontSize: 14, color: AppColors.textSecondary),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: color),
          ),
        ),
      ],
    );
  }
}
