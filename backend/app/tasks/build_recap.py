"""Pipeline orchestrator — for a trip_day:

    1. TTS the voiceover script via ElevenLabs → MP3 → upload to storage
    2. Build a Shotstack timeline (photos weighted by item importance + text overlays + music)
    3. Submit to Shotstack, poll until done
    4. Download the rendered MP4 → upload to storage
    5. Mark video_render row as pending_review
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from sqlmodel import select

from ..db import session_scope
from ..deps import get_storage
from ..models import ItineraryItem, Photo, TripDay, VideoRender
from ..services import audio_probe, remotion, shotstack, tts

log = logging.getLogger(__name__)

# Total target length of the recap.
TARGET_SECONDS = 30.0
END_CARD_SECONDS = 3.0  # last 3 seconds = branding card
# Per Shotstack's official Ken Burns template, photos crossfade on parallel
# tracks with overlap. clip_length > step → adjacent clips overlap = no black.
PHOTO_OVERLAP = 1.2          # seconds — overlap region for crossfade
MIN_STEP = 1.6               # seconds between consecutive photo START times

DEFAULT_MUSIC_URL = (
    # Shotstack canonical demo asset (royalty-free, on their CDN).
    "https://shotstack-assets.s3.ap-southeast-2.amazonaws.com/music/unminus/palmtrees.mp3"
)


def run_recap(video_render_id: str) -> None:
    """Entry point — call from BackgroundTasks. Catches everything."""
    import asyncio
    try:
        asyncio.run(_run(video_render_id))
    except Exception as e:  # noqa: BLE001
        log.exception("recap pipeline crashed for %s", video_render_id)
        with session_scope() as s:
            vr = s.get(VideoRender, video_render_id)
            if vr:
                vr.status = "failed"
                vr.error = str(e)[:500]
                s.add(vr)
                s.commit()


async def _run(video_render_id: str) -> None:
    storage = get_storage()

    # ---------- 1. Load + validate ----------
    with session_scope() as s:
        vr = s.get(VideoRender, video_render_id)
        if vr is None:
            raise RuntimeError(f"video_render {video_render_id} not found")
        day = s.get(TripDay, vr.trip_day_id)
        if day is None:
            raise RuntimeError("trip_day not found")
        if not (day.voiceover_script or "").strip():
            raise RuntimeError("trip_day has no voiceover_script — write/generate one first")

        items = s.exec(
            select(ItineraryItem)
            .where(ItineraryItem.trip_day_id == day.id)
            .order_by(ItineraryItem.position)  # type: ignore[arg-type]
        ).all()
        photos = s.exec(
            select(Photo).where(Photo.trip_id == day.trip_id, Photo.itinerary_item_id.is_not(None))  # type: ignore[attr-defined]
        ).all()
        item_ids = {i.id for i in items}
        photos = [p for p in photos if p.itinerary_item_id in item_ids and (p.taken_at is not None)]
        if not photos:
            raise RuntimeError("no photos with itinerary_item_id matched to this day — upload + match first")

        engine = (vr.engine or "shotstack").lower()
        version = vr.version
        script_text = day.voiceover_script or ""

    # ---------- 2. TTS (shared by both engines) ----------
    log.info("[recap %s] tts: %d chars (engine=%s)", video_render_id, len(script_text), engine)
    mp3_bytes = tts.synthesize(script_text)
    voiceover_key = f"voiceovers/{day.id}/v{version}.mp3"
    await storage.put(voiceover_key, mp3_bytes, "audio/mpeg")
    voiceover_url = storage.public_url(voiceover_key)

    # Probe voiceover duration so the video matches the audio length.
    voice_secs = audio_probe.mp3_duration_seconds(mp3_bytes) or TARGET_SECONDS
    log.info("[recap %s] voiceover_secs=%.2f", video_render_id, voice_secs)

    with session_scope() as s:
        vr = s.get(VideoRender, video_render_id)
        if vr is not None:
            vr.voiceover_storage_path = voiceover_key
            vr.status = "rendering"
            s.add(vr)
            s.commit()

    # ---------- 3. Dispatch to chosen engine ----------
    photos_by_item: dict[str, list[Photo]] = {i.id: [] for i in items}
    for p in photos:
        assert p.itinerary_item_id
        photos_by_item.setdefault(p.itinerary_item_id, []).append(p)
    for lst in photos_by_item.values():
        lst.sort(key=lambda x: x.taken_at or datetime.min.replace(tzinfo=timezone.utc))

    if engine == "remotion":
        mp4_bytes = await _render_via_remotion(
            video_render_id=video_render_id,
            day=day,
            items=items,
            photos=photos,
            photos_by_item=photos_by_item,
            voiceover_url=voiceover_url,
            voice_secs=voice_secs,
            storage=storage,
        )
    elif engine == "shotstack":
        mp4_bytes = await _render_via_shotstack(
            video_render_id=video_render_id,
            day=day,
            items=items,
            photos_by_item=photos_by_item,
            voiceover_url=voiceover_url,
            storage=storage,
        )
    else:
        raise RuntimeError(f"unknown engine: {engine}")

    # ---------- 4. Store MP4 + mark pending_review ----------
    mp4_key = f"recap_videos/{day.id}/v{version}.mp4"
    await storage.put(mp4_key, mp4_bytes, "video/mp4")
    with session_scope() as s:
        vr = s.get(VideoRender, video_render_id)
        if vr is None:
            return
        vr.mp4_storage_path = mp4_key
        vr.duration_seconds = int(round(voice_secs))
        vr.status = "pending_review"
        s.add(vr)
        s.commit()

    log.info("[recap %s] DONE → pending_review (engine=%s)", video_render_id, engine)


async def _render_via_shotstack(
    *, video_render_id, day, items, photos_by_item, voiceover_url, storage
) -> bytes:
    """Existing Shotstack pipeline: build timeline JSON → submit → poll → download MP4."""
    timeline = _build_timeline(
        day=day, items=items, photos_by_item=photos_by_item,
        storage=storage, voiceover_url=voiceover_url,
    )
    log.info("[recap %s] submitting to shotstack", video_render_id)
    rid = shotstack.submit_render(timeline)
    with session_scope() as s:
        vr = s.get(VideoRender, video_render_id)
        if vr is not None:
            vr.shotstack_render_id = rid
            s.add(vr)
            s.commit()

    log.info("[recap %s] waiting on shotstack %s ...", video_render_id, rid)
    mp4_url = shotstack.wait_for_mp4(rid, poll_every=5.0, timeout=600.0)
    log.info("[recap %s] downloading mp4 from %s", video_render_id, mp4_url)
    with httpx.Client(timeout=120.0) as c:
        r = c.get(mp4_url)
        r.raise_for_status()
        return r.content


async def _render_via_remotion(
    *, video_render_id, day, items, photos, photos_by_item, voiceover_url,
    voice_secs: float, storage
) -> bytes:
    """Remotion pipeline: POST spec to Node renderer → receive MP4 bytes."""
    item_by_id = {i.id: i for i in items}

    # Order photos: by item position, then by taken_at within each item.
    ordered: list[Photo] = []
    for item in sorted(items, key=lambda i: i.position):
        ordered.extend(photos_by_item.get(item.id, []))

    photo_specs = []
    for p in ordered:
        item = item_by_id.get(p.itinerary_item_id or "")
        # Prefer the diary-style caption; fall back to the descriptive title.
        caption = (item.caption if item and item.caption else (item.title if item else None))
        photo_specs.append({
            "url": storage.public_url(p.storage_path),
            "title": item.title if item else None,
            "caption": caption,
            "importance": int(item.importance) if item else 5,
        })

    # Size the video to fit ALL photos at a senior-friendly pace.
    # Voiceover plays for its natural length; music tails after.
    INTRO_SEC = 3.0
    OUTRO_SEC = 3.0
    MIN_PHOTO_SEC = 2.0
    n_photos = max(1, len(photo_specs))
    photo_content_sec = n_photos * MIN_PHOTO_SEC
    content_sec = max(voice_secs, photo_content_sec)
    total_sec = INTRO_SEC + content_sec + OUTRO_SEC
    log.info(
        "[recap %s] duration plan: total=%.1fs (intro=%.0f + content=%.1f + outro=%.0f), %d photos",
        video_render_id, total_sec, INTRO_SEC, content_sec, OUTRO_SEC, n_photos,
    )

    spec = {
        "videoRenderId": video_render_id,
        "dayTitle": day.theme or "Day",
        "daySubtitle": day.date.isoformat(),
        "photos": photo_specs,
        "voiceoverUrl": voiceover_url,
        "musicUrl": DEFAULT_MUSIC_URL,
        "targetSeconds": total_sec,
        "voiceoverDurationSec": total_sec,   # Recap uses this to size durationInFrames
        "fps": 30,
        "width": 1280,
        "height": 720,
        "brandColor": "#0E5C4A",
        "endCardText": "Travel Seasons",
    }

    if not remotion.is_available():
        raise RuntimeError(
            "Remotion renderer is offline at "
            f"{os.environ.get('REMOTION_RENDERER_URL','http://localhost:3001')}. "
            "Start it: `cd renderer && npm run start`"
        )

    log.info("[recap %s] submitting to Remotion renderer (%d photos)", video_render_id, len(photo_specs))
    import asyncio
    mp4_bytes = await asyncio.to_thread(remotion.render, spec)
    log.info("[recap %s] Remotion returned %d bytes", video_render_id, len(mp4_bytes))
    return mp4_bytes


# Preset 1 — "Warm Memories"
# Mirrors Shotstack's official "ken-burns-effect-slideshow-slow" template:
# clips overlap across two parallel tracks with fadeSlow crossfades, so the
# off-screen edges of slide effects are always hidden by the neighbouring clip.
PRESET = {
    "name": "warm_memories",
    # Full Ken Burns variety — slides are now safe because adjacent clips
    # crossfade and cover the moments when the image moves off-screen.
    "motion_cycle": [
        "zoomInSlow", "slideLeftSlow",
        "zoomOutSlow", "slideRightSlow",
        "zoomInSlow", "slideUpSlow",
        "zoomOutSlow", "slideDownSlow",
    ],
    "image_filter": "boost",           # subtle saturation + warmth
    "transition_in": "fadeSlow",
    "transition_out": "fadeSlow",
    "title_style": "vogue",            # elegant italic serif
    "title_size": "small",
    "title_position": "bottomLeft",
    "title_color": "#ffffff",
    "title_background": "rgba(0,0,0,0.4)",
    "music_volume": 0.15,
    "music_effect": "fadeOut",
    "voice_volume": 1.0,
    "end_card_bg": "#0E5C4A",          # brand green
    "background": "#0E5C4A",           # any bleed-through is brand colour, not black
}


def _build_timeline(*, day, items, photos_by_item, storage, voiceover_url: str) -> dict:
    """Build a Shotstack timeline using the Ken-Burns-crossfade pattern.

    Photos alternate between two parallel tracks (A and B). Each clip is
    longer than the step between its start and the next photo's start —
    that overlap is the crossfade region, hidden by fadeSlow transitions.
    Net effect: NO black frames; slide effects safely move off-screen.
    """

    # Reserve 3 sec for branding end-card.
    content_secs = TARGET_SECONDS - END_CARD_SECONDS

    # Flatten photos in itinerary order, but weight more important items by
    # giving them a longer step.
    items_with_photos = [i for i in items if photos_by_item.get(i.id)]
    if not items_with_photos:
        items_with_photos = items

    # Compute per-photo step. Equal time per photo so adjacent overlaps line
    # up cleanly; importance can be re-introduced later by varying step.
    flat: list[tuple[object, object]] = []  # (item, photo)
    for item in items_with_photos:
        for p in photos_by_item.get(item.id) or []:
            flat.append((item, p))
    if not flat:
        flat = []
    step = max(MIN_STEP, content_secs / max(1, len(flat))) if flat else MIN_STEP
    clip_length = step + PHOTO_OVERLAP

    track_a: list[dict] = []
    track_b: list[dict] = []
    title_clips: list[dict] = []
    motion_idx = 0
    titled_items: set[str] = set()

    for idx, (item, p) in enumerate(flat):
        start = idx * step
        # Title overlay once per important section, anchored at the first
        # photo of that section.
        if item.importance >= 7 and item.id not in titled_items:
            titled_items.add(item.id)
            title_clips.append({
                "asset": {
                    "type": "title",
                    "text": item.title,
                    "style": PRESET["title_style"],
                    "color": PRESET["title_color"],
                    "background": PRESET["title_background"],
                    "size": PRESET["title_size"],
                    "position": PRESET["title_position"],
                },
                "start": round(start + 0.2, 2),       # slight delay so it eases in
                "length": min(2.2, clip_length - 0.5),
                "transition": {"in": "fadeSlow", "out": "fadeSlow"},
            })

        url = storage.public_url(p.storage_path)
        effect = PRESET["motion_cycle"][motion_idx % len(PRESET["motion_cycle"])]
        motion_idx += 1
        clip = {
            "asset": {"type": "image", "src": url},
            "start": round(start, 2),
            "length": round(clip_length, 2),
            "effect": effect,
            "filter": PRESET["image_filter"],
            "transition": {"in": PRESET["transition_in"], "out": PRESET["transition_out"]},
        }
        # Alternate tracks so neighbours overlap on different tracks.
        (track_a if idx % 2 == 0 else track_b).append(clip)

    last_photo_end = (len(flat) - 1) * step + clip_length if flat else 0
    content_end = max(content_secs, last_photo_end)
    total_length = content_end + END_CARD_SECONDS

    # End card on its own track (so it appears on top at the end and is
    # opaque, covering any tail of photo tracks).
    end_card_track = [{
        "asset": {
            "type": "title",
            "text": "Travel Seasons",
            "style": PRESET["title_style"],
            "color": "#ffffff",
            "background": PRESET["end_card_bg"],
            "size": "large",
            "position": "center",
        },
        "start": round(content_end, 2),
        "length": END_CARD_SECONDS,
        "transition": {"in": "fadeSlow"},
    }]

    return {
        "background": PRESET["background"],
        "tracks": [
            # Top: end card (above titles so it covers them at the end)
            {"clips": end_card_track},
            # Title overlays (over photos)
            {"clips": title_clips},
            # Photo track A (odd-indexed: 0, 2, 4, ...)
            {"clips": track_a},
            # Photo track B (even-indexed: 1, 3, 5, ...)
            {"clips": track_b},
            # Voiceover audio
            {"clips": [{
                "asset": {"type": "audio", "src": voiceover_url, "volume": PRESET["voice_volume"]},
                "start": 0,
                "length": round(total_length, 2),
            }]},
            # Music ducked with fadeOut at end
            {"clips": [{
                "asset": {
                    "type": "audio",
                    "src": DEFAULT_MUSIC_URL,
                    "volume": PRESET["music_volume"],
                    "effect": PRESET["music_effect"],
                },
                "start": 0,
                "length": round(total_length, 2),
            }]},
        ],
    }
