from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


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


class PhotoOut(BaseModel):
    id: str
    url: str
    status: str
    width: int | None
    height: int | None
    uploaded_at: datetime
    faces: list[FaceTagOut]


class PhotoStatusOut(BaseModel):
    total: int
    pending: int
    processing: int
    done: int
    failed: int
    percent: float


class FaceAdd(BaseModel):
    user_id: str
    bbox: list[float] | None = None


class FaceOverride(BaseModel):
    remove_face_ids: list[str] = []
    add: list[FaceAdd] = []


class HealthOut(BaseModel):
    ok: bool
    mode: str
    model: str
    threshold: float
