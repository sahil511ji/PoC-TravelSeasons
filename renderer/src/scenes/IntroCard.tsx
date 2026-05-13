import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig, spring } from 'remotion';
import { theme } from '../theme';

/**
 * Opening card:
 *   "Travel Seasons" small uppercase  (top)
 *   ────                              gold rule
 *   "Day 3 · 14 Oct 2026"             eyebrow gold uppercase
 *   "Old & New Singapore"             huge Fraunces serif title
 *
 * Radial brand-green gradient background. Staggered fade-up.
 */
export const IntroCard: React.FC<{
  brandName: string;       // "Travel Seasons"
  eyebrow: string;         // "Day 3 · 14 Oct 2026"
  title: string;           // "Old & New Singapore"
}> = ({ brandName, eyebrow, title }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const wordmarkO = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 22 });
  const ruleO = spring({ frame: frame - 8, fps, config: { damping: 200 }, durationInFrames: 22 });
  const eyebrowO = spring({ frame: frame - 14, fps, config: { damping: 200 }, durationInFrames: 22 });
  const titleO = spring({ frame: frame - 20, fps, config: { damping: 200 }, durationInFrames: 26 });

  const outOpacity = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );

  const ruleW = interpolate(ruleO, [0, 1], [0, 48]);
  const titleY = interpolate(titleO, [0, 1], [24, 0]);

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at center, ${theme.brandGreenLight} 0%, ${theme.brandGreen} 55%, ${theme.brandGreenDeep} 100%)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        opacity: outOpacity,
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            fontFamily: theme.inter,
            fontWeight: 500,
            fontSize: 13,
            letterSpacing: '0.45em',
            textTransform: 'uppercase',
            color: theme.gold,
            opacity: wordmarkO,
          }}
        >
          {brandName}
        </div>
        <div
          style={{
            width: ruleW,
            height: 1,
            background: theme.gold,
            margin: '22px 0',
            opacity: ruleO,
          }}
        />
        <div
          style={{
            fontFamily: theme.inter,
            fontWeight: 400,
            fontSize: 16,
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: theme.cream,
            opacity: eyebrowO,
          }}
        >
          {eyebrow}
        </div>
        <div
          style={{
            fontFamily: theme.fraunces,
            fontWeight: 500,
            fontSize: 76,
            lineHeight: 1.08,
            letterSpacing: '-0.025em',
            color: theme.white,
            marginTop: 22,
            maxWidth: 1000,
            opacity: titleO,
            transform: `translateY(${titleY}px)`,
            textShadow: '0 8px 32px rgba(0,0,0,0.30)',
          }}
        >
          {title}
        </div>
      </div>
    </AbsoluteFill>
  );
};
