"""Remotion renderer wrapper — calls the local Node service.

The Node service runs at REMOTION_RENDERER_URL (default http://localhost:3001)
and exposes:
    GET  /health             — returns {ok: true, service: "renderer"}
    POST /render             — body: RenderSpec JSON; returns MP4 bytes
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)


class RemotionError(Exception):
    pass


def _base_url() -> str:
    return os.environ.get("REMOTION_RENDERER_URL", "http://localhost:3001").rstrip("/")


def is_available(timeout: float = 2.0) -> bool:
    """Cheap health probe — returns True if the renderer answers."""
    try:
        r = httpx.get(f"{_base_url()}/health", timeout=timeout)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:  # noqa: BLE001
        return False


def render(spec: dict, timeout: float = 600.0) -> bytes:
    """POST the render spec to the Node service, return MP4 bytes.

    Raises RemotionError on non-200 or empty response.
    """
    url = f"{_base_url()}/render"
    with httpx.Client(timeout=timeout) as c:
        r = c.post(url, json=spec)
    if r.status_code != 200:
        raise RemotionError(f"renderer {r.status_code}: {r.text[:400]}")
    ctype = r.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        raise RemotionError(f"renderer returned JSON instead of MP4: {r.text[:400]}")
    if not r.content:
        raise RemotionError("renderer returned empty body")
    log.info("[remotion] received %d bytes", len(r.content))
    return r.content
