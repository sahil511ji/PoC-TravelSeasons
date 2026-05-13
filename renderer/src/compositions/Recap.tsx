import React from 'react';
import { AbsoluteFill, Audio, Sequence, useVideoConfig } from 'remotion';
import { PhotoScene } from '../scenes/PhotoScene';
import { TitleOverlay } from '../scenes/TitleOverlay';
import { IntroCard } from '../scenes/IntroCard';
import { EndCard } from '../scenes/EndCard';
import { theme } from '../theme';
import { RenderSpec } from '../types';

const MOTIONS = ['zoomIn', 'panRight', 'zoomOut', 'panLeft', 'panUp', 'zoomIn', 'panDown', 'zoomOut'] as const;

const INTRO_SECONDS = 3;
const OUTRO_SECONDS = 3;
const PHOTO_OVERLAP_RATIO = 0.18;   // 18% overlap between consecutive photos for crossfade
const MIN_PHOTO_SECONDS = 2.0;       // hard floor — senior-friendly readable
const MAX_PHOTO_SECONDS = 4.5;

export const Recap: React.FC<RenderSpec> = ({
  photos,
  voiceoverUrl,
  musicUrl,
  dayTitle,
  daySubtitle,
  fps,
}) => {
  const { durationInFrames } = useVideoConfig();
  const introFrames = Math.round(INTRO_SECONDS * fps);
  const outroFrames = Math.round(OUTRO_SECONDS * fps);
  const photoContentFrames = Math.max(1, durationInFrames - introFrames - outroFrames);

  // Backend pre-sizes the video to fit every photo at MIN_PHOTO_SECONDS+.
  // We trust it and keep them all.
  const kept = (photos || []).filter((p) => p && p.url);
  const N = Math.max(1, kept.length);
  const minFrames = Math.round(MIN_PHOTO_SECONDS * fps);
  const step = Math.min(
    Math.round(MAX_PHOTO_SECONDS * fps),
    Math.max(minFrames, Math.floor(photoContentFrames / N)),
  );
  const overlapFrames = Math.round(step * PHOTO_OVERLAP_RATIO);
  const photoSceneFrames = step + overlapFrames;

  const photosFrom = introFrames;
  const outroFrom = Math.max(introFrames, durationInFrames - outroFrames);

  return (
    <AbsoluteFill style={{ backgroundColor: theme.brandGreenDeep }}>
      {/* Audio — voiceover starts ~0.7s after intro lifts, music underneath */}
      {musicUrl ? <Audio src={musicUrl} volume={0.16} /> : null}
      {voiceoverUrl ? (
        <Sequence from={Math.round(0.7 * fps)} layout="none">
          <Audio src={voiceoverUrl} volume={1.0} />
        </Sequence>
      ) : null}

      {/* Warm grade applied at composition root for uniformity */}
      <AbsoluteFill style={{ filter: theme.warmGrade }}>
        {/* 1 — Intro card */}
        <Sequence from={0} durationInFrames={introFrames}>
          <IntroCard
            brandName="Travel Seasons"
            eyebrow={daySubtitle || ''}
            title={dayTitle || 'Day'}
          />
        </Sequence>

        {/* 2 — Photo sequences with crossfade overlap.
            Captions only show on the FIRST photo of each unique activity. */}
        {(() => {
          const seenActivities = new Set<string>();
          return kept.map((p, i) => {
            const start = photosFrom + i * step;
            const motion = MOTIONS[i % MOTIONS.length];
            const activityKey = p.title || p.caption || '';
            const isFirstOfActivity = !!activityKey && !seenActivities.has(activityKey);
            if (isFirstOfActivity) seenActivities.add(activityKey);
            // Diary caption is preferred; fall back to title.
            const overlayText = p.caption || p.title;
            const showOverlay = isFirstOfActivity && !!overlayText && p.importance >= 7;
            return (
              <Sequence
                key={`photo-${i}`}
                from={start}
                durationInFrames={photoSceneFrames}
                name={`Photo ${i + 1}`}
              >
                <PhotoScene src={p.url} motion={motion} />
                {showOverlay && (
                  <Sequence
                    from={Math.round(0.20 * photoSceneFrames)}
                    durationInFrames={Math.round(0.62 * photoSceneFrames)}
                  >
                    <TitleOverlay eyebrow={daySubtitle} title={overlayText!} />
                  </Sequence>
                )}
              </Sequence>
            );
          });
        })()}

        {/* 3 — End card */}
        <Sequence from={outroFrom} durationInFrames={outroFrames}>
          <EndCard brandName="Travel Seasons" tagline="Curated · Personal · Yours" />
        </Sequence>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
