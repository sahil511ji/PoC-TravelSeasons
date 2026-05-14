"""TTS wrapper — supports word-level timestamps for live captions.

Two providers, dispatched via the TTS_PROVIDER env var:

- ``google_cloud_tts`` (default): Google Cloud Text-to-Speech REST API with
  SSML ``<mark>`` tags + ``enableTimePointing`` — returns MP3 + word
  timepoints in one call. Uses ``GOOGLE_API_KEY`` (a Cloud Console API key
  with Cloud TTS enabled, AIzaSy... prefix).

- ``elevenlabs``: ElevenLabs ``/with-timestamps`` endpoint. Returns MP3 +
  character-level alignment, which we group into words. Emergency fallback.

Public API preserved so callers (``tasks.build_recap``) and the renderer
don't need to change:

    synthesize_with_timing(text) -> (audio_bytes, list[WordTiming])

``audio_bytes`` is MP3 from either provider. The pipeline sniffs the format
via ``audio_probe`` and uploads with the right extension + mime.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import time
from dataclasses import dataclass
from xml.sax.saxutils import escape as xml_escape

import httpx

log = logging.getLogger(__name__)


class TTSError(Exception):
    pass


# ElevenLabs preset voice (Sarah). Override via ``ELEVENLABS_VOICE_ID``.
DEFAULT_ELEVENLABS_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
_WHITESPACE = set(" \t\n\r ")

# Google Cloud TTS — v1beta1 has enableTimePointing; v1 does NOT.
GOOGLE_CLOUD_TTS_URL = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
GOOGLE_CLOUD_TTS_MAX_CHARS = 1800
GOOGLE_CLOUD_TTS_MAX_SSML_BYTES = 4800


@dataclass
class WordTiming:
    word: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"word": self.word, "start": round(self.start, 3), "end": round(self.end, 3)}


# ---------- public entry point ----------

def synthesize_with_timing(
    text: str, voice_id: str | None = None
) -> tuple[bytes, list[WordTiming]]:
    """Returns (audio_bytes, word_timings). audio_bytes is MP3.
    ``voice_id`` only applies to the elevenlabs provider.
    """
    provider = (os.environ.get("TTS_PROVIDER") or "google_cloud_tts").lower()
    if provider == "google_cloud_tts":
        return _synth_with_timing_cloud_tts(text)
    if provider == "elevenlabs":
        return _synth_with_timing_elevenlabs(text, voice_id)
    raise TTSError(f"unknown TTS_PROVIDER={provider!r}")


# ---------- Google Cloud TTS (primary) ----------

def _synth_with_timing_cloud_tts(text: str) -> tuple[bytes, list[WordTiming]]:
    if not text.strip():
        raise TTSError("empty TTS text")
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise TTSError("GOOGLE_API_KEY not set")

    voice = os.environ.get("GOOGLE_TTS_VOICE_NAME", "en-IN-Neural2-A")
    try:
        speaking_rate = float(os.environ.get("GOOGLE_TTS_SPEAKING_RATE", "1.0"))
    except ValueError:
        speaking_rate = 1.0
    speaking_rate = max(0.25, min(4.0, speaking_rate))

    # Strip markdown chars + collapse whitespace so SSML stays clean.
    cleaned = re.sub(r"[*_`~]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        raise TTSError("empty TTS text after sanitisation")
    if len(cleaned) > GOOGLE_CLOUD_TTS_MAX_CHARS:
        raise TTSError(
            f"script too long ({len(cleaned)} chars > {GOOGLE_CLOUD_TTS_MAX_CHARS})"
        )

    words = cleaned.split()
    parts = [f'<mark name="w{i}"/>{xml_escape(w)}' for i, w in enumerate(words)]
    ssml = "<speak>" + " ".join(parts) + "</speak>"
    if len(ssml.encode("utf-8")) > GOOGLE_CLOUD_TTS_MAX_SSML_BYTES:
        raise TTSError(f"SSML too large ({len(ssml)} bytes)")

    body = {
        "input": {"ssml": ssml},
        "voice": {"languageCode": "en-IN", "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": speaking_rate},
        "enableTimePointing": ["SSML_MARK"],
    }
    url = f"{GOOGLE_CLOUD_TTS_URL}?key={key}"

    log.info("[tts] cloud_tts request: voice=%s ssml=%d bytes", voice, len(ssml))
    t0 = time.monotonic()

    # Single bounded retry for 5xx / 429.
    with httpx.Client(timeout=90.0) as c:
        r = c.post(url, json=body)
        if r.status_code in (429, 500, 502, 503, 504):
            log.warning("[tts] cloud_tts %d; retrying once after 2s", r.status_code)
            time.sleep(2.0)
            r = c.post(url, json=body)
    if r.status_code != 200:
        raise TTSError(f"Google Cloud TTS {r.status_code}: {r.text[:400]}")

    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        raise TTSError("Google Cloud TTS: non-JSON response body") from None

    audio_b64 = data.get("audioContent")
    if not audio_b64:
        raise TTSError("Google Cloud TTS: missing audioContent")
    mp3_bytes = base64.b64decode(audio_b64)
    if not mp3_bytes:
        raise TTSError("Google Cloud TTS returned empty audio")

    by_name = {
        tp["markName"]: float(tp["timeSeconds"]) for tp in data.get("timepoints", []) or []
    }

    from . import audio_probe

    mp3_dur = audio_probe.mp3_duration_seconds(mp3_bytes)

    out: list[WordTiming] = []
    for i, w in enumerate(words):
        start = by_name.get(f"w{i}")
        end = by_name.get(f"w{i + 1}", mp3_dur)
        if start is None or end is None or end <= start:
            continue
        out.append(WordTiming(word=w, start=start, end=end))

    elapsed = time.monotonic() - t0
    log.info(
        "[tts] cloud_tts done: %d MP3 bytes + %d word timings in %.2fs",
        len(mp3_bytes), len(out), elapsed,
    )
    return mp3_bytes, out


# ---------- ElevenLabs (emergency fallback) ----------

def _elevenlabs_voice_id(voice_id: str | None) -> str:
    return voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_ELEVENLABS_VOICE_ID


def _elevenlabs_api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise TTSError("ELEVENLABS_API_KEY not set in .env")
    return key


def _synth_plain_elevenlabs(text: str, voice_id: str | None = None) -> bytes:
    """Plain MP3 synthesis fallback when /with-timestamps is unavailable."""
    if not text.strip():
        raise TTSError("empty TTS text")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{_elevenlabs_voice_id(voice_id)}"
    headers = {
        "xi-api-key": _elevenlabs_api_key(),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.75},
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=headers, json=body)
    if r.status_code != 200:
        raise TTSError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    return r.content


def _synth_with_timing_elevenlabs(
    text: str, voice_id: str | None = None
) -> tuple[bytes, list[WordTiming]]:
    """ElevenLabs /with-timestamps -> (mp3_bytes, word_timings)."""
    if not text.strip():
        raise TTSError("empty TTS text")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{_elevenlabs_voice_id(voice_id)}/with-timestamps"
    headers = {"xi-api-key": _elevenlabs_api_key(), "Content-Type": "application/json"}
    body = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.75},
    }
    with httpx.Client(timeout=90.0) as client:
        r = client.post(url, headers=headers, json=body)

    if r.status_code != 200:
        log.warning(
            "ElevenLabs /with-timestamps unavailable (%s); falling back to plain TTS, no captions",
            r.status_code,
        )
        return _synth_plain_elevenlabs(text, voice_id), []

    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        raise TTSError("ElevenLabs /with-timestamps: non-JSON body") from None

    audio_b64 = data.get("audio_base64") or data.get("audio")
    if not audio_b64:
        raise TTSError("ElevenLabs /with-timestamps: missing audio_base64")
    mp3_bytes = base64.b64decode(audio_b64)

    alignment = data.get("alignment") or data.get("normalized_alignment") or {}
    timings = _alignment_to_words(alignment)
    log.info("[tts] elevenlabs: %d MP3 bytes + %d word timings", len(mp3_bytes), len(timings))
    return mp3_bytes, timings


def _alignment_to_words(alignment: dict) -> list[WordTiming]:
    """Group ElevenLabs character-level alignment into word timings.
    Walk chars, accumulate non-whitespace chars; flush on whitespace.
    """
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    n = min(len(chars), len(starts), len(ends))
    if n == 0:
        return []

    words: list[WordTiming] = []
    buf_chars: list[str] = []
    buf_start: float | None = None
    buf_end: float | None = None

    def flush() -> None:
        nonlocal buf_chars, buf_start, buf_end
        if buf_chars and buf_start is not None and buf_end is not None and buf_end > buf_start:
            words.append(WordTiming(word="".join(buf_chars), start=buf_start, end=buf_end))
        buf_chars = []
        buf_start = None
        buf_end = None

    for i in range(n):
        ch = chars[i]
        if ch in _WHITESPACE:
            flush()
            continue
        if buf_start is None:
            buf_start = float(starts[i])
        buf_end = float(ends[i])
        buf_chars.append(ch)
    flush()
    return words


def synthesize(text: str, voice_id: str | None = None) -> bytes:
    """Plain audio only — provider-dispatched. Returns MP3 from either provider."""
    audio_bytes, _ = synthesize_with_timing(text, voice_id)
    return audio_bytes
