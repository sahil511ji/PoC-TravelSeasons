"""Probe audio duration so the video matches the voiceover length.

Supports both MP3 (ElevenLabs path) and WAV (Gemini path). Format is sniffed
from the first few bytes; the right probe is dispatched accordingly.
"""
from __future__ import annotations

import io
import logging
import wave

log = logging.getLogger(__name__)


def _detect_format(audio_bytes: bytes) -> str:
    """Returns 'wav' | 'mp3' | 'unknown' by sniffing magic bytes."""
    if len(audio_bytes) < 12:
        return "unknown"
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "wav"
    # MP3: ID3 tag header OR raw frame sync (FF Fx)
    if audio_bytes[:3] == b"ID3":
        return "mp3"
    if audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0:
        return "mp3"
    return "unknown"


def wav_duration_seconds(wav_bytes: bytes) -> float | None:
    """Returns duration in seconds for a WAV blob, or None if it can't be read."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate <= 0:
                return None
            return float(frames) / float(rate)
    except (wave.Error, EOFError) as e:
        log.warning("wav duration probe failed: %s", e)
        return None


def mp3_duration_seconds(mp3_bytes: bytes) -> float | None:
    """Returns duration in seconds for an MP3 blob, or None if it can't be read."""
    try:
        from mutagen.mp3 import MP3
    except ImportError:
        log.warning("mutagen not installed — cannot probe MP3 duration")
        return None
    try:
        audio = MP3(io.BytesIO(mp3_bytes))
        return float(audio.info.length)
    except Exception as e:  # noqa: BLE001
        log.warning("mp3 duration probe failed: %s", e)
        return None


def audio_duration_seconds(audio_bytes: bytes) -> float | None:
    """Format-aware duration probe. Sniffs magic bytes then dispatches."""
    fmt = _detect_format(audio_bytes)
    if fmt == "wav":
        return wav_duration_seconds(audio_bytes)
    if fmt == "mp3":
        return mp3_duration_seconds(audio_bytes)
    log.warning("audio_duration_seconds: unknown format, %d bytes", len(audio_bytes))
    return None


def audio_ext_and_mime(audio_bytes: bytes) -> tuple[str, str]:
    """Returns the right (extension, content-type) pair for the bytes.

    Defaults to MP3 when format can't be detected — keeps legacy behaviour.
    """
    fmt = _detect_format(audio_bytes)
    if fmt == "wav":
        return ("wav", "audio/wav")
    return ("mp3", "audio/mpeg")
