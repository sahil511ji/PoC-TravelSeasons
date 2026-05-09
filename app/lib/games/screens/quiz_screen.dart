import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../models/question.dart';
import 'results_screen.dart';

class QuizScreen extends StatefulWidget {
  final String title;
  final GameRound round;

  const QuizScreen({super.key, required this.title, required this.round});

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<QuizScreen> {
  int _index = 0;
  int? _selected;
  bool _revealed = false;

  Question get _q => widget.round.questions[_index];
  int get _total => widget.round.questions.length;

  void _onPick(int i) {
    if (_revealed) return;
    setState(() {
      _selected = i;
      _revealed = true;
      widget.round.userAnswers[_index] = i;
    });
  }

  void _next() {
    if (_index < _total - 1) {
      setState(() {
        _index++;
        _selected = null;
        _revealed = false;
      });
    } else {
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => ResultsScreen(title: widget.title, round: widget.round),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        title: Text(widget.title),
        leading: IconButton(
          icon: const Icon(Icons.close_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            _progressBar(),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'Question ${_index + 1} of $_total',
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textSecondary,
                        letterSpacing: 0.6,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _q.prompt,
                      style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                        height: 1.25,
                      ),
                    ),
                    const SizedBox(height: 20),
                    if (_q.imageUrl != null) _imageBlock(_q.imageUrl!),
                    const SizedBox(height: 20),
                    ...List.generate(_q.options.length, (i) => _optionTile(i)),
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

  Widget _progressBar() {
    final pct = (_index + (_revealed ? 1 : 0)) / _total;
    return Container(
      height: 6,
      color: AppColors.surfaceMuted,
      child: Align(
        alignment: Alignment.centerLeft,
        child: FractionallySizedBox(
          widthFactor: pct.clamp(0, 1),
          child: Container(color: AppColors.brandGreen),
        ),
      ),
    );
  }

  Widget _imageBlock(String url) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Container(
        color: Colors.white,
        constraints: const BoxConstraints(maxHeight: 240),
        child: AspectRatio(
          aspectRatio: 16 / 10,
          child: CachedNetworkImage(
            imageUrl: url,
            fit: widget.round.gameId == 'guess_the_flag' ? BoxFit.contain : BoxFit.cover,
            placeholder: (_, __) => Container(color: AppColors.surfaceMuted),
            errorWidget: (_, __, ___) => Container(
              color: AppColors.surfaceMuted,
              child: const Icon(Icons.broken_image_outlined, size: 40),
            ),
          ),
        ),
      ),
    );
  }

  Widget _optionTile(int i) {
    final correct = i == _q.correctIndex;
    final picked = i == _selected;
    Color bg = Colors.white;
    Color border = AppColors.border;
    Color text = AppColors.textPrimary;
    IconData? trailing;

    if (_revealed) {
      if (correct) {
        bg = const Color(0xFFE7F6EE);
        border = AppColors.brandGreen;
        trailing = Icons.check_circle_rounded;
      } else if (picked) {
        bg = const Color(0xFFFCEBEA);
        border = const Color(0xFFE03131);
        trailing = Icons.cancel_rounded;
      }
    } else if (picked) {
      border = AppColors.brandGreen;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: () => _onPick(i),
          child: Container(
            constraints: const BoxConstraints(minHeight: 56),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: border, width: 1.5),
            ),
            child: Row(
              children: [
                Container(
                  width: 30,
                  height: 30,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: AppColors.surfaceMuted,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    String.fromCharCode(65 + i),
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    _q.options[i],
                    style: TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w600,
                      color: text,
                    ),
                  ),
                ),
                if (trailing != null)
                  Icon(trailing, color: border, size: 24),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _bottomBar() {
    final isLast = _index == _total - 1;
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: AppColors.divider)),
      ),
      child: SizedBox(
        height: 54,
        width: double.infinity,
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.brandGreen,
            disabledBackgroundColor: AppColors.surfaceMuted,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          ),
          onPressed: _revealed ? _next : null,
          child: Text(
            isLast ? 'See results' : 'Next question',
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
          ),
        ),
      ),
    );
  }
}
