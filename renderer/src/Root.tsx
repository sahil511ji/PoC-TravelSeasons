import React from 'react';
import { Composition, registerRoot } from 'remotion';
import { Recap } from './compositions/Recap';
import { RenderSpec } from './types';

const sample: RenderSpec = {
  videoRenderId: 'sample',
  dayTitle: 'Old & New Singapore',
  daySubtitle: 'Day 3 · 14 Oct 2026',
  photos: [
    { url: 'https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=1280', title: 'Chinatown walking tour', importance: 5 },
    { url: 'https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=1280', title: 'Maxwell Food Centre', importance: 6 },
    { url: 'https://images.unsplash.com/photo-1538678867871-5d0b46cb5fcf?w=1280', title: 'Cloud Forest Dome', importance: 9 },
    { url: 'https://images.unsplash.com/photo-1573843981267-be1999ff37cd?w=1280', title: 'Marina Bay SkyPark', importance: 7 },
    { url: 'https://images.unsplash.com/photo-1555899434-94d1368aa7af?w=1280', title: 'Banana Leaf Apolo', importance: 10 },
  ],
  voiceoverUrl: '',
  musicUrl: '',
  targetSeconds: 30,
  voiceoverDurationSec: 30,
  fps: 30,
  brandColor: '#0E5C4A',
  endCardText: 'Travel Seasons',
  width: 1280,
  height: 720,
};

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="Recap"
        component={Recap}
        durationInFrames={Math.round(sample.targetSeconds * sample.fps)}
        fps={sample.fps}
        width={sample.width}
        height={sample.height}
        defaultProps={sample}
        calculateMetadata={({ props }) => {
          const secs = props.voiceoverDurationSec ?? props.targetSeconds ?? 30;
          return {
            durationInFrames: Math.max(1, Math.round(secs * props.fps)),
            fps: props.fps,
            width: props.width,
            height: props.height,
          };
        }}
      />
    </>
  );
};

registerRoot(Root);
