export interface PhotoSpec {
  url: string;
  title?: string;              // descriptive item title — admin-facing
  caption?: string;            // diary-style line shown over the photo in recap
  importance: number;          // 1-10
}

export interface RenderSpec {
  videoRenderId: string;
  dayTitle: string;
  daySubtitle?: string;

  photos: PhotoSpec[];
  voiceoverUrl: string;
  timingUrl?: string;              // URL to word-timing JSON (pre-fetched server-side)
  wordTimings?: { word: string; start: number; end: number }[]; // inlined by render.ts
  voiceoverStartSec?: number;      // seconds the voice MP3 begins after frame 0 (default 0.7)
  musicUrl?: string;

  targetSeconds: number;
  voiceoverDurationSec?: number;
  fps: number;

  brandColor: string;          // "#0E5C4A"
  endCardText: string;         // "Travel Seasons"

  width: number;
  height: number;
}
