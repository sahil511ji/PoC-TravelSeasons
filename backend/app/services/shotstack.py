"""Shotstack render wrapper — submit a JSON timeline, poll until done, return MP4 URL."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ShotstackError(Exception):
    pass


def _env() -> tuple[str, str]:
    api_key = os.environ.get("SHOTSTACK_API_KEY")
    if not api_key:
        raise ShotstackError("SHOTSTACK_API_KEY not set in .env")
    # Sandbox endpoint is free; "stage" or "v1" for production.
    env = os.environ.get("SHOTSTACK_ENV", "stage")  # stage = sandbox (free with watermark)
    return api_key, env


def _base_url(env: str) -> str:
    # New Shotstack API: https://api.shotstack.io/edit/{stage|v1}/...
    return f"https://api.shotstack.io/edit/{env}"


def submit_render(timeline: dict, output: dict | None = None) -> str:
    """Posts a render job, returns the render_id (string).

    `timeline` follows Shotstack's `edit.timeline` schema.
    `output` defaults to MP4 1080p 16:9; pass to override.
    """
    api_key, env = _env()
    url = f"{_base_url(env)}/render"
    output = output or {
        "format": "mp4",
        "resolution": "hd",   # 720p (1280x720). Use 'sd' for free-tier safety.
        "aspectRatio": "16:9",
    }
    body = {"timeline": timeline, "output": output}
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as c:
        r = c.post(url, headers=headers, json=body)
    if r.status_code not in (200, 201):
        raise ShotstackError(f"Shotstack submit {r.status_code}: {r.text[:400]}")
    data = r.json()
    rid = data.get("response", {}).get("id")
    if not rid:
        raise ShotstackError(f"Shotstack response missing id: {data}")
    return rid


def get_status(render_id: str) -> dict[str, Any]:
    """Returns Shotstack render status JSON."""
    api_key, env = _env()
    url = f"{_base_url(env)}/render/{render_id}"
    headers = {"x-api-key": api_key}
    with httpx.Client(timeout=60.0) as c:
        r = c.get(url, headers=headers)
    if r.status_code != 200:
        raise ShotstackError(f"Shotstack status {r.status_code}: {r.text[:200]}")
    return r.json().get("response", {})


def wait_for_mp4(render_id: str, *, poll_every: float = 5.0, timeout: float = 600.0) -> str:
    """Polls until status='done', returns the MP4 URL. Raises on timeout or failed.

    Transient network errors during polling are tolerated — we just retry on the next tick.
    """
    start = time.monotonic()
    transient_failures = 0
    last_status: str | None = None
    while True:
        try:
            s = get_status(render_id)
            transient_failures = 0
            status = s.get("status")
            last_status = status
            if status == "done":
                url = s.get("url")
                if not url:
                    raise ShotstackError("status=done but no url")
                return url
            if status == "failed":
                raise ShotstackError(f"render failed: {s.get('error')}")
        except httpx.HTTPError as e:
            # Read/connect timeouts, transient socket errors — tolerate up to ~5 in a row.
            transient_failures += 1
            log.warning("shotstack get_status transient error (%d): %s", transient_failures, e)
            if transient_failures > 5:
                raise ShotstackError(f"get_status failed repeatedly: {e}") from e
        if time.monotonic() - start > timeout:
            raise ShotstackError(f"render timed out (last status={last_status})")
        time.sleep(poll_every)
