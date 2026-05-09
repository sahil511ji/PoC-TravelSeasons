from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

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
    face_embedding: str | None = None  # JSON-encoded list[float], len=512
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


class PhotoFace(SQLModel, table=True):
    __tablename__ = "photoface"

    id: str = Field(default_factory=_uuid, primary_key=True)
    photo_id: str = Field(foreign_key="photo.id", index=True)
    user_id: str | None = Field(default=None, foreign_key="user.id", index=True)
    bbox: str  # JSON [x, y, w, h]
    embedding: str  # JSON list[float]
    confidence: float | None = None
    source: str = Field(default="auto")  # auto|manual
    removed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)
