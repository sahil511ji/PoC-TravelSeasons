import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../models/question.dart';
import '../services/wallet_service.dart';
import 'review_screen.dart';

class ResultsScreen extends StatefulWidget {
  final String title;
  final GameRound round;

  const ResultsScreen({super.key, required this.title, required this.round});

  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  CreditAwardResult? _award;
  bool _claiming = true;

  @override
  void initState() {
    super.initState();
    _claim();
  }

  Future<void> _claim() async {
    final result = await WalletService.instance.awardIfEligible(
      idempotencyKey: '${widget.round.gameId}-${widget.round.roundId}',
      score: widget.round.correctCount,
      total: widget.round.total,
    );
    if (!mounted) return;
    setState(() {
      _award = result;
      _claiming = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final score = widget.round.correctCount;
    final total = widget.round.total;
    final passed = score >= 4;

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        title: Text(widget.title),
        leading: IconButton(
          icon: const Icon(Icons.close_rounded),
          onPressed: () => Navigator.of(context).popUntil((r) => r.isFirst),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
                child: Column(
                  children: [
                    Container(
                      width: 88,
                      height: 88,
                      decoration: BoxDecoration(
                        color: passed ? const Color(0xFFE7F6EE) : AppColors.surfaceMuted,
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        passed ? Icons.emoji_events_rounded : Icons.sentiment_neutral_rounded,
                        size: 48,
                        color: passed ? AppColors.brandGreen : AppColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      passed ? 'Well done!' : 'Good try!',
                      style: const TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'You scored $score out of $total',
                      style: const TextStyle(fontSize: 17, color: AppColors.textSecondary),
                    ),
                    const SizedBox(height: 28),
                    _walletCard(),
                    const SizedBox(height: 16),
                    _scoreBreakdown(),
                  ],
                ),
              ),
            ),
            _bottomBar(),
          ],
        ),
      ),
    );
  }

  Widget _walletCard() {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: AppColors.accentGoldLight,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.account_balance_wallet_rounded,
                color: Color(0xFF6B4A12)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: _claiming
                ? const Text('Updating wallet…',
                    style: TextStyle(color: AppColors.textSecondary))
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _award!.awarded
                            ? '+${_award!.creditsAdded} credits'
                            : 'No credits this time',
                        style: const TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        _award!.reason,
                        style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          _pill('Balance ${_award!.newBalance}'),
                          const SizedBox(width: 8),
                          _pill('🔥 ${_award!.streakDays}-day streak'),
                        ],
                      ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }

  Widget _pill(String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
        ),
      ),
    );
  }

  Widget _scoreBreakdown() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: List.generate(widget.round.questions.length, (i) {
          final q = widget.round.questions[i];
          final pickedIdx = widget.round.userAnswers[i];
          final correct = pickedIdx == q.correctIndex;
          return Padding(
            padding: EdgeInsets.only(bottom: i == widget.round.questions.length - 1 ? 0 : 10),
            child: Row(
              children: [
                Icon(
                  correct ? Icons.check_circle_rounded : Icons.cancel_rounded,
                  color: correct ? AppColors.brandGreen : const Color(0xFFE03131),
                  size: 22,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Q${i + 1} · ${q.correctAnswer}',
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
          );
        }),
      ),
    );
  }

  Widget _bottomBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: AppColors.divider)),
      ),
      child: Row(
        children: [
          Expanded(
            child: SizedBox(
              height: 52,
              child: OutlinedButton(
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: AppColors.brandGreen, width: 1.4),
                  foregroundColor: AppColors.brandGreen,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => ReviewScreen(title: widget.title, round: widget.round),
                )),
                child: const Text('View answers',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: SizedBox(
              height: 52,
              child: FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.brandGreen,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Play again',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
