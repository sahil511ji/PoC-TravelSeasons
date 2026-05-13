import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig, spring } from 'remotion';
import { theme } from '../theme';

/**
 * Editorial lower-third overlay:
 *   eyebrow ("DAY 3 · SINGAPORE")   ← tracked gold uppercase
 *   ────                             ← 1px × 32px gold hairline rule
 *   Title                            ← Fraunces serif white
 *
 * Staggered fade-up: eyebrow 0ms → rule 200ms → title 350ms.
 * Fades out cleanly in the final 25%.
 */
export const TitleOverlay: React.FC<{
  eyebrow?: string;
  title: string;
}> = ({ eyebrow, title }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const eyebrowO = spring({ frame: frame, fps, config: { damping: 200 }, durationInFrames: 18 });
  const ruleO = spring({ frame: frame - 6, fps, config: { damping: 200 }, durationInFrames: 18 });
  const titleO = spring({ frame: frame - 11, fps, config: { damping: 200 }, durationInFrames: 22 });

  const outOpacity = interpolate(
    frame,
    [durationInFrames - 18, durationInFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );

  const eyebrowY = interpolate(eyebrowO, [0, 1], [10, 0]);
  const titleY = interpolate(titleO, [0, 1], [20, 0]);
  const ruleW = interpolate(ruleO, [0, 1], [0, 32]);

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'flex-start',
        padding: '64px 56px 80px',
        pointerEvents: 'none',
        opacity: outOpacity,
      }}
    >
      <div style={{ maxWidth: '70%' }}>
        {eyebrow && (
          <div
            style={{
              fontFamily: theme.inter,
              fontWeight: 500,
              fontSize: 13,
              letterSpacing: '0.32em',
              color: theme.gold,
              textTransform: 'uppercase',
              opacity: eyebrowO,
              transform: `translateY(${eyebrowY}px)`,
              textShadow: '0 1px 2px rgba(0,0,0,0.55)',
            }}
          >
            {eyebrow}
          </div>
        )}
        <div
          style={{
            width: ruleW,
            height: 1,
            background: theme.gold,
            margin: '16px 0',
            opacity: ruleO,
          }}
        />
        <div
          style={{
            fontFamily: theme.fraunces,
            fontWeight: 500,
            fontSize: 48,
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
            color: theme.white,
            opacity: titleO,
            transform: `translateY(${titleY}px)`,
            textShadow: theme.captionShadow,
          }}
        >
          {title}
        </div>
      </div>
    </AbsoluteFill>
  );
};
