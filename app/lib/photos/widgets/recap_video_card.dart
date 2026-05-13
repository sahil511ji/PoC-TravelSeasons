import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../theme/app_colors.dart';
import '../models/trip_day.dart';

class RecapVideoCard extends StatefulWidget {
  final VideoRender video;
  final String dayTitle;

  const RecapVideoCard({super.key, required this.video, required this.dayTitle});

  @override
  State<RecapVideoCard> createState() => _RecapVideoCardState();
}

class _RecapVideoCardState extends State<RecapVideoCard> {
  VideoPlayerController? _controller;
  bool _ready = false;
  bool _expanded = false;

  @override
  void didUpdateWidget(covariant RecapVideoCard old) {
    super.didUpdateWidget(old);
    if (old.video.mp4Url != widget.video.mp4Url) {
      _controller?.dispose();
      _controller = null;
      _ready = false;
      _expanded = false;
    }
  }

  Future<void> _initIfNeeded() async {
    if (_controller != null) return;
    final url = widget.video.mp4Url;
    if (url == null) return;
    final c = VideoPlayerController.networkUrl(Uri.parse(url));
    _controller = c;
    await c.initialize();
    if (!mounted) return;
    setState(() => _ready = true);
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final v = widget.video;
    final isApproved = v.status == 'approved';
    final url = v.mp4Url;

    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.brandGreen,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          children: [
            if (_expanded && url != null) ...[
              AspectRatio(
                aspectRatio: 16 / 9,
                child: !_ready
                    ? Container(color: Colors.black, child: const Center(child: CircularProgressIndicator(color: Colors.white)))
                    : Stack(
                        alignment: Alignment.bottomCenter,
                        children: [
                          VideoPlayer(_controller!),
                          VideoProgressIndicator(_controller!, allowScrubbing: true),
                        ],
                      ),
              ),
              if (_ready)
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    IconButton(
                      onPressed: () {
                        setState(() {
                          if (_controller!.value.isPlaying) {
                            _controller!.pause();
                          } else {
                            _controller!.play();
                          }
                        });
                      },
                      iconSize: 36,
                      color: Colors.white,
                      icon: Icon(_controller!.value.isPlaying ? Icons.pause_circle : Icons.play_circle),
                    ),
                  ],
                ),
            ] else
              InkWell(
                onTap: url == null
                    ? null
                    : () async {
                        setState(() => _expanded = true);
                        await _initIfNeeded();
                        _controller?.play();
                      },
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
                  child: Row(
                    children: [
                      Container(
                        width: 52,
                        height: 52,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.18),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          isApproved ? Icons.play_arrow_rounded : Icons.hourglass_top_rounded,
                          color: Colors.white,
                          size: 28,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              isApproved
                                  ? 'Watch your ${v.durationSeconds ?? 30}-second recap'
                                  : 'Recap is ${v.status.replaceAll('_', ' ')}',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '${widget.dayTitle} · auto-curated by AI',
                              style: const TextStyle(
                                color: Colors.white70,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
