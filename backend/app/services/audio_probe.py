"""Probe MP3 duration so the video matches the voiceover length."""
from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)


def mp3_duration_seconds(mp3_bytes: bytes) -> float | None:
    """Returns the duration in seconds, or None if it can't be determined."""
    try:
        from mutagen.mp3 import MP3
        from mutagen import MutagenError
    except ImportError:
        log.warning("mutagen not installed — cannot probe MP3 duration")
        return None
    try:
        audio = MP3(io.BytesIO(mp3_bytes))
        return float(audio.info.length)
    except Exception as e:  # noqa: BLE001
        log.warning("mp3 duration probe failed: %s", e)
        return None
