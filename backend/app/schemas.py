from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, field_validator


class UserOut(BaseModel):
    id: str
    name: str
    email: str | None = None
    has_selfie: bool
    selfie_url: str | None = None
    created_at: datetime


class TripCreate(BaseModel):
    name: str
    start_date: date | None = None
    end_date: date | None = None
    member_user_ids: list[str] = []


class TripOut(BaseModel):
    id: str
    name: str
    start_date: date | None = None
    end_date: date | None = None
    photo_count: int
    members: list[UserOut]


class FaceTagOut(BaseModel):
    id: str
    user_id: str | None
    name: str | None
    confidence: float | None
    source: str
    bbox: list[float]
    bbox_space: str = "normalised"  # 'pixel' (legacy) or 'normalised'


class RecapPhotosUpdate(BaseModel):
    """Replace-all selection + order for a day's recap photos."""
    ordered_photo_ids: list[str]


class PhotoOut(BaseModel):
    id: str
    url: str
    status: str
    width: int | None
    height: int | None
    uploaded_at: datetime
    taken_at: datetime | None = None
    itinerary_item_id: str | None = None
    recap_position: int | None = None
    faces: list[FaceTagOut]


class PhotoStatusOut(BaseModel):
    total: int
    pending: int
    processing: int
    done: int
    failed: int
    percent: float


class FaceOverride(BaseModel):
    remove_face_ids: list[str] = []


class ManualTagIn(BaseModel):
    user_id: str
    bbox: list[float]  # [x, y, w, h] normalised 0-1
    replace_photoface_id: str | None = None

    @field_validator("bbox")
    @classmethod
    def _bbox_in_unit_square(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError("bbox must have 4 elements: [x, y, w, h]")
        x, y, w, h = v
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("x and y must be in [0, 1]")
        if not (w > 0 and h > 0):
            raise ValueError("w and h must be > 0")
        if x + w > 1.0 + 1e-6 or y + h > 1.0 + 1e-6:
            raise ValueError("bbox extends beyond image")
        return v


class ManualTagOut(BaseModel):
    photo: PhotoOut
    propagated_count: int
    propagated_photo_ids: list[str]


class HealthOut(BaseModel):
    ok: bool
    mode: str
    face_engine: str
    collection: str
    collection_face_count: int
    threshold: float


# ---------- Itinerary / TripDay / Video ----------

class ItineraryItemIn(BaseModel):
    start_time: time | None = None
    end_time: time | None = None
    title: str
    description: str | None = None
    caption: str | None = None
    importance: int = 5


class ItineraryItemOut(ItineraryItemIn):
    id: str
    position: int
    photo_count: int = 0


class ItineraryItemUpdate(BaseModel):
    start_time: time | None = None
    end_time: time | None = None
    title: str | None = None
    description: str | None = None
    caption: str | None = None
    importance: int | None = None


class TripDayCreate(BaseModel):
    date: date
    raw_text: str
    theme: str | None = None
    tour_manager: str | None = None
    weather: str | None = None


class TripDayUpdate(BaseModel):
    theme: str | None = None
    tour_manager: str | None = None
    weather: str | None = None
    voiceover_script: str | None = None


class VideoRenderOut(BaseModel):
    id: str
    trip_day_id: str
    version: int
    status: str
    engine: str = "shotstack"
    mp4_url: str | None = None
    duration_seconds: int | None = None
    admin_notes: str | None = None
    error: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class TripDaySummaryOut(BaseModel):
    id: str
    date: date
    theme: str | None
    photo_count: int
    has_approved_video: bool


class TripDayOut(BaseModel):
    id: str
    trip_id: str
    date: date
    theme: str | None
    weather: str | None
    tour_manager: str | None
    voiceover_script: str | None
    filmable_moments: list[Any] | None
    items: list[ItineraryItemOut]
    photos: list[PhotoOut] = []  # selected first by recap_position, then unselected
    photo_count: int
    latest_video: VideoRenderOut | None = None


from typing import Literal


class VideoGenerateRequest(BaseModel):
    voice_id: str | None = None       # override default ElevenLabs voice
    music_track: str | None = None    # filename in assets/music/, default = calm_travel.mp3
    renderer: Literal["shotstack", "remotion"] = "remotion"   # default engine


class VideoReviewRequest(BaseModel):
    admin_notes: str | None = None

