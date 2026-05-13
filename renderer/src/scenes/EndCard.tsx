import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig, spring } from 'remotion';
import { theme } from '../theme';

/**
 * Closing card:
 *   "Travel Seasons"  Fraunces serif white
 *   ────              gold rule
 *   "Travel · Memories · Tomorrow"  tracked gold eyebrow
 */
export const EndCard: React.FC<{
  brandName: string;         // "Travel Seasons"
  tagline?: string;          // optional small line, e.g. "Tomorrow — Sentosa"
}> = ({ brandName, tagline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleO = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 30 });
  const ruleO = spring({ frame: frame - 10, fps, config: { damping: 200 }, durationInFrames: 26 });
  const tagO = spring({ frame: frame - 18, fps, config: { damping: 200 }, durationInFrames: 26 });

  const ruleW = interpolate(ruleO, [0, 1], [0, 56]);
  const titleY = interpolate(titleO, [0, 1], [16, 0]);

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at center, ${theme.brandGreenLight} 0%, ${theme.brandGreen} 55%, ${theme.brandGreenDeep} 100%)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
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
            fontFamily: theme.fraunces,
            fontWeight: 500,
            fontSize: 64,
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
            color: theme.white,
            opacity: titleO,
            transform: `translateY(${titleY}px)`,
            textShadow: '0 8px 32px rgba(0,0,0,0.30)',
          }}
        >
          {brandName}
        </div>
        <div
          style={{
            width: ruleW,
            height: 1,
            background: theme.gold,
            margin: '20px 0',
            opacity: ruleO,
          }}
        />
        <div
          style={{
            fontFamily: theme.inter,
            fontWeight: 500,
            fontSize: 13,
            letterSpacing: '0.40em',
            color: theme.gold,
            textTransform: 'uppercase',
            opacity: tagO,
          }}
        >
          {tagline || 'Curated · Personal · Yours'}
        </div>
      </div>
    </AbsoluteFill>
  );
};
