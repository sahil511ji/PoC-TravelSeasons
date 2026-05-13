"""ElevenLabs TTS wrapper."""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)


class TTSError(Exception):
    pass


# Some preset voice IDs from ElevenLabs (English, warm, female).
# "Bella" — warm, soft English female. Good for senior-friendly recap.
DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"   # Sarah


def synthesize(text: str, voice_id: str | None = None) -> bytes:
    """Returns MP3 audio bytes of `text` spoken by the given (or default) voice."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise TTSError("ELEVENLABS_API_KEY not set in .env")
    if not text.strip():
        raise TTSError("empty TTS text")

    vid = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    headers = {
        "xi-api-key": api_key,
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
