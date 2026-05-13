import React from 'react';
import { AbsoluteFill, Img, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../theme';

type Motion = 'zoomIn' | 'zoomOut' | 'panLeft' | 'panRight' | 'panUp' | 'panDown';

/**
 * Apple-Memories style photo scene:
 *   1. A blurred + dimmed copy of the photo fills the frame (backdrop).
 *   2. The same photo (contained, max 82%) sits in front with a soft drop shadow.
 *   3. Subtle Ken Burns on the foreground (scale 1.00 → ~1.06 over the clip).
 *   4. Opacity crossfade in/out — overlap is handled by the parent Recap.
 */
export const PhotoScene: React.FC<{
  src: string;
  motion: Motion;
}> = ({ src, motion }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = Math.max(0, Math.min(1, frame / Math.max(1, durationInFrames)));

  // 15-frame crossfade in + out (assuming 30fps clips); plateaus to 1 in the middle.
  const inEnd = 0.18;
  const outStart = 0.82;
  const opacity = interpolate(t, [0, inEnd, outStart, 1], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Very subtle Ken Burns — 6% over the clip, varied direction.
  let scale = 1.04;
  let tx = 0;
  let ty = 0;
  switch (motion) {
    case 'zoomIn':
      scale = interpolate(t, [0, 1], [1.0, 1.06]);
      break;
    case 'zoomOut':
      scale = interpolate(t, [0, 1], [1.06, 1.0]);
      break;
    case 'panLeft':
      tx = interpolate(t, [0, 1], [1.5, -1.5]);
      scale = 1.04;
      break;
    case 'panRight':
      tx = interpolate(t, [0, 1], [-1.5, 1.5]);
      scale = 1.04;
      break;
    case 'panUp':
      ty = interpolate(t, [0, 1], [1.5, -1.5]);
      scale = 1.04;
      break;
    case 'panDown':
      ty = interpolate(t, [0, 1], [-1.5, 1.5]);
      scale = 1.04;
      break;
  }

  // Backdrop drifts gently in the opposite direction (parallax).
  const bgScale = interpolate(t, [0, 1], [1.18, 1.22]);
  const bgTx = -tx * 0.35;
  const bgTy = -ty * 0.35;

  return (
    <AbsoluteFill style={{ opacity, backgroundColor: theme.brandGreenDeep }}>
      {/* Blurred backdrop — same photo */}
      <AbsoluteFill>
        <Img
          src={src}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `scale(${bgScale}) translate(${bgTx}%, ${bgTy}%)`,
            filter: 'blur(38px) brightness(0.55) saturate(1.25)',
            willChange: 'transform',
          }}
        />
        {/* Soft darken so foreground pops */}
        <AbsoluteFill style={{ background: 'rgba(8, 56, 44, 0.30)' }} />
      </AbsoluteFill>

      {/* Foreground — contained, with shadow */}
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            width: '82%',
            height: '82%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transform: `scale(${scale}) translate(${tx}%, ${ty}%)`,
            willChange: 'transform',
            filter: 'drop-shadow(0 30px 60px rgba(0,0,0,0.55))',
          }}
        >
          <Img
            src={src}
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              width: 'auto',
              height: 'auto',
              objectFit: 'contain',
              borderRadius: 18,
            }}
          />
        </div>
      </AbsoluteFill>

      {/* Vignette */}
      <AbsoluteFill
        style={{
          boxShadow: 'inset 0 0 220px rgba(0,0,0,0.55)',
          pointerEvents: 'none',
        }}
      />
    </AbsoluteFill>
  );
};
