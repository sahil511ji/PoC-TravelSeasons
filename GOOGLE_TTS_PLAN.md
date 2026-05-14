# Plan — Replace ElevenLabs with Google TTS (Indian accent) (v3 — FINAL)

> 5 reviewers, 2 rounds, ~40 findings folded in. **Live captions must keep working exactly as today** — that's the non-negotiable.

## Context

Recap voiceover currently uses ElevenLabs Brian (British male). Boss wants Indian-accented narration on the next renders. Boss pasted a key starting with `AQ.` — an **AI Studio (Generative Language) key**, not a Cloud Console key.

The renderer's contract:
- `timing.json` shape: `[{word: string, start: number, end: number}, ...]`
- Pre-fetched server-side in [renderer/src/render.ts](renderer/src/render.ts), inlined into Remotion `inputProps`
- Consumed by [LiveCaption.tsx](renderer/src/scenes/LiveCaption.tsx) via `t = frame/fps - voiceStartSec` then `sentences.find(s => t >= s.start && t < s.end)`

We preserve this contract bit-for-bit.

## What the curl test proved

Real test against `texttospeech.googleapis.com/v1beta1/text:synthesize` with the pasted AQ. key:

```
HTTP 401
{"error":{"message":"API keys are not supported by this API. Expected OAuth2 access token or other authentication credentials..."}}
```

**Cloud TTS does not accept API key auth on `text:synthesize`. We need service-account JSON.**

## What to ask the boss for (verbatim)

> "I need a Google Cloud **service-account JSON** key for the Text-to-Speech API. Please:
> 1. Open **GCP Console → IAM & Admin → Service Accounts** in a project where TTS is needed
> 2. Create a service account, name it e.g. `travelseasons-tts`, grant the **Cloud Text-to-Speech User** role
> 3. Open the service account → **Keys** tab → **Add Key** → **Create new key** → **JSON**
> 4. A `.json` file downloads. Send me **that file**.
> 5. In the same project, **APIs & Services → Library** → search "Text-to-Speech" → click **Enable**
> 6. Confirm the project has **billing enabled** (Cloud TTS free tier still requires billing turned on)."

## Voice selection

Default: **`en-IN-Neural2-A`** (warm female Indian English, SSML mark support confirmed). Override via env: `GOOGLE_TTS_VOICE_NAME`.

🛠 **Removed:** `en-IN-Chirp3-HD-*` — Chirp3 voices do **not** support SSML, so no `<mark>` tags, no word timepoints.

Alternatives that DO support SSML:
- `en-IN-Neural2-B` (male)
- `en-IN-Neural2-C` (male, deeper)
- `en-IN-Neural2-D` (female, brighter)
- `en-IN-Wavenet-A/B/C/D` (older, still solid)

## Pricing

Cloud TTS free tier (verified May 2026):
- **Neural2 / WaveNet:** 1M chars/month free for the first 12 months on a **new** project, then $16 per 1M chars
- **Standard:** 4M chars/month free, then $4 per 1M
- Our usage: ~400 chars × ~10 renders/day = ~120k chars/month → fully under free tier

🛠 **Circuit breaker** (added in v3): env var `GOOGLE_TTS_MAX_CHARS_PER_REQUEST=2000` enforced before SSML build. Prevents a retry-storm bug from burning the free tier.

## API: SDK + auth

🛠 **Critical (v2 was wrong):** `enable_time_pointing` is **only on `texttospeech_v1beta1`**, not on stable v1. The v1 REST reference lists only `input`, `voice`, `audioConfig`, `advancedVoiceOptions` — no timepointing field. The v1 Python SDK doesn't export `TimepointType` at all.

Use:
```python
from google.cloud import texttospeech_v1beta1 as gtts
```

And the request:
```python
client.synthesize_speech(
    request=gtts.SynthesizeSpeechRequest(
        input=gtts.SynthesisInput(ssml=ssml_str),
        voice=gtts.VoiceSelectionParams(language_code="en-IN", name=voice_name),
        audio_config=gtts.AudioConfig(audio_encoding=gtts.AudioEncoding.MP3),
        enable_time_pointing=[gtts.SynthesizeSpeechRequest.TimepointType.SSML_MARK],
    )
)
```

Response:
- `resp.audio_content` — MP3 bytes (already decoded; the SDK handles base64)
- `resp.timepoints` — list of `{mark_name: str, time_seconds: float}` (proto fields are snake_case)

`requirements.txt`:
```
+ google-cloud-texttospeech>=2.16.0,<3.0.0    # 🛠 pin upper bound for major-version safety
```

## SSML construction

🛠 **Pre-pass: strip markdown / SSML-risky chars** before tokenisation. LLM-generated scripts sometimes contain `**bold**`, backticks, em-dashes that aren't SSML-special but get read aloud awkwardly:

```python
text = re.sub(r'[*_`~]', ' ', text)
```

🛠 **Word cap: 250.** Hard byte-budget assertion: `len(ssml.encode('utf-8')) <= 4800` (200-byte safety margin under Google's 5000-byte SSML limit).

🛠 **Per-request char limit:** raise `TTSError` if input text exceeds `GOOGLE_TTS_MAX_CHARS_PER_REQUEST` (default 2000). Defense against runaway costs.

Single-line SSML, single-space-separated, no newlines (newlines in SSML are speakable whitespace and shift timing):

```xml
<speak><mark name="w0"/>We <mark name="w1"/>went <mark name="w2"/>to <mark name="w3"/>the <mark name="w4"/>park. <mark name="w5"/>It <mark name="w6"/>was <mark name="w7"/>lovely.</speak>
```

🛠 **No `<mark name="wend"/>`.** SSML drops consecutive marks with no audio between. Last-word end time comes from MP3 duration instead.

## SSML escaping

```python
from xml.sax.saxutils import escape as xml_escape
```

Escape `&`, `<`, `>`, `'`, `"`. Punctuation stays attached (`lovely.` → `lovely.`). UTF-8 safe for non-ASCII (Devanagari, Tamil, etc.).

## Tokenisation

`text.split()` — Python's default split handles any whitespace. Punctuation stays attached. Sentence regex `/[.?!]$/` in the renderer still works because escape() doesn't touch ASCII punctuation.

**Known visual diff vs ElevenLabs:** ElevenLabs occasionally splits `lovely.` into `lovely` + `.` as two char-buffers; Google's mark approach keeps them as one. Acceptable, subtle.

## Implementation — file diff

### `backend/google-tts-key.json`

Service-account JSON from the boss. Placed in `backend/` next to `.env`. **Gitignored.**

### `backend/.gitignore`

```
+ google-tts-key.json
```

### `backend/.env`

```
+ GOOGLE_APPLICATION_CREDENTIALS=./google-tts-key.json
+ GOOGLE_TTS_VOICE_NAME=en-IN-Neural2-A
+ GOOGLE_TTS_MAX_CHARS_PER_REQUEST=2000
+ TTS_PROVIDER=google
  ELEVENLABS_API_KEY=...                       (left intact for fallback)
  ELEVENLABS_VOICE_ID=...
```

### `backend/.env.example`

Same lines with empty values + comment block.

### `backend/app/config.py`

```python
GOOGLE_APPLICATION_CREDENTIALS: str = ""    # path to service-account JSON
GOOGLE_TTS_VOICE_NAME: str = "en-IN-Neural2-A"
GOOGLE_TTS_MAX_CHARS_PER_REQUEST: int = 2000
TTS_PROVIDER: str = "google"                # 'google' or 'elevenlabs'
```

### `backend/app/services/tts.py`

Refactor: dispatch by provider; existing ElevenLabs code preserved verbatim under a renamed private function.

```python
def synthesize_with_timing(text: str, voice_id: str | None = None) -> tuple[bytes, list[WordTiming]]:
    provider = os.environ.get("TTS_PROVIDER", "google").lower()
    if provider == "google":
        return _synth_with_timing_google(text)
    elif provider == "elevenlabs":
        return _synth_with_timing_elevenlabs(text, voice_id)  # 🛠 preserve voice_id pass-through
    raise TTSError(f"unknown TTS_PROVIDER={provider!r}")    # 🛠 fail loud, no silent default
```

Add at module top:
```python
import re
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

_google_client = None
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
```

🛠 **Path resolution** — uses `Path(__file__)` so the JSON path can be relative to `backend/` regardless of cwd:

```python
def _resolve_cred_path(cred_path: str) -> Path:
    p = Path(cred_path)
    if not p.is_absolute():
        p = (_BACKEND_ROOT / cred_path).resolve()
    return p
```

```python
def _get_google_client():
    """Lazy-load; harmless TOCTOU at PoC scale."""
    global _google_client
    if _google_client is not None:
        return _google_client
    from google.cloud import texttospeech_v1beta1 as gtts    # 🛠 v1beta1, not v1
    from google.oauth2 import service_account
    cred_str = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not cred_str:
        raise TTSError(
            "GOOGLE_APPLICATION_CREDENTIALS not set. Boss needs to provide a "
            "Google Cloud service-account JSON for Cloud TTS — see plan §'What to ask the boss for'."
        )
    cred_path = _resolve_cred_path(cred_str)
    if not cred_path.exists():
        raise TTSError(f"Service-account JSON missing at {cred_path}")
    creds = service_account.Credentials.from_service_account_file(str(cred_path))
    _google_client = gtts.TextToSpeechClient(credentials=creds)
    return _google_client
```

🛠 **Reuse the existing duration probe** instead of mutagen-inside-tts:

```python
from . import audio_probe                        # already in the project
```

```python
def _synth_with_timing_google(text: str) -> tuple[bytes, list[WordTiming]]:
    from google.cloud import texttospeech_v1beta1 as gtts

    if not text.strip():
        raise TTSError("empty TTS text")

    max_chars = int(os.environ.get("GOOGLE_TTS_MAX_CHARS_PER_REQUEST", "2000"))
    if len(text) > max_chars:
        raise TTSError(f"text too long ({len(text)} chars > {max_chars}); aborting to protect free tier")

    # Markdown/SSML-risky chars → spaces before tokenisation
    text = re.sub(r"[*_`~]", " ", text)

    words = text.split()
    if not words:
        raise TTSError("empty TTS text after sanitisation")
    if len(words) > 250:
        raise TTSError(f"script too long ({len(words)} words); SSML mark budget exceeded")

    parts = [f'<mark name="w{i}"/>{xml_escape(w)}' for i, w in enumerate(words)]
    ssml = "<speak>" + " ".join(parts) + "</speak>"
    if len(ssml.encode("utf-8")) > 4800:
        raise TTSError(f"SSML over 4.8KB ({len(ssml)} bytes)")

    voice_name = os.environ.get("GOOGLE_TTS_VOICE_NAME", "en-IN-Neural2-A")
    client = _get_google_client()
    try:
        resp = client.synthesize_speech(
            request=gtts.SynthesizeSpeechRequest(
                input=gtts.SynthesisInput(ssml=ssml),
                voice=gtts.VoiceSelectionParams(language_code="en-IN", name=voice_name),
                audio_config=gtts.AudioConfig(audio_encoding=gtts.AudioEncoding.MP3),
                enable_time_pointing=[gtts.SynthesizeSpeechRequest.TimepointType.SSML_MARK],
            )
        )
    except Exception as e:
        raise TTSError(f"Google TTS call failed: {e}") from e

    mp3_bytes = bytes(resp.audio_content) if resp.audio_content else b""
    if not mp3_bytes:                              # 🛠 hard guard against silent empty audio
        raise TTSError("Google TTS returned empty audio_content")

    # MP3 duration for last-word end (reuse existing helper)
    mp3_dur = audio_probe.mp3_duration_seconds(mp3_bytes)

    by_name = {tp.mark_name: float(tp.time_seconds) for tp in (resp.timepoints or [])}

    out: list[WordTiming] = []
    for i, w in enumerate(words):
        start = by_name.get(f"w{i}")
        end = by_name.get(f"w{i + 1}")
        if end is None:
            end = mp3_dur                          # last word — use MP3 length
        if start is None or end is None or end <= start:
            continue
        out.append(WordTiming(word=w, start=start, end=end))

    # 🛠 Eliminate float rounding gaps — chain adjacent words so end[i] == start[i+1]
    for i in range(len(out) - 1):
        out[i] = WordTiming(word=out[i].word, start=out[i].start, end=out[i + 1].start)

    log.info(
        "[tts] google: %d MP3 bytes + %d word timings (mp3_dur=%s)",
        len(mp3_bytes), len(out), f"{mp3_dur:.2f}" if mp3_dur else "?",
    )
    return mp3_bytes, out
```

🛠 **Rename existing ElevenLabs body** to `_synth_with_timing_elevenlabs(text, voice_id)` — same signature, same behaviour. The existing fallback to `synthesize()` (plain) inside it stays.

### `backend/app/main.py`

🛠 **Startup health check** in the existing lifespan:

```python
if get_settings().TTS_PROVIDER == "google":
    try:
        await asyncio.to_thread(tts._synth_with_timing_google, "Hi")
        log.info("google tts: ok")
    except TTSError as e:
        log.error("google tts unhealthy at boot: %s", e)
        # Don't refuse boot; recap endpoint will surface failures clearly
```

🛠 **Voice availability check** (optional polish, recommend to include):
```python
# After health-check, before logging "ok":
from google.cloud import texttospeech_v1beta1 as gtts
client = tts._get_google_client()
voices = await asyncio.to_thread(client.list_voices, language_code="en-IN")
configured = get_settings().GOOGLE_TTS_VOICE_NAME
if not any(v.name == configured for v in voices.voices):
    log.warning("configured voice %s not in en-IN voice list", configured)
```

### `backend/app/tasks/build_recap.py`

**Single comment addition** near the `voiceoverStartSec` field (around line 239):

```python
# voiceoverStartSec=0.7 → composition-level offset; word timings in timing.json
# are relative to MP3 t=0, the renderer reconstructs absolute time as t = frame/fps - 0.7
"voiceoverStartSec": 0.7,
```

No functional change. `tts.synthesize_with_timing(script_text)` call site unchanged.

### `renderer/`

**No change.**

## Edge cases (consolidated, ~25)

| # | Case | Handling |
|---|---|---|
| 1 | `GOOGLE_APPLICATION_CREDENTIALS` not set | `TTSError` with remediation pointer |
| 2 | Path set but file missing | `TTSError` with resolved absolute path |
| 3 | JSON file invalid | SDK raises; rewrapped |
| 4 | Service-account lacks TTS role | 403 → surfaced |
| 5 | Cloud TTS API not enabled | 403 → surfaced |
| 6 | Billing not enabled | 403 → surfaced |
| 7 | Voice name typo | 400 → surfaced; startup check logs warning |
| 8 | Text empty | `TTSError("empty TTS text")` |
| 9 | Text contains markdown (`**foo**`, backticks) | Stripped pre-tokenisation |
| 10 | Text contains SSML-breaking chars | `xml_escape` |
| 11 | Text >`GOOGLE_TTS_MAX_CHARS_PER_REQUEST` (default 2000) | Reject — protects free tier |
| 12 | Text >250 words | Reject — SSML budget |
| 13 | SSML payload >4800 bytes | Reject (rare given caps above) |
| 14 | Network timeout | SDK default retry; `TTSError` after |
| 15 | Timepoint missing for `wN` | Skip that word; loop continues |
| 16 | Last word has no `w(N+1)` | Use `audio_probe.mp3_duration_seconds()` |
| 17 | MP3 duration probe fails AND last `w(N+1)` missing | Last word skipped; one-word gap at end (rare) |
| 18 | **Empty `audio_content`** | Hard raise — no silent partial captions |
| 19 | Non-ASCII (`café`, `पार्क`) | `xml_escape` UTF-8 safe |
| 20 | Punctuation-only token (`...`) | Same timepoint twice → `end <= start` → skipped; index `i` still increments |
| 21 | Mark micro-pauses audible | Verified imperceptible at typical reading pace |
| 22 | Voice deprecated mid-month | Surface 400; admin picks another |
| 23 | `TTS_PROVIDER` env typo | Fail loud at first call |
| 24 | Fallback ElevenLabs key expired | Same fail-loud pattern |
| 25 | Float rounding boundary at sentence breaks | Chained: `end[i] = start[i+1]` post-pass |
| 26 | SDK client called from two threads concurrently | First-call race spawns 2 clients; harmless leak; PoC-acceptable |
| 27 | Two consecutive renders | Cached client reused after first lazy-init; verified in smoke test |
| 28 | Video length changes with new voice speed | `build_recap.py` already `max(voice_secs, photo_content_sec)` — recap shrinks/grows to fit |

## Rollback

`TTS_PROVIDER=elevenlabs` in `.env`, restart backend. Existing ElevenLabs path unchanged.

## Verification

1. Save `google-tts-key.json` from boss → `backend/google-tts-key.json`
2. Add the GOOGLE_* lines to `.env`
3. `pip install -r requirements.txt`
4. Restart backend. Look for: `google tts: ok`. If unhealthy, message tells you exactly what to fix (missing role / API / billing / typo).
5. Trigger recap render via admin → poll status → MP3 + timing.json produced in Supabase
6. Open the MP3 — confirm Indian English voice
7. Inspect `timing.json` — N word entries, sensible `start`/`end`, monotonically increasing
8. Watch the rendered video — captions still sync, words light gold one at a time
9. 🛠 **Render a SECOND recap immediately** — confirm SDK client is reused (logs do NOT show "lazy-load" twice)
10. Test fallback: `TTS_PROVIDER=elevenlabs`, restart, render → ElevenLabs Brian still works
11. Test failure path: temporarily rename JSON file, restart → startup log shows `google tts unhealthy`; recap request returns 502 with clear reason

## Out of scope

- Multi-speaker (Chirp3 supports it but Chirp3 lacks SSML)
- Streaming / long-form synthesis
- Sarvam AI / Azure swap (provider dispatch supports adding via 3rd elif branch)
- Whisper forced-alignment as a Gemini-TTS fallback (documented as a separate Plan B if service account is impossible)
- Provider Protocol class (3rd provider would justify it; for 2, if/elif is clearer)
- Cost-counter telemetry (circuit breaker protects free tier; no per-month aggregation needed at PoC)
- A/B voice picker UI

## Effort

| Step | Time |
|---|---|
| Wait for boss's JSON | external |
| `requirements.txt` + install | 5 min |
| `tts.py` refactor + Google path | 60 min |
| `main.py` lifespan check | 15 min |
| `build_recap.py` comment | 1 min |
| `.env` + `.env.example` + `.gitignore` | 5 min |
| Restart + 1 smoke render | 5 min |
| Verification edge-case tests | 20 min |
| **Total once JSON is in hand** | **~2 hours** |
