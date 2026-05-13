import path from 'path';
import fs from 'fs';
import os from 'os';
import crypto from 'crypto';
import { fileURLToPath } from 'url';
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { RenderSpec } from './types';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let _bundlePromise: Promise<string> | null = null;

async function getBundle(): Promise<string> {
  if (!_bundlePromise) {
    console.log('[render] bundling Remotion project (first run ~20s)...');
    _bundlePromise = bundle({
      entryPoint: path.resolve(__dirname, 'Root.tsx'),
      onProgress: (p) => {
        if (p % 25 === 0 || p === 100) console.log(`[render] bundle ${p}%`);
      },
    });
  }
  return _bundlePromise;
}

// Concurrency mutex — Remotion + headless Chromium is heavy.
let _busy: Promise<unknown> = Promise.resolve();
async function withMutex<T>(fn: () => Promise<T>): Promise<T> {
  const prev = _busy;
  let release: () => void = () => {};
  _busy = new Promise<void>((r) => { release = r; });
  await prev;
  try {
    return await fn();
  } finally {
    release();
  }
}

export async function renderRecap(spec: RenderSpec): Promise<string> {
  return withMutex(async () => {
    const bundled = await getBundle();

    // Pre-fetch word timings ONCE in Node before bundling into Chromium tabs.
    // Otherwise every parallel tab refetches independently, killing render speed.
    if (spec.timingUrl && !spec.wordTimings) {
      try {
        const res = await fetch(spec.timingUrl);
        if (res.ok) spec.wordTimings = await res.json();
      } catch (e) {
        console.warn('[render] timing.json fetch failed, captions disabled:', (e as Error).message);
      }
    }

    const totalSeconds = spec.voiceoverDurationSec ?? spec.targetSeconds ?? 30;
    const durationInFrames = Math.max(1, Math.round(totalSeconds * spec.fps));

    const composition = await selectComposition({
      serveUrl: bundled,
      id: 'Recap',
      inputProps: spec as unknown as Record<string, unknown>,
    });

    const outPath = path.join(
      os.tmpdir(),
      `recap-${spec.videoRenderId || crypto.randomBytes(4).toString('hex')}-${Date.now()}.mp4`,
    );

    console.log(`[render] start: id=${spec.videoRenderId} frames=${durationInFrames} photos=${spec.photos.length}`);

    await renderMedia({
      composition: {
        ...composition,
        durationInFrames,
        width: spec.width,
        height: spec.height,
        fps: spec.fps,
      },
      serveUrl: bundled,
      codec: 'h264',
      outputLocation: outPath,
      inputProps: spec as unknown as Record<string, unknown>,
      // gl: 'angle' = DirectX 11 GPU rasterization (uses the RTX 3050).
      // Without this, Chromium falls back to SwiftShader (CPU software) and
      // CSS blur / backdrop-filter is 5-20x slower.
      chromiumOptions: { headless: true, gl: 'angle' },
      concurrency: '50%',
      hardwareAcceleration: 'if-possible',
      jpegQuality: 75,
      timeoutInMilliseconds: 90000,
      onProgress: ({ progress }) => {
        const pct = Math.round(progress * 100);
        if (pct % 20 === 0) console.log(`[render] ${spec.videoRenderId} ${pct}%`);
      },
    });

    if (!fs.existsSync(outPath)) throw new Error('Output file missing after render');
    console.log(`[render] done: ${outPath}`);
    return outPath;
  });
}
