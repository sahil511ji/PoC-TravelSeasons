# Live captions — implementation plan

> Goal: burn-in word-by-word subtitles that follow the voiceover in the recap video. Implement with **ElevenLabs `/with-timestamps`** now (no card, uses existing key), structured so we can swap to **Google Cloud TTS `en-IN-Neural2-A`** the moment the boss sends the JSON key.

---

## 1. What changes vs current state

| Layer | Now | After |
|---|---|---|
| TTS provider | ElevenLabs (Brian voice) — MP3 only | ElevenLabs `/with-timestamps` — MP3 + per-character timings |
| Stored alongside MP3 | Nothing | `voiceovers/{day_id}/v{n}_timing.json` |
| Recap caption | Activity title (once, on first photo of activity) | Spoken-sentence caption that follows the voiceover word-by-word |
| Caption position | Lower-third, left, Fraunces serif | Bottom-centre, Inter sans, 44px, high-contrast |
| TTS swap to Google later | n/a | One file edit in `services/tts.py` — same `timing.json` shape, renderer unchanged |

---

## 2. Architecture

```
script (Gemini)
     │
     ▼
 ElevenLabs /v1/text-to-speech/{voice_id}/with-timestamps
     │ returns:  audio_base64  +  alignment{characters, char_start_times, char_end_times}
     ▼
  group chars → words → [{word, start, end}, ...]
     │
     ├──► upload MP3       → voiceovers/{day_id}/v{n}.mp3
     └──► upload timing    → voiceovers/{day_id}/v{n}_timing.json
                                  │
                  spec.voiceoverUrl + spec.timingUrl
                                  │
                                  ▼
                       Remotion renderer
                                  │
                       LiveCaption component:
                         - fetch timing.json (delayRender)
                         - group words into sentences
                         - on every frame, find sentence whose words contain
                           currentTime − VOICEOVER_OFFSET
                         - render that sentence at the bottom centre
                                  │
                                  ▼
                                MP4
```

---

## 3. Backend changes — `services/tts.py`

### 3.1 New function `synthesize_with_timing(text)`

Calls `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps`. Returns `(mp3_bytes, timing_list)` where:

```python
timing_list = [
  {"word": "We",        "start": 0.00, "end": 0.18},
  {"word": "walked",    "start": 0.18, "end": 0.55},
  {"word": "through",   "start": 0.55, "end": 0.85},
  ...
]
```

### 3.2 Char → word grouping helper

ElevenLabs returns one entry per CHARACTER (including spaces, punctuation):

```python
chars      = ["W","e"," ","w","a","l","k","e","d","'","s",".", ...]
char_start = [0.00, 0.05, 0.10, 0.10, 0.14, ...]
char_end   = [0.05, 0.10, 0.10, 0.14, 0.20, ...]
```

Algorithm:
- Walk chars. Treat space as word boundary.
- Treat punctuation `.`, `,`, `!`, `?`, `;` attached to the last word as part of that word (keeps `"we walked."` as one word `walked.`).
- Apostrophes inside a word ("Sahil's") are part of the word — only spaces break words.
- For each word: `start = char_start[first_char_index]`, `end = char_end[last_char_index]`.
- Skip words where `end <= start` (alignment glitch).

### 3.3 Save both to storage

```python
mp3_key     = f"voiceovers/{day_id}/v{version}.mp3"
timing_key  = f"voiceovers/{day_id}/v{version}_timing.json"
await storage.put(mp3_key, mp3_bytes, "audio/mpeg")
await storage.put(timing_key, json.dumps(timing_list).encode(), "application/json")
```

### 3.4 Update `tasks/build_recap.py`

Replace:
```python
mp3_bytes = tts.synthesize(script_text)
```
with:
```python
mp3_bytes, timing_list = tts.synthesize_with_timing(script_text)
await storage.put(timing_key, json.dumps(timing_list).encode(), "application/json")
```

Pass `timingUrl` + `voiceoverStartSec` (0.7) in the spec to Remotion:
```python
spec = {
   ...,
   "voiceoverUrl":   storage.public_url(mp3_key),
   "timingUrl":      storage.public_url(timing_key),
   "voiceoverStartSec": 0.7,    # voice begins after intro lifts
}
```

---

## 4. Renderer changes — Remotion

### 4.1 `types.ts`

```ts
export interface RenderSpec {
  ...
  timingUrl?: string;
  voiceoverStartSec?: number;   // default 0.7
}
```

### 4.2 New component `src/scenes/LiveCaption.tsx`

```tsx
import { useState, useEffect, useMemo } from 'react';
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig,
  delayRender, continueRender,
} from 'remotion';
import { theme } from '../theme';

type Word = { word: string; start: number; end: number };
type Sentence = { text: string; start: number; end: number };

const wordsToSentences = (words: Word[]): Sentence[] => {
  const out: Sentence[] = [];
  let buf: Word[] = [];
  for (const w of words) {
    buf.push(w);
    if (/[.?!]$/.test(w.word) || buf.length >= 9) {
      out.push({
        text: buf.map(b => b.word).join(' '),
        start: buf[0].start,
        end: buf[buf.length - 1].end,
      });
      buf = [];
    }
  }
  if (buf.length) {
    out.push({ text: buf.map(b => b.word).join(' '), start: buf[0].start, end: buf[buf.length - 1].end });
  }
  return out;
};

export const LiveCaption: React.FC<{
  timingUrl: string;
  voiceStartSec: number;
}> = ({ timingUrl, voiceStartSec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [words, setWords] = useState<Word[] | null>(null);
  const [handle] = useState(() => delayRender('loading timing.json'));

  useEffect(() => {
    fetch(timingUrl)
      .then(r => r.json())
      .then(t => { setWords(Array.isArray(t) ? t : null); continueRender(handle); })
      .catch(() => { setWords([]); continueRender(handle); });
  }, [timingUrl, handle]);

  const sentences = useMemo(() => (words ? wordsToSentences(words) : []), [words]);

  if (!sentences.length) return null;

  const t = frame / fps - voiceStartSec;  // align to MP3 timeline
  const current = sentences.find(s => t >= s.start && t < s.end);
  if (!current) return null;

  return (
    <AbsoluteFill style={{
      justifyContent: 'flex-end',
      alignItems: 'center',
      padding: '0 80px 90px',
      pointerEvents: 'none',
    }}>
      <div style={{
        fontFamily: theme.inter,
        fontSize: 44,
        fontWeight: 700,
        lineHeight: 1.25,
        color: theme.white,
        textAlign: 'center',
        textShadow: '0 2px 4px rgba(0,0,0,0.85), 0 8px 32px rgba(0,0,0,0.55)',
        padding: '14px 26px',
        borderRadius: 14,
        background: 'rgba(0,0,0,0.32)',
        backdropFilter: 'blur(10px)',
        maxWidth: '85%',
      }}>{current.text}</div>
    </AbsoluteFill>
  );
};
```

### 4.3 Mount in `Recap.tsx`

After the photo sequences, BEFORE the end card sequence (so end card covers the caption when we get to the outro):

```tsx
{timingUrl && (
  <Sequence from={photosFrom} durationInFrames={contentFramesEnd - photosFrom}>
    <LiveCaption timingUrl={timingUrl} voiceStartSec={voiceoverStartSec ?? 0.7} />
  </Sequence>
)}
```

### 4.4 Decision: keep or drop the existing `TitleOverlay`?

Recommendation: **drop it**. Live caption already conveys what's happening — adding the activity title on top is double-text. We can keep it as a 1-sec tiny eyebrow chip if the brief reviewer wants context, but default = drop.

---

## 5. Voiceover offset handling

Current `Recap.tsx`:
```tsx
{voiceoverUrl && (
  <Sequence from={Math.round(0.7 * fps)} layout="none">
    <Audio src={voiceoverUrl} volume={1.0} />
  </Sequence>
)}
```

Voice plays starting at frame `0.7 * fps`. So when frame = `1.0 * fps` (1 second of video), the MP3 has played for only 0.3 seconds. The timing entries are 0-based to the MP3, not to the video.

`LiveCaption` subtracts `voiceStartSec` from the frame's time → the value we look up in `timing.json` is the MP3-relative time. Then the lookup works correctly.

---

## 6. Edge cases & how each is handled

| # | Edge case | Handling |
|---|---|---|
| 1 | ElevenLabs free tier doesn't include `/with-timestamps` | Fallback in `services/tts.py`: catch 4xx → use `synthesize()` (no timings) → return `(mp3, [])`. Renderer with empty timing shows no captions. Log a warning so we can switch to Whisper if needed |
| 2 | Word has internal apostrophe (e.g. `Sahil's`) | Single-word — only spaces are boundaries |
| 3 | Word has trailing punctuation (`walked.`) | Punctuation stays attached. Sentence boundary detected later when grouping into sentences |
| 4 | Long sentence (15+ words) | Cap a "sentence" at 9 words. Long ones split into chunks |
| 5 | Two-word sentence ("Wow. Look.") | Each becomes its own sentence chunk, displays for that brief window |
| 6 | Voice has a silent gap (Gemini's script with `…` or natural pause) | timing has no entry for that gap. `sentences.find()` returns nothing → caption hides briefly. Acceptable. |
| 7 | Video duration > voiceover duration | Beyond voice end, no sentence matches → caption hides automatically. Music plays under, no caption. |
| 8 | `timing.json` URL fails to load | `setWords([])` on error. Render proceeds without captions. Logged. |
| 9 | Frame time before voice starts (frame < 0.7s × fps) | `t = frame/fps - 0.7 < 0` → no sentence matches → no caption shown. Correct behaviour |
| 10 | Timing entry with `end <= start` (alignment glitch) | Filtered out in char→word grouping |
| 11 | Caption text wider than 85% of frame | `maxWidth: 85%` triggers wrap. Line-height 1.25 keeps wrapped lines tight |
| 12 | Backdrop-filter blur not rendered by Chromium in some configs | Falls back to the dark `rgba(0,0,0,0.32)` background alone — still readable |
| 13 | User regenerates without timing.json (stale render) | Old MP4 keeps playing; admin reviews. No backend issue |
| 14 | Special chars in word (em-dash, ellipsis) | Stays as part of word, renders fine in Inter |
| 15 | Sentence boundary in the middle of a word due to TTS rendering | Rare; will look slightly off for 1 frame. Acceptable for PoC |
| 16 | Voice volume / music volume balance | Unchanged from current — music 0.16, voice 1.0 |
| 17 | When TTS swap happens later (Google) | `timing.json` shape stays identical. Renderer changes nothing. `services/tts.py` gets new internal function |

---

## 7. Visual design

- Position: **bottom centre**, 90px from bottom
- Font: **Inter 700**, 44px, line-height 1.25, letter-spacing −0.01em
- Color: white
- Backdrop: `rgba(0,0,0,0.32)` + `backdrop-filter: blur(10px)`
- Padding: 14px 26px, border-radius 14px
- Shadow: `0 2px 4px + 0 8px 32px` (dual-shadow for crispness over any background)
- Max width: 85% of frame
- Wrap behaviour: auto-wraps, centered

Senior-friendly:
- Large (44px on 720p, scales for 1080p)
- High contrast (white on dark frosted backdrop)
- Mid-screen text avoids overlapping photo subjects (most senior portraits have face mid-frame, our caption sits below)
- No animations on the caption itself — just appears/disappears with each sentence

---

## 8. Future Google TTS swap (one file)

When the JSON key arrives:

1. Drop key at `backend/google-tts-key.json`
2. Add to `.env`:
   ```
   GOOGLE_APPLICATION_CREDENTIALS=./google-tts-key.json
   GOOGLE_TTS_VOICE=en-IN-Neural2-A
   ```
3. Inside `services/tts.py`, add `synthesize_with_timing_google()` that returns the SAME `(mp3, timing_list)` tuple shape. Backend picks which provider by an env var like `TTS_PROVIDER=google`.
4. Renderer untouched — `timing.json` shape is identical.

---

## 9. Verification

End-to-end test (after build):

1. ✅ Boot backend + renderer
2. ✅ Generate a recap on the existing day
3. ✅ Watch the MP4 in admin: every spoken sentence appears at the bottom-centre, exactly when narrator speaks the first word of it
4. ✅ When the narrator finishes a sentence, caption hides until the next sentence starts
5. ✅ During intro card and end card, no caption shown (narrator isn't speaking)
6. ✅ Renderer logs show `loading timing.json` once at start, no errors
7. ✅ Inspect Supabase Storage: both `v{n}.mp3` and `v{n}_timing.json` exist for the render

---

## 10. Implementation order

1. (5 min) Add `synthesize_with_timing` to `services/tts.py` + char→word grouping helper
2. (5 min) Update `build_recap.py` to call new method, upload timing.json, pass `timingUrl` + `voiceoverStartSec` in spec
3. (5 min) Update `renderer/src/types.ts` to add new fields
4. (15 min) Build `LiveCaption.tsx`
5. (10 min) Mount it in `Recap.tsx`, drop the old activity title overlay
6. (5 min) Restart both services
7. (5 min) Generate test render, verify

Total: **~50 min**.

---

## 11. Self-review pass 1 — what I missed

1. **`voiceoverStartSec` could change in future.** If we ever move the voice start (e.g. start at 1s after intro instead of 0.7s), captions would drift. Mitigation: backend computes voice offset, passes it explicitly. ✅ Done in §3.4
2. **Sentence-grouping greedy cap at 9 words.** That's arbitrary — chosen so 30-second recaps with ~75 words land at ~8-9 sentences. Tune later based on user feedback.
3. **What if a sentence's words span an unnatural emphasis (e.g. comma pauses)?** I'm only splitting on `.?!`, not commas. Commas stay within a sentence. Acceptable.
4. **timing.json fetch URL must be CORS-accessible from the renderer's Chromium.** Supabase Storage public URLs are CORS-permissive — confirmed in earlier audio/photo work. No change needed.
5. **What about videos with no voiceover at all?** Backend always generates voiceover for the recap, but defensive: if `timingUrl` is missing or empty, `LiveCaption` renders nothing. ✅ Handled
6. **The current end-card has its own timing.** End card starts at `outroFrom`. If timing.json's last word is at, say, 23s, and outro starts at 26s, there's a 3s gap of music with no caption. Looks fine — it's the "tail" we discussed earlier. ✅ Intended.

---

## 12. Self-review pass 2 — what's still uncertain

1. **ElevenLabs free-tier eligibility for `/with-timestamps`.** I'm 95% sure it's not gated to paid plans, but if it returns 402, we fall through to plain MP3 + no captions. The fallback's already in §6 case #1. Worth a quick first-call test.
2. **Char index → word membership when chars include whitespace.** I described splitting on space chars. But if ElevenLabs returns a space character with start/end times, that space's times are between words — we don't include them in either word, just skip. Simpler than I wrote in §3.2. Let me re-check the algorithm:
   ```
   build word buffer "current_word_chars"
   build "current_word_starts" / "current_word_ends"
   walk chars:
     if char is whitespace and current_word non-empty:
       emit word (text=current_word, start=current_word_starts[0], end=current_word_ends[-1])
       reset
     else:
       append char + its start/end times
   at end: emit remaining buffer if any
   ```
   That's correct.
3. **ElevenLabs might return alignment field as `null` for some voices.** If so, we'd need to assume word timing manually (~150 wpm). Defensive: if alignment missing, save empty timing.json and proceed. Caption stays hidden.
4. **Punctuation cluster like `"...what?"` or `"Sahil—again"`** — em-dashes, ellipses. Most readers treat them as separators. I'm treating them as part of the word they're attached to. Could split, but probably fine. Note for follow-up.
5. **Renderer bundle restart.** Adding a new component requires bundling the renderer again. We've already handled this by killing the Node process and restarting — same workflow.

---

## 13. Self-review pass 3 — checking against the boss's brief

From `poc-ai-daily-recap-video.md` acceptance criteria, the items that this plan covers:

- [x] **"Captions stay in sync with audio (test with random skipping in the player)"** — Live captions are derived from per-frame timing lookups, frame-accurate. ✅
- [x] **"Captions are large, high-contrast, readable on phone (60+ eyes)"** — 44px Inter Bold, white on frosted dark, max 85% width. ✅
- [x] **"Voiceover is in `en-IN-Neural2-A` voice"** — NOT today. We'll be on Brian (American) until the Google JSON arrives. Documented in §8 swap path. **Partial / pending**.
- [x] **"Background music plays under voiceover (ducked appropriately)"** — already working, no change. ✅
- [ ] **"Output works in both 9:16 (in-app) and 16:9 (sharing) aspect ratios"** — current is 16:9 only. 9:16 vertical is a separate feature, deferred. **Not in this plan** — note for next iteration.
- [x] **"Audio is in warm + gentle voice"** — ElevenLabs Brian is warm; once we swap to en-IN-Neural2-A it'll match the brief better.

Other brief acceptance items already satisfied by current build: 8-12 visual cuts, photo transitions, music ducked, pipeline re-runnable.

**Conclusion of pass 3:** the plan covers the brief's captions criterion. Voice swap and 9:16 cut are documented as separate future work. No blocking gaps.

---

## 14. What's NOT in this plan (deferred)

- 9:16 vertical render
- Google TTS swap (one-line provider switch when key arrives — described in §8)
- ElevenLabs `with-timestamps` to Whisper fallback if endpoint is gated (described in §6 case #1)
- Caption animation (word-by-word highlighting within a sentence) — could add later
- Multi-language captions (Hindi/Tamil)
- Custom font for captions (using Inter which we already have loaded)

---

## 15. Definition of done

- [ ] `services/tts.py` exposes `synthesize_with_timing(text) → (mp3_bytes, timing_list)`
- [ ] `build_recap.py` uploads `_timing.json` and passes `timingUrl` to Remotion spec
- [ ] `renderer/src/scenes/LiveCaption.tsx` exists and is mounted in `Recap.tsx`
- [ ] Old `TitleOverlay` removed from `Recap.tsx` (or kept as a brief eyebrow — TBD)
- [ ] Both services restart cleanly with no errors
- [ ] Generated MP4 shows live captions matching the voiceover
- [ ] Captions hide during intro (before voice starts) and outro (after voice ends)
- [ ] If TTS endpoint fails, recap still renders without captions (graceful)
- [ ] Documented in `RECAP_RENDERER_PLAN.md` or this plan's §8 for future Google swap
