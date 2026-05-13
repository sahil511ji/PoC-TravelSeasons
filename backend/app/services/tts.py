"""ElevenLabs TTS wrapper — supports word-level timestamps for live captions."""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


class TTSError(Exception):
    pass


# Preset voice ID (Sarah). Overridable via ELEVENLABS_VOICE_ID.
DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"

# Word boundaries during char→word grouping.
_WHITESPACE = set(" \t\n\r ")


@dataclass
class WordTiming:
    word: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"word": self.word, "start": round(self.start, 3), "end": round(self.end, 3)}


def _voice_id(voice_id: str | None) -> str:
    return voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID


def _api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise TTSError("ELEVENLABS_API_KEY not set in .env")
    return key


def synthesize(text: str, voice_id: str | None = None) -> bytes:
    """Plain MP3 synthesis. Kept for backward compatibility / fallback."""
    if not text.strip():
        raise TTSError("empty TTS text")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{_voice_id(voice_id)}"
    headers = {"xi-api-key": _api_key(), "Content-Type": "application/json", "Accept": "audio/mpeg"}
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


def synthesize_with_timing(
    text: str, voice_id: str | None = None
) -> tuple[bytes, list[WordTiming]]:
    """Returns (mp3_bytes, word_timings).

    Uses ElevenLabs' /with-timestamps endpoint which returns audio + per-character
    alignment in one call. If that endpoint is unavailable (paid plan only?), we
    fall back to plain synthesize() with empty timings so the recap still renders.
    """
    if not text.strip():
        raise TTSError("empty TTS text")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{_voice_id(voice_id)}/with-timestamps"
    headers = {"xi-api-key": _api_key(), "Content-Type": "application/json"}
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
        return synthesize(text, voice_id), []

    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        raise TTSError("ElevenLabs /with-timestamps: non-JSON body") from None

    audio_b64 = data.get("audio_base64") or data.get("audio")
    if not audio_b64:
        raise TTSError("ElevenLabs /with-timestamps: missing audio_base64")
    mp3_bytes = base64.b64decode(audio_b64)

    alignment = data.get("alignment") or data.get("normalized_alignment") or {}
    timings = _alignment_to_words(alignment, source_text=text)
    log.info("[tts] received %d MP3 bytes + %d word timings", len(mp3_bytes), len(timings))
    return mp3_bytes, timings


def _alignment_to_words(alignment: dict, source_text: str) -> list[WordTiming]:
    """Group ElevenLabs character-level alignment into word timings.

    Algorithm: walk chars, accumulate non-whitespace chars into a buffer.
    On whitespace, emit the buffer as one word (start = buffer[0].start,
    end = buffer[-1].end). Skip words where end <= start (alignment glitch).
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
