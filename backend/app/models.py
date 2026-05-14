from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    email: str | None = None
    selfie_path: str | None = None
    face_embedding: str | None = None  # LEGACY: JSON-encoded list[float], len=512 (facenet era)
    rekognition_face_id: str | None = None  # AWS Rekognition FaceId
    created_at: datetime = Field(default_factory=_now)
    deleted_at: datetime | None = None


class Trip(SQLModel, table=True):
    __tablename__ = "trip"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    start_date: date | None = None
    end_date: date | None = None
    created_at: datetime = Field(default_factory=_now)


class TripUser(SQLModel, table=True):
    __tablename__ = "tripuser"

    trip_id: str = Field(foreign_key="trip.id", primary_key=True)
    user_id: str = Field(foreign_key="user.id", primary_key=True)


class Photo(SQLModel, table=True):
    __tablename__ = "photo"

    id: str = Field(default_factory=_uuid, primary_key=True)
    trip_id: str = Field(foreign_key="trip.id", index=True)
    storage_path: str
    width: int | None = None
    height: int | None = None
    status: str = Field(default="pending", index=True)  # pending|processing|done|failed
    error: str | None = None
    uploaded_at: datetime = Field(default_factory=_now)
    processed_at: datetime | None = None
    taken_at: datetime | None = None
    itinerary_item_id: str | None = Field(default=None, foreign_key="itinerary_item.id", index=True)
    recap_position: int | None = None  # NULL = excluded from recap; integer = ordered position within day


class TripDay(SQLModel, table=True):
    __tablename__ = "trip_day"

    id: str = Field(default_factory=_uuid, primary_key=True)
    trip_id: str = Field(foreign_key="trip.id", index=True)
    date: date
    theme: str | None = None
    weather: str | None = None
    tour_manager: str | None = None
    raw_text: str | None = None
    voiceover_script: str | None = None
    filmable_moments: list[Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_at: datetime = Field(default_factory=_now)


class ItineraryItem(SQLModel, table=True):
    __tablename__ = "itinerary_item"

    id: str = Field(default_factory=_uuid, primary_key=True)
    trip_day_id: str = Field(foreign_key="trip_day.id", index=True)
    start_time: time | None = None
    end_time: time | None = None
    title: str
    description: str | None = None
    caption: str | None = None   # diary-style one-liner shown in recap video
    importance: int = Field(default=5)
    position: int = Field(default=0)
    created_at: datetime = Field(default_factory=_now)


class VideoRender(SQLModel, table=True):
    __tablename__ = "video_render"

    id: str = Field(default_factory=_uuid, primary_key=True)
    trip_day_id: str = Field(foreign_key="trip_day.id", index=True)
    version: int = 1
    status: str = Field(default="queued")  # queued|rendering|pending_review|approved|rejected|failed
    engine: str = Field(default="shotstack")  # shotstack | remotion
    shotstack_render_id: str | None = None
    mp4_storage_path: str | None = None
    voiceover_storage_path: str | None = None
    duration_seconds: int | None = None
    admin_notes: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    reviewed_at: datetime | None = None


class PhotoFace(SQLModel, table=True):
    __tablename__ = "photoface"

    id: str = Field(default_factory=_uuid, primary_key=True)
    photo_id: str = Field(foreign_key="photo.id", index=True)
    user_id: str | None = Field(default=None, foreign_key="user.id", index=True)
    bbox: str  # JSON [x, y, w, h]
    bbox_space: str = Field(default="normalised")  # 'pixel' (legacy) | 'normalised' (new)
    embedding: str | None = None  # LEGACY nullable since Rekognition migration
    rekognition_face_id: str | None = Field(default=None, index=True)
    confidence: float | None = None  # 0-100 for Rekognition rows; 0-1 for legacy facenet rows
    source: str = Field(default="auto")  # auto|manual
    removed: bool = Field(default=False)
    error: str | None = None  # per-face error e.g. "throttled" | "too_small" | "quality_reject"
    created_at: datetime = Field(default_factory=_now)
