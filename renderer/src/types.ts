export interface PhotoSpec {
  url: string;
  title?: string;
  importance: number;          // 1-10
}

export interface RenderSpec {
  videoRenderId: string;
  dayTitle: string;
  daySubtitle?: string;

  photos: PhotoSpec[];
  voiceoverUrl: string;
  musicUrl?: string;

  targetSeconds: number;
  voiceoverDurationSec?: number;
  fps: number;

  brandColor: string;          // "#0E5C4A"
  endCardText: string;         // "Travel Seasons"

  width: number;
  height: number;
}
