# Recap Renderer — dual-engine (Shotstack + Remotion) plan

> Goal: add **Remotion** as a second rendering engine alongside Shotstack. Each video_render gets to choose which engine produces the MP4. Default = Remotion (higher quality). Shotstack stays as a fallback / comparison option.

---

## 1. Context & goals

### Why we're doing this
Shotstack's free-tier output keeps disappointing — watermark, codec quirks, fights over black frames, mediocre quality even when it works. The user has seen Remotion output (React-based, browser-renders to MP4) and wants to try it. We're not removing Shotstack — we're making them switchable so we can compare side-by-side, and demoers can pick the path that produces the best result for their context.

### Success criteria
1. Generate-recap endpoint accepts a `renderer` parameter (`"shotstack"` or `"remotion"`)
2. Both engines produce a stored MP4 in Supabase + a `video_render` row with status flow (queued → rendering → pending_review)
3. Remotion output is meaningfully better visually than Shotstack output on the same source data
4. Admin panel can pick the engine per render
5. Existing Shotstack pipeline keeps working, untouched in behaviour

### Non-goals
- Remotion Lambda / cloud rendering (we run it locally)
- Replacing Shotstack — both coexist
- Building a full template-picker UI (single Remotion comp for now)
- Multi-tenancy concerns (single user, single machine)

---

## 2. Architecture

```
                ┌──────────────────────────┐
                │  Admin (browser, Chrome) │
                │  /admin/#trip-day/:id    │
                └────────────┬─────────────┘
                             │ POST /trip-days/{id}/generate-recap
                             │     body: { renderer: "remotion" | "shotstack" }
                             v
        ┌─────────────────────────────────────────────┐
        │  FastAPI backend (port 8000)               │
        │  ├─ /routers/videos.py     dispatches      │
        │  ├─ /tasks/build_recap.py  orchestrator    │
        │  └─ branches on `renderer`:                │
        │       ├─ shotstack → shotstack.io API      │  (current path)
        │       └─ remotion  → POST localhost:3001   │  (NEW path)
        └────────────────────────┬────────────────────┘
                                 │ POST /render
                                 │   body: full render spec JSON
                                 v
              ┌──────────────────────────────────────┐
              │  Renderer service (Node, port 3001) │
              │  ├─ Express server                   │
              │  ├─ src/Recap.tsx  (composition)     │
              │  └─ @remotion/renderer (CLI/lib)     │
              │     → Chromium headless → MP4 bytes  │
              └──────────────────────────────────────┘
```

### Port allocation
| Service | Port |
|---|---|
| FastAPI backend (existing) | 8000 |
| Renderer service (NEW) | 3001 |
| Admin panel | served by FastAPI at /admin |

### Communication pattern
FastAPI → Renderer: **synchronous HTTP**. Renderer receives a full spec, renders, writes MP4 to a temp file, streams the bytes back. FastAPI uploads to Supabase + writes DB. Renderer never touches Supabase — keeps creds local to one service.

Rationale: simpler, no shared secrets, no race conditions on DB. Trade-off is 30–60s blocking HTTP call to Renderer — fine because the orchestrator already runs in a FastAPI BackgroundTask.

---

## 3. Folder structure

```
c:\travelseason_POC\
├── backend\                            (existing, mostly unchanged)
├── admin\                              (existing, small UI tweak)
├── app\                                (existing, no changes)
└── renderer\                           ← NEW
    ├── package.json
    ├── tsconfig.json
    ├── remotion.config.ts
    ├── .gitignore                      (node_modules, out, .env)
    ├── README.md
    ├── src\
    │   ├── server.ts                   Express + /render endpoint
    │   ├── render.ts                   Wraps @remotion/renderer
    │   ├── Root.tsx                    Remotion registerRoot
    │   ├── compositions\
    │   │   └── Recap.tsx               Main composition
    │   ├── scenes\
    │   │   ├── PhotoScene.tsx          One Ken Burns photo
    │   │   ├── TitleOverlay.tsx        Activity title chip
    │   │   ├── IntroCard.tsx           Optional opening
    │   │   └── EndCard.tsx             "Travel Seasons" outro
    │   ├── theme.ts                    Brand colours, fonts
    │   └── types.ts                    Shared TS interfaces
    └── out\                            (gitignored, render output)
```

---

## 4. Renderer service — Node + Remotion

### 4.1 Dependencies (`package.json`)

```json
{
  "name": "ts-recap-renderer",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "tsx watch src/server.ts",
    "start": "tsx src/server.ts",
    "preview": "remotion preview src/Root.tsx",
    "render": "remotion render src/Root.tsx Recap out/preview.mp4"
  },
  "dependencies": {
    "remotion": "^4.0.0",
    "@remotion/cli": "^4.0.0",
    "@remotion/renderer": "^4.0.0",
    "@remotion/bundler": "^4.0.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "express": "^4.19.0",
    "express-async-handler": "^1.2.0"
  },
  "devDependencies": {
    "@types/express": "^4.17.0",
    "@types/node": "^20.0.0",
    "@types/react": "^18.3.0",
    "typescript": "^5.4.0",
    "tsx": "^4.7.0"
  }
}
```

First-run install:
- `npm install` (~200 MB node_modules)
- `npx remotion browser install` → downloads headless Chromium (~200 MB)
- Total one-time: ~400 MB

### 4.2 Express server (`src/server.ts`)

```typescript
import express from 'express';
import { renderRecap } from './render';

const app = express();
app.use(express.json({ limit: '10mb' }));

app.get('/health', (req, res) => res.json({ ok: true, service: 'renderer' }));

app.post('/render', async (req, res) => {
  try {
    const spec = req.body;        // validated below
    const mp4Path = await renderRecap(spec);
    res.sendFile(mp4Path);        // streams MP4 bytes back, then cleanup
  } catch (e: any) {
    console.error(e);
    res.status(500).json({ error: e.message ?? String(e) });
  }
});

const port = Number(process.env.PORT) || 3001;
app.listen(port, () => console.log(`Renderer listening on ${port}`));
```

### 4.3 Render spec contract

JSON sent from FastAPI:

```typescript
interface RenderSpec {
  // identity
  videoRenderId: string;          // for logging
  dayTitle: string;               // "Old & New Singapore"
  daySubtitle?: string;           // "Day 3 · 14 Oct 2026"

  // assets
  photos: Array<{
    url: string;                  // public Supabase URL
    title?: string;               // activity title (optional)
    importance: number;           // 1-10, used for emphasis
  }>;
  voiceoverUrl: string;
  musicUrl: string;

  // timing
  targetSeconds: number;          // typically 30
  fps: number;                    // 30
  voiceoverDurationSec?: number;  // optional; if provided, video matches it

  // styling
  brandColor: string;             // "#0E5C4A"
  endCardText: string;            // "Travel Seasons"

  // output
  width: number;                  // 1280
  height: number;                 // 720
}
```

### 4.4 The render function (`src/render.ts`)

```typescript
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import path from 'path';
import fs from 'fs';
import os from 'os';
import crypto from 'crypto';

let _bundlePromise: Promise<string> | null = null;

async function getBundle(): Promise<string> {
  // Bundle once, reuse — bundling takes ~20s, renders should be <60s after.
  if (!_bundlePromise) {
    _bundlePromise = bundle({
      entryPoint: path.resolve(__dirname, 'Root.tsx'),
      onProgress: (p) => console.log(`bundle ${p}%`),
    });
  }
  return _bundlePromise;
}

export async function renderRecap(spec: RenderSpec): Promise<string> {
  const bundled = await getBundle();
  const composition = await selectComposition({
    serveUrl: bundled,
    id: 'Recap',
    inputProps: spec,
  });

  // Total frames must match voiceover if provided, else target seconds.
  const totalSeconds = spec.voiceoverDurationSec ?? spec.targetSeconds;
  const durationInFrames = Math.round(totalSeconds * spec.fps);

  const outPath = path.join(
    os.tmpdir(),
    `recap-${spec.videoRenderId || crypto.randomBytes(4).toString('hex')}.mp4`
  );

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
    inputProps: spec,
    chromiumOptions: { headless: true },
  });

  if (!fs.existsSync(outPath)) throw new Error('Output file missing after render');
  return outPath;
}
```

### 4.5 Composition (`src/compositions/Recap.tsx`)

Layout strategy:
- **Audio layer (always-on)**: `<Audio src={voiceoverUrl}/>` + `<Audio src={musicUrl} volume={0.15}/>`
- **Photo sequences** distributed across the duration with crossfade overlap
- **Optional title overlay** sequences anchored to high-importance photos
- **End card** in the final 3 seconds

```tsx
import { AbsoluteFill, Audio, Sequence, useVideoConfig, interpolate, useCurrentFrame } from 'remotion';
import { PhotoScene } from '../scenes/PhotoScene';
import { TitleOverlay } from '../scenes/TitleOverlay';
import { EndCard } from '../scenes/EndCard';

export const Recap: React.FC<RenderSpec> = ({ photos, voiceoverUrl, musicUrl, dayTitle, daySubtitle, brandColor, endCardText, fps }) => {
  const { durationInFrames } = useVideoConfig();
  const endCardFrames = 3 * fps;
  const contentFrames = durationInFrames - endCardFrames;
  const perPhotoFrames = Math.floor(contentFrames / photos.length);
  const overlapFrames = Math.floor(perPhotoFrames * 0.4); // 40% crossfade overlap
  const photoLengthFrames = perPhotoFrames + overlapFrames;

  return (
    <AbsoluteFill style={{ backgroundColor: brandColor }}>
      <Audio src={voiceoverUrl} volume={1} />
      <Audio src={musicUrl} volume={0.15} />

      {photos.map((p, i) => {
        const start = i * perPhotoFrames;
        return (
          <Sequence key={i} from={start} durationInFrames={photoLengthFrames}>
            <PhotoScene
              src={p.url}
              motionKind={MOTIONS[i % MOTIONS.length]}
              brand={brandColor}
            />
            {p.title && p.importance >= 7 && (
              <TitleOverlay text={p.title} fps={fps} />
            )}
          </Sequence>
        );
      })}

      <Sequence from={contentFrames} durationInFrames={endCardFrames}>
        <EndCard text={endCardText} subtitle={dayTitle} brand={brandColor} />
      </Sequence>
    </AbsoluteFill>
  );
};

const MOTIONS = ['zoomIn', 'zoomOut', 'panLeft', 'panRight', 'panUp', 'panDown'] as const;
```

### 4.6 PhotoScene with Ken Burns (`src/scenes/PhotoScene.tsx`)

```tsx
import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill, Img } from 'remotion';

export const PhotoScene: React.FC<{src: string; motionKind: typeof MOTIONS[number]; brand: string}> = ({ src, motionKind, brand }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = frame / durationInFrames;       // 0 → 1

  // Crossfade in (first 15%) + out (last 15%)
  const opacity = interpolate(t, [0, 0.15, 0.85, 1], [0, 1, 1, 0]);

  // Ken Burns transforms
  const scale = motionKind === 'zoomIn' ? interpolate(t, [0, 1], [1.0, 1.15])
              : motionKind === 'zoomOut' ? interpolate(t, [0, 1], [1.15, 1.0])
              : 1.08;                       // slight zoom for pans
  const translateX = motionKind === 'panLeft' ? interpolate(t, [0, 1], [4, -4])
                   : motionKind === 'panRight' ? interpolate(t, [0, 1], [-4, 4])
                   : 0;
  const translateY = motionKind === 'panUp' ? interpolate(t, [0, 1], [4, -4])
                   : motionKind === 'panDown' ? interpolate(t, [0, 1], [-4, 4])
                   : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: brand, opacity }}>
      <Img
        src={src}
        style={{
          width: '100%', height: '100%', objectFit: 'cover',
          transform: `scale(${scale}) translate(${translateX}%, ${translateY}%)`,
          filter: 'saturate(1.15) contrast(1.05) brightness(1.02)',  // boost equivalent
        }}
      />
    </AbsoluteFill>
  );
};
```

### 4.7 Title and end card

Simple AbsoluteFill components with brand-coloured cards, fade in/out via interpolate. Use Inter font (consistent with Flutter app).

### 4.8 Composition registration (`src/Root.tsx`)

```tsx
import { Composition, registerRoot } from 'remotion';
import { Recap } from './compositions/Recap';

export const Root = () => (
  <>
    <Composition
      id="Recap"
      component={Recap}
      durationInFrames={900}        // 30 sec × 30 fps — overridden per render
      fps={30}
      width={1280}
      height={720}
      defaultProps={{
        // Sample data for preview mode
        photos: [{ url: 'https://placehold.co/1280x720', importance: 5 }],
        voiceoverUrl: '',
        musicUrl: '',
        dayTitle: 'Sample Day',
        brandColor: '#0E5C4A',
        endCardText: 'Travel Seasons',
        fps: 30,
        targetSeconds: 30,
        width: 1280,
        height: 720,
      } as any}
    />
  </>
);
registerRoot(Root);
```

This lets `npm run preview` open a live browser preview — designer-friendly iteration.

---

## 5. Backend changes (FastAPI)

### 5.1 New service wrapper (`backend/app/services/remotion.py`)

```python
"""Remotion renderer wrapper — calls the local Node service."""
import os
import httpx

class RemotionError(Exception):
    pass

def _base_url() -> str:
    return os.environ.get("REMOTION_RENDERER_URL", "http://localhost:3001")

def is_available() -> bool:
    try:
        r = httpx.get(f"{_base_url()}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False

def render(spec: dict, timeout: float = 600.0) -> bytes:
    """POSTs the render spec, returns MP4 bytes. Raises on non-200."""
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{_base_url()}/render", json=spec)
    if r.status_code != 200:
        raise RemotionError(f"renderer {r.status_code}: {r.text[:400]}")
    if not r.content or r.headers.get("content-type", "").startswith("application/json"):
        raise RemotionError(f"renderer returned no MP4: {r.text[:400]}")
    return r.content
```

### 5.2 Update schema (`backend/app/schemas.py`)

```python
from typing import Literal

class VideoGenerateRequest(BaseModel):
    voice_id: str | None = None
    music_track: str | None = None
    renderer: Literal["shotstack", "remotion"] = "remotion"   # default = remotion
```

### 5.3 Update model + DB (`backend/app/models.py`)

Add a column to `video_render`:
```python
engine: str = Field(default="shotstack")   # shotstack | remotion
```

Migration via MCP:
```sql
alter table video_render add column if not exists engine text default 'shotstack';
```

### 5.4 Update orchestrator (`backend/app/tasks/build_recap.py`)

Refactor `_run` to dispatch:

```python
async def _run(video_render_id: str) -> None:
    storage = get_storage()
    with session_scope() as s:
        vr = s.get(VideoRender, video_render_id)
        ... # load day, items, photos, validate
        engine = vr.engine or "remotion"

    # 1. TTS (shared by both engines)
    mp3_bytes = tts.synthesize(day.voiceover_script or "")
    voiceover_key = f"voiceovers/{day.id}/v{vr.version}.mp3"
    await storage.put(voiceover_key, mp3_bytes, "audio/mpeg")
    voiceover_url = storage.public_url(voiceover_key)

    # 2. Probe voiceover duration via mutagen or pydub (so video matches audio length)
    voiceover_secs = _probe_mp3_duration(mp3_bytes) or TARGET_SECONDS

    # 3. Render via chosen engine
    if engine == "remotion":
        mp4_bytes = await _render_via_remotion(vr, day, items, photos, voiceover_url, voiceover_secs)
    elif engine == "shotstack":
        mp4_bytes = await _render_via_shotstack(vr, day, items, photos, voiceover_url, voiceover_secs)
    else:
        raise RuntimeError(f"unknown engine: {engine}")

    # 4. Store MP4 + mark pending_review
    mp4_key = f"recap_videos/{vr.trip_day_id}/v{vr.version}.mp4"
    await storage.put(mp4_key, mp4_bytes, "video/mp4")
    with session_scope() as s:
        vr = s.get(VideoRender, video_render_id)
        vr.mp4_storage_path = mp4_key
        vr.duration_seconds = int(round(voiceover_secs))
        vr.status = "pending_review"
        s.commit()
```

The existing Shotstack path moves into `_render_via_shotstack(...)`. The new Remotion path:

```python
async def _render_via_remotion(vr, day, items, photos, voiceover_url, voiceover_secs) -> bytes:
    spec = {
        "videoRenderId": vr.id,
        "dayTitle": day.theme or "Day",
        "daySubtitle": f"{day.date.isoformat()}",
        "photos": [
            {
                "url": storage.public_url(p.storage_path),
                "title": _photo_item_title(p, items),
                "importance": _photo_item_importance(p, items),
            }
            for p in photos
        ],
        "voiceoverUrl": voiceover_url,
        "musicUrl": DEFAULT_MUSIC_URL,
        "targetSeconds": voiceover_secs,
        "voiceoverDurationSec": voiceover_secs,
        "fps": 30,
        "width": 1280,
        "height": 720,
        "brandColor": "#0E5C4A",
        "endCardText": "Travel Seasons",
    }
    # remotion.render is sync (HTTP), wrap in to_thread for async context
    import asyncio
    from ..services import remotion
    return await asyncio.to_thread(remotion.render, spec)
```

### 5.5 Update videos router (`backend/app/routers/videos.py`)

`generate_recap` reads `payload.renderer`, writes it onto the new `VideoRender.engine` field. Existing approve/reject endpoints unchanged.

### 5.6 New backend dep: `mutagen` (to probe MP3 duration)

```
mutagen==1.47.0
```

---

## 6. Admin UI changes

### 6.1 Engine dropdown on "Generate recap" button

In the `tpl-trip-day` template, replace the lone Generate button with:

```html
<div class="form-actions">
  <select id="tday-engine">
    <option value="remotion" selected>Remotion (recommended)</option>
    <option value="shotstack">Shotstack</option>
  </select>
  <button id="tday-generate-recap" class="primary">▶ Generate recap video</button>
</div>
```

In `app.js`, the click handler reads the selected engine and posts:

```js
await api(`/trip-days/${dayId}/generate-recap`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ renderer: document.getElementById('tday-engine').value }),
});
```

### 6.2 Engine badge in render history + videos tab

Each render row shows its engine:

```html
<span class="pill">v3</span>
<span class="pill" style="background:var(--muted-bg)">remotion</span>
<span class="pill ok">approved</span>
```

So admins can compare which engine produced which version visually.

---

## 7. Local dev setup

### One-time install

```powershell
# Renderer side (one-time)
cd c:\travelseason_POC\renderer
npm install
npx remotion browser install   # downloads headless Chromium

# Backend side (one-time)
cd c:\travelseason_POC\backend
.\.venv\Scripts\activate.bat
pip install mutagen==1.47.0
```

### Running (two terminals)

```powershell
# Terminal 1 — backend
cd c:\travelseason_POC\backend
.\.venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — renderer
cd c:\travelseason_POC\renderer
npm run start
```

### Designer iteration (live preview)

```powershell
cd c:\travelseason_POC\renderer
npm run preview            # opens http://localhost:3000 with live Remotion preview
```

Designers can edit `Recap.tsx`, see changes instantly in the browser, no render queue.

### Convenience: a single `run-all.ps1`

```powershell
Start-Process powershell "-NoExit -Command cd backend; .\.venv\Scripts\activate.bat; uvicorn app.main:app --host 0.0.0.0 --port 8000"
Start-Process powershell "-NoExit -Command cd renderer; npm run start"
```

---

## 8. Edge cases — every one I can think of

| # | Edge case | Mitigation |
|---|---|---|
| 1 | Renderer not running when admin clicks Generate (Remotion) | Backend probes `/health` before submit; if down → fail fast with `502: renderer offline` message in `video_render.error`. Admin sees clear error. |
| 2 | Render crashes mid-way (e.g. Chromium OOM, broken image URL) | Renderer's catch-all returns 500 with stderr. FastAPI stores in `video_render.error`, status=failed. |
| 3 | Renderer hangs (slow asset download, infinite loop) | httpx timeout=600s. After 10 min → ReadTimeout → mark failed. |
| 4 | Voiceover MP3 fails to load inside Chromium | Remotion's `<Audio>` fails the render. Catch via `delayRender()` timeout. Fall back to silent video would be ugly — better to fail loudly. |
| 5 | Photo URLs return 404 / slow | Browser shows broken image. Mitigate: pre-verify URLs in backend with `httpx.head()` before sending; skip 404s. Also Remotion's `<Img>` has `delayRender` until image loads — covered. |
| 6 | Concurrent renders on same machine | Remotion handles one at a time well; multiple in parallel could spike memory. Add a `concurrency: 1` lock in renderer (in-memory mutex). Future: queue. |
| 7 | First-time Chromium not installed | `renderRecap` will throw on first call. Setup README explicitly mentions `npx remotion browser install`. Renderer's startup logs check for browser presence and warn. |
| 8 | Port 3001 already in use | Renderer fails to start with clear EADDRINUSE error. Env var `PORT` overrides. |
| 9 | FastAPI runs but Remotion default selected and renderer never started | Backend `is_available()` check returns False → don't queue, return 400: `"renderer unavailable; install + start renderer service, or pick shotstack"`. |
| 10 | Variable photo count (1 photo vs 30 photos) | Composition divides `contentFrames` by `photos.length`. With 1 photo: 27s static. With 30 photos: 0.9s each → too fast. Clamp `perPhotoFrames` to min 30 frames (1s), trim photos if count exceeds budget. Pick by importance descending. |
| 11 | Voiceover longer than target seconds | `voiceoverDurationSec` from mutagen wins → composition runs for that duration. Music + photos fill the same duration. |
| 12 | Voiceover shorter than photos can fit | Trim photos by importance, keep top N that fit. |
| 13 | No photos in the day (rare) | Render an end-card-only video with voiceover + music. Or refuse and surface error. Plan: refuse with clear message. |
| 14 | No voiceover script | Already validated before TTS call — endpoint returns 400. No change. |
| 15 | Music URL fails | Catch in `<Audio>` and render without music. Or fall back to silent. Plan: log warning, render without music. |
| 16 | Special characters in photo URL (Supabase signed URLs sometimes encode oddly) | Renderer uses URL as-is in `<Img>`. Browser handles standard URL encoding. Test with one tricky URL. |
| 17 | Mixed engine in render history (v1=shotstack, v2=remotion, v3=remotion) | Stored per-row in `engine` column. Admin sees which is which via pill badge. |
| 18 | Backend switched between engines but `_render_via_*` helpers grow stale code | Both helpers must produce the SAME output contract (MP4 bytes). Add a sanity test endpoint that renders both with the same input and stores both for visual comparison. (Future enhancement.) |
| 19 | Remotion bundle is rebuilt every render (slow) | `_bundlePromise` is module-level — bundles once on first render. Subsequent renders reuse. ~20s warmup, fast after. |
| 20 | Hot-reload of Recap.tsx during dev | Renderer dev mode (`tsx watch`) restarts on file change. First render after change re-bundles. OK. |
| 21 | Brand color / fonts not loading in Chromium | Use system-safe fonts ("system-ui", "Helvetica", "Arial") as fallbacks. Embed Inter from Google Fonts via `<link>` in Recap. |
| 22 | Render output file permissions / temp dir full | Renderer writes to `os.tmpdir()` (Windows = `%TEMP%`). Standard. Cleans up after sending. Add try/finally for cleanup even on error. |
| 23 | Renderer crashes silently and FastAPI hangs | httpx timeout handles. Also: renderer has process-level `uncaughtException` handler → log + exit so user sees failure. |
| 24 | Different fps between backend assumption and renderer config | Single source of truth: backend sends `fps: 30` in the spec. Renderer uses spec.fps everywhere. |
| 25 | Aspect ratio mismatch (photo is portrait, video is 16:9) | `objectFit: cover` crops; portrait photos get center-cropped. Acceptable for PoC. Future: detect and add letterbox. |
| 26 | Audio sync drift over 30 seconds | Remotion is frame-accurate (renders frame-by-frame, audio rendered to match). Unlike Shotstack where we saw audio drop entirely. Should be fine. |
| 27 | Repeatedly re-rendering for the same day grows DB with old failed video_renders | Already in current behaviour. Add a cleanup endpoint later if needed. |
| 28 | Admin selects Remotion but renderer down → existing behaviour failure | Frontend pre-checks `/health/renderer` (NEW backend endpoint that proxies to renderer health). If down, disable the Remotion option in dropdown with tooltip. |
| 29 | Both engines using same `recap_videos/{day_id}/v{n}.mp4` path → collision? | No — each gets a different version number, and the engine column distinguishes. |
| 30 | Renderer Windows path issue (Node uses forward slashes; outputLocation needs OS native) | Use `path.join` everywhere in Node. Node handles both on Windows. |

---

## 9. DB migration

Single SQL via MCP:

```sql
alter table video_render add column if not exists engine text default 'shotstack';
```

Existing rows get `'shotstack'` (since that's what produced them). New Remotion-generated rows will be marked `'remotion'`.

---

## 10. Verification (acceptance test)

After implementation:

1. **Renderer health**: `curl http://localhost:3001/health` → `{ok:true,service:'renderer'}`
2. **Backend health**: `curl http://localhost:8000/health` → mode/model JSON
3. **Backend → renderer connectivity**: new endpoint `GET /health/renderer` returns whether renderer is reachable
4. **Live preview works**: `cd renderer && npm run preview` opens http://localhost:3000 showing the sample Recap
5. **Shotstack render still works**: admin → trip-day → engine=Shotstack → Generate → produces v? with engine='shotstack' badge → plays in browser
6. **Remotion render works**: admin → trip-day → engine=Remotion → Generate → produces v? with engine='remotion' badge → plays in browser
7. **Both videos compare visually**: open v?-shotstack vs v?-remotion side by side → Remotion noticeably better quality
8. **Flutter still picks up the latest**: customer's app shows the most-recent approved video regardless of engine
9. **Failure paths**: stop the renderer, click Generate-Remotion → backend returns clear error, status=failed
10. **End-card present**: every render ends with the "Travel Seasons" card for 3 seconds

---

## 11. Rollback / off-switch

If Remotion turns out unreliable:
- Admin can switch the dropdown default back to "shotstack" — single line change
- Or set a backend env var `DEFAULT_RENDERER=shotstack` — single line change
- Renderer service can be left dormant; backend is dispatch-aware

We don't delete Shotstack code. We always have an out.

---

## 12. Implementation order

1. **MCP migration** — add `engine` column to `video_render` (5 min)
2. **Scaffold renderer folder** — package.json, tsconfig, .gitignore (10 min)
3. **Build Recap composition** — Recap.tsx + PhotoScene + TitleOverlay + EndCard (45 min)
4. **Wire Express server** — server.ts + render.ts (20 min)
5. **First local render test** — `npm run render` produces a sample MP4 (10 min)
6. **Backend service wrapper** — `services/remotion.py` (15 min)
7. **Refactor orchestrator** — extract `_render_via_shotstack` and `_render_via_remotion` (30 min)
8. **Update schemas + model + router** — VideoGenerateRequest.renderer, VideoRender.engine (15 min)
9. **Admin UI dropdown + engine badge** (15 min)
10. **Add `GET /health/renderer`** — pre-check before submitting Remotion render (10 min)
11. **End-to-end test both engines** — generate one of each, compare (15 min)
12. **Polish + document in README** (10 min)

**Total estimate: ~3 hours.**

---

## 13. Self-review — first pass

Things I considered but didn't include initially:

- **a)** Probing voiceover duration. Added in §5.4 — without it, the video might be longer than the speech, leaving silent dead air. mutagen handles this.
- **b)** What if Chromium is not installed when first render runs? Added §8.7 — explicit setup step, startup warning.
- **c)** Concurrent renders crashing the box. Added §8.6 — single-flight mutex on renderer.
- **d)** Sharing render-spec types between Node and Python — they'll drift. Mitigation: document the contract in §4.3, keep field names matching. Future: codegen from JSON Schema. Acceptable for PoC.
- **e)** Renderer logs in production — currently stdout. For PoC, fine. Add to README that `npm run start` should ideally run with `pm2` or similar in production.

---

## 14. Self-review — second pass (catching what I missed)

**Found on re-read:**

- **i)** **MP3 streaming in browsers:** Remotion's `<Audio>` may need the audio file fully downloadable, not streamed. Supabase public URLs serve the whole file with proper `Content-Length` and `Accept-Ranges` headers — should be fine. Worth verifying in test 5 of the acceptance plan.
- **ii)** **CORS:** the renderer's Chromium fetches photos + audio from Supabase. Supabase Storage public bucket has permissive CORS by default — confirmed earlier in PoC 2 work. No change needed.
- **iii)** **The order of operations**: bundle once → render many. If the user edits Recap.tsx and restarts the renderer, the bundle promise resets — they'll see a 20-sec delay on the first render. Documented.
- **iv)** **HTTP body size for render spec**: with 30 photos, the JSON spec is maybe 5 KB — trivial. Express body limit set to 10 MB for safety.
- **v)** **Renderer crash recovery**: if Node process dies, the FastAPI BackgroundTask sees a connection error → marks the render failed → admin retries. No orphaned state.
- **vi)** **What about Shotstack render times that exceed Renderer's timeout?**: Renderer timeout (600s) is separate from Shotstack's poll timeout. Each engine has its own timing config. No interference.
- **vii)** **DB column nullability**: I had `engine: str = Field(default="shotstack")` — but old rows pre-migration have NULL. `default 'shotstack'` in the ALTER fixes this. Confirmed in §9.
- **viii)** **Engine badge on Flutter app**: Customer's RecapVideoCard doesn't know about engines and doesn't need to — it just plays the MP4 URL. No change.
- **ix)** **Cleanup of temp MP4 files**: Renderer's `os.tmpdir()` files accumulate. Add an OS-level cron / startup cleanup later if it matters. For PoC: fine.
- **x)** **Process management on Windows**: PowerShell windows don't gracefully kill children. The user has been using `Ctrl+C` consistently. For PoC: fine. Note in README.

All these are addressed or accepted as acceptable PoC risk.

---

## 15. What this does NOT change

- Flutter app: zero changes (it just plays whatever MP4 URL the API returns)
- Face recognition pipeline: zero changes
- Photo upload + EXIF + itinerary matching: zero changes
- Supabase schema (other than the one new column): zero changes
- Existing Shotstack-rendered videos: still play perfectly

---

## 16. Definition of done

- [ ] Renderer service starts cleanly, `/health` returns 200
- [ ] `npm run preview` opens a live preview of the sample Recap
- [ ] Backend's `GET /health/renderer` accurately reports renderer status
- [ ] Admin can choose engine in the dropdown
- [ ] Generating with engine=shotstack works as it did before
- [ ] Generating with engine=remotion produces a noticeably better MP4
- [ ] DB has an `engine` column populated correctly per row
- [ ] Admin renders panel shows engine badge
- [ ] Flutter app plays both engines' MP4s identically (no engine-specific bugs)
- [ ] Failure paths handled (renderer down, render error, asset 404) — none crash the backend
- [ ] README updated with one-time setup + run-both-services instructions
