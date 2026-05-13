# PoC — AI Daily Recap Video Pipeline

**Project:** Travel Seasons mobile app
**Audience:** Developer working on PoC 1 (AI daily video)
**Status:** Pre-build PoC phase
**Author:** Nitin · Ekam Apps

---

## What we're building

For every day of a trip, the Tour Manager (TM) uploads raw clips + photos. An AI pipeline turns them into a short narrated recap video (~30 seconds). An admin reviews and publishes. The customer sees the published video in their live trip view.

This PoC validates the pipeline end-to-end on **one real day's data** (Singapore Day 3, sample provided separately).

---

## Stack

| Layer | Tool | Why |
|---|---|---|
| Script generation | **Claude / GPT-4o API** | Turn itinerary text into voiceover script |
| Voiceover (TTS) | **Google Cloud TTS** with `en-IN-Neural2-A` voice | Indian English, warm female, very cheap |
| Word-level timing | Google TTS SSML marks + `enableTimePointing` | For caption sync |
| Composition + render | **Remotion** (React-based programmatic video) | Full control, cheap, captions native |
| Render at scale | **Remotion Lambda** on AWS | Parallel rendering, ~$0.05 per video |
| Storage | S3 for input clips + output MP4 | Standard |
| Admin review queue | Web UI (already designed in prototype: `admin/video-review.html`) | Approve / reject / regenerate flow |

**Why Remotion and not Shotstack:** Same skill set as the prototype (React), open-source, full creative control, 5-10× cheaper at scale, native captions support.

**Why Google TTS and not ElevenLabs (for now):** 20× cheaper, voice quality good enough to validate the pipeline. We'll upgrade to ElevenLabs (or Ankita voice clone) in V1.5.

---

## Pipeline flow

```
[Itinerary text from TM]
       ↓ (LLM script generation)
[Voiceover script ~80 words]
       ↓ (Google TTS API with SSML marks)
[audio.mp3 + timing.json (word-level)]
       ↓
       ↓ (combine with photos/video clips + music)
[Remotion composition renders]
       ↓ (Remotion Lambda)
[recap.mp4]
       ↓
[Admin review queue — approve/reject/regenerate]
       ↓ (on approve)
[Customer sees in live trip view]
```

---

## Step-by-step code

### 1. Script generation (LLM call)

```
You are a senior-friendly travel narrator for Travel Seasons,
an Indian tour operator for travellers aged 60+.

Given this day's itinerary, write a 30-second voiceover script
(around 75-80 words).

Tone: warm, gentle, slightly nostalgic, never excited or salesy.
Use short sentences. Don't oversell.
Include 1-2 specific moments by name (a person, a dish, a place).
End with a one-line teaser of tomorrow.

Itinerary:
[paste itinerary text]
```

Output: ~80-word narration string.

### 2. Generate audio + timing (`scripts/tts.mjs`)

```js
import { TextToSpeechClient } from '@google-cloud/text-to-speech';
import fs from 'fs/promises';

const client = new TextToSpeechClient();

async function generateAudio(scriptText, outDir = 'public') {
  const words = scriptText.split(/\s+/).filter(Boolean);
  const ssml = '<speak>' +
    words.map((w, i) => `<mark name="${i}"/>${w}`).join(' ') +
    '</speak>';

  const [response] = await client.synthesizeSpeech({
    input: { ssml },
    voice: { languageCode: 'en-IN', name: 'en-IN-Neural2-A' },
    audioConfig: {
      audioEncoding: 'MP3',
      speakingRate: 0.95,
      effectsProfileId: ['headphone-class-device'],
    },
    enableTimePointing: ['SSML_MARK'],
  });

  await fs.writeFile(`${outDir}/audio.mp3`, response.audioContent);

  const timing = response.timepoints.map((tp, i) => {
    const idx = parseInt(tp.markName, 10);
    const nextStart = response.timepoints[i + 1]?.timeSeconds ?? tp.timeSeconds + 0.4;
    return { word: words[idx], start: tp.timeSeconds, end: nextStart };
  });

  await fs.writeFile(`${outDir}/timing.json`, JSON.stringify(timing, null, 2));
}
```

Output: `audio.mp3` + `timing.json` in `public/`.

### 3. Remotion composition (`src/RecapVideo.tsx`)

```tsx
import { AbsoluteFill, Audio, Img, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import timing from '../public/timing.json';

const photos = ['photo1.jpg', 'photo2.jpg', 'photo3.jpg', 'photo4.jpg', 'photo5.jpg'];

export const RecapVideo = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  const currentWord = timing.find(t => currentTime >= t.start && currentTime < t.end);
  const phraseSize = 5;
  const idx = currentWord ? timing.indexOf(currentWord) : 0;
  const currentPhrase = timing
    .slice(Math.floor(idx / phraseSize) * phraseSize, Math.floor(idx / phraseSize) * phraseSize + phraseSize)
    .map(t => t.word).join(' ');

  const totalSec = timing[timing.length - 1].end + 0.5;
  const totalFrames = Math.ceil(totalSec * fps);

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Audio src={staticFile('audio.mp3')} />

      {photos.map((photo, i) => {
        const dur = Math.floor(totalFrames / photos.length);
        return (
          <Sequence key={photo} from={i * dur} durationInFrames={dur}>
            <Img src={staticFile(photo)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            <AbsoluteFill style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.8) 0%, transparent 50%)' }} />
          </Sequence>
        );
      })}

      <div style={{
        position: 'absolute', bottom: 80, left: 40, right: 40,
        textAlign: 'center', color: '#fff', fontSize: 42, fontWeight: 700,
        textShadow: '0 2px 12px rgba(0,0,0,0.8)',
      }}>{currentPhrase}</div>
    </AbsoluteFill>
  );
};
```

### 4. Render

```bash
# Preview
npx remotion preview

# Render locally
npx remotion render DailyRecap out/video.mp4

# Or production: Remotion Lambda (parallel)
npx remotion lambda render DailyRecap
```

---

## Test input (sample itinerary)

Use the file: **`sample-itinerary-singapore-day3.md`** (shared separately in the same folder).

It contains:
- Realistic Day 3 itinerary for a senior Singapore tour
- Group context, mood, sensory beats
- Suggested filmable moments (ranked)
- Suggested voiceover script (you can compare your AI output against this)
- Asset inventory (photos + clips we'll provide)
- Expected output spec
- Anti-patterns to avoid (generic tour-video feel, fast cuts, robotic voice)

Run your pipeline on this and produce a video we can review against the spec.

---

## Real test assets

We'll send these separately via WeTransfer:

- ~30 photos from a real Bhutan trip (Lakshmi's TM upload)
- 2 short video clips
- (For PoC use this Singapore Day 3 itinerary; we'll provide matching Singapore footage if needed)

For now, use stock images or your own photos that roughly match the itinerary beats — quality of pipeline matters more than asset perfection at this stage.

---

## Acceptance criteria

Tick all of these before calling the PoC done:

- [ ] One end-to-end run: itinerary text in → MP4 out
- [ ] Audio is in `en-IN-Neural2-A` voice, sounds warm + gentle (play it for a senior if possible)
- [ ] Captions stay in sync with audio (test with random skipping in the player)
- [ ] Video is ~30 seconds, 8-12 visual cuts, photos transition cleanly
- [ ] Captions are large, high-contrast, readable on phone (60+ eyes)
- [ ] Background music plays under voiceover (ducked appropriately)
- [ ] Pipeline can be re-run with different itinerary text and produces a different video
- [ ] Output works in both 9:16 (in-app) and 16:9 (sharing) aspect ratios
- [ ] You can show me how to swap one input photo for another and re-render

---

## Out of scope for this PoC

- TM mobile upload UI (REST endpoint OK)
- Admin review web page (we have the design in prototype/v2/admin/video-review.html; just give us an API hook)
- Multi-language voiceover (English only for PoC)
- Voice cloning (Ankita's voice — V1.5 enhancement)
- Music licensing for production (use any royalty-free track)
- Auto-captions in Hindi or regional languages
- Pre-trip / post-trip variants

---

## Deliverables

1. **Working repo** — README with setup, run instructions, env variables
2. **Sample output MP4** — generated from the Singapore Day 3 sample itinerary
3. **Brief notes** on:
   - What surprised you
   - What's risky for production
   - What you'd change if doing it again
4. **List of any open questions** that need our (Ekam + TS) input before V1 build

Send everything via WhatsApp summary + repo link + sample MP4 link.

---

## Reference links

| What | URL |
|---|---|
| Remotion docs | https://www.remotion.dev/docs/ |
| Remotion Lambda (cloud render) | https://www.remotion.dev/docs/lambda |
| Google Cloud TTS docs | https://cloud.google.com/text-to-speech/docs |
| Google TTS Indian voices | https://cloud.google.com/text-to-speech/docs/voices (filter `en-IN`, `hi-IN`) |
| SSML marks for timing | https://cloud.google.com/text-to-speech/docs/ssml#mark |
| Anthropic Claude API | https://docs.anthropic.com/ |
| Existing prototype | https://travelseasons.ekamapps.com/v2/ |
| Existing admin video-review UI | https://travelseasons.ekamapps.com/v2/admin/video-review.html |

---

## Open questions for you to think about

While building, please form opinions on:

1. Can a senior viewer tell the voice is AI-generated? Compare against ElevenLabs as a control.
2. What's the longest single visual cut that feels natural (we'd argue 4 sec for the "hero shot")?
3. How do you handle missing assets (e.g. only 5 photos for a day with 6 beats)?
4. What's the failure mode if Google TTS API is down — fallback to local TTS?
5. How fast can the pipeline produce a video from text-to-MP4? (target: under 5 minutes including render)

---

## Communication

- **WhatsApp** for daily questions
- **Demo as soon as one end-to-end run works** — even if rough
- **Flag blockers immediately** — don't sit on them

The PoC is about validating the approach, not about being beautiful. Get to "working end-to-end" first, then polish.
