from __future__ import annotations

import json
import uuid
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from sqlmodel import Session, select

from ..deps import db_session, get_storage, x_user_id
from ..models import Photo, PhotoFace, Trip, User
from ..schemas import FaceOverride, FaceTagOut, PhotoOut, PhotoStatusOut
from ..tasks.process_photos import schedule_photo_processing

router = APIRouter(tags=["photos"])


@router.post("/trips/{trip_id}/photos", status_code=202)
async def upload_photos(
    trip_id: str,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    session: Session = Depends(db_session),
):
    storage = get_storage()
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")

    queued: list[str] = []
    for upload in files:
        data = await upload.read()
        if len(data) == 0:
            continue
        photo_id = str(uuid.uuid4())
        key = f"trip_photos/{trip_id}/{photo_id}.jpg"
        await storage.put(key, data, upload.content_type or "image/jpeg")
        photo = Photo(id=photo_id, trip_id=trip_id, storage_path=key, status="pending")
        session.add(photo)
        session.commit()
        schedule_photo_processing(background, photo_id)
        queued.append(photo_id)

    return {"queued": queued, "count": len(queued)}


def _photo_to_out(photo: Photo, faces: list[PhotoFace], users_by_id: dict[str, User], storage) -> PhotoOut:
    face_outs: list[FaceTagOut] = []
    for f in faces:
        try:
            bbox = json.loads(f.bbox)
        except (json.JSONDecodeError, TypeError):
            bbox = []
        name = users_by_id[f.user_id].name if f.user_id and f.user_id in users_by_id else None
        face_outs.append(
            FaceTagOut(
                id=f.id,
                user_id=f.user_id,
                name=name,
                confidence=f.confidence,
                source=f.source,
                bbox=bbox,
            )
        )
    return PhotoOut(
        id=photo.id,
        url=storage.public_url(photo.storage_path),
        status=photo.status,
        width=photo.width,
        height=photo.height,
        uploaded_at=photo.uploaded_at,
        faces=face_outs,
    )


@router.get("/trips/{trip_id}/photos", response_model=list[PhotoOut])
def list_trip_photos(
    trip_id: str,
    filter: Literal["all", "me", "group"] = Query(default="all"),
    user_id: str | None = Depends(x_user_id),
    session: Session = Depends(db_session),
):
    storage = get_storage()
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")

    if filter == "me" and not user_id:
        raise HTTPException(status_code=400, detail="X-User-Id header required for filter=me")

    photos = session.exec(
        select(Photo).where(Photo.trip_id == trip_id).order_by(Photo.uploaded_at.desc())  # type: ignore[attr-defined]
    ).all()
    if not photos:
        return []
    photo_ids = [p.id for p in photos]

    faces_by_photo: dict[str, list[PhotoFace]] = {pid: [] for pid in photo_ids}
    all_faces = session.exec(
        select(PhotoFace).where(PhotoFace.photo_id.in_(photo_ids), PhotoFace.removed == False)  # type: ignore[attr-defined]  # noqa: E712
    ).all()
    for f in all_faces:
        faces_by_photo[f.photo_id].append(f)

    user_ids = {f.user_id for fs in faces_by_photo.values() for f in fs if f.user_id}
    users_by_id: dict[str, User] = {}
    if user_ids:
        for u in session.exec(select(User).where(User.id.in_(list(user_ids)))).all():  # type: ignore[attr-defined]
            users_by_id[u.id] = u

    if filter == "me":
        photos = [
            p for p in photos
            if any(f.user_id == user_id for f in faces_by_photo[p.id])
        ]
    elif filter == "group":
        photos = [
            p for p in photos
            if len({f.user_id for f in faces_by_photo[p.id] if f.user_id}) >= 2
        ]

    return [_photo_to_out(p, faces_by_photo[p.id], users_by_id, storage) for p in photos]


@router.get("/trips/{trip_id}/photos/status", response_model=PhotoStatusOut)
def trip_photos_status(trip_id: str, session: Session = Depends(db_session)):
    photos = session.exec(select(Photo).where(Photo.trip_id == trip_id)).all()
    counts = {"pending": 0, "processing": 0, "done": 0, "failed": 0}
    for p in photos:
        if p.status in counts:
            counts[p.status] += 1
    total = len(photos)
    done_or_failed = counts["done"] + counts["failed"]
    pct = (done_or_failed / total * 100.0) if total else 0.0
    return PhotoStatusOut(total=total, percent=pct, **counts)


@router.patch("/photos/{photo_id}/faces", response_model=PhotoOut)
def override_photo_faces(
    photo_id: str,
    body: FaceOverride,
    session: Session = Depends(db_session),
):
    storage = get_storage()
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")

    if body.remove_face_ids:
        for face_id in body.remove_face_ids:
            f = session.get(PhotoFace, face_id)
            if f and f.photo_id == photo_id:
                f.removed = True
                f.source = "manual"
                session.add(f)

    for add in body.add:
        u = session.get(User, add.user_id)
        if u is None:
            continue
        bbox = add.bbox or [0.0, 0.0, 0.0, 0.0]
        embedding = u.face_embedding or "[]"
        face = PhotoFace(
            photo_id=photo_id,
            user_id=add.user_id,
            bbox=json.dumps(bbox),
            embedding=embedding,
            confidence=None,
            source="manual",
            removed=False,
        )
        session.add(face)

    session.commit()

    faces = session.exec(
        select(PhotoFace).where(PhotoFace.photo_id == photo_id, PhotoFace.removed == False)  # noqa: E712
    ).all()
    user_ids = {f.user_id for f in faces if f.user_id}
    users_by_id: dict[str, User] = {}
    if user_ids:
        for u in session.exec(select(User).where(User.id.in_(list(user_ids)))).all():  # type: ignore[attr-defined]
            users_by_id[u.id] = u

    return _photo_to_out(photo, faces, users_by_id, storage)


@router.delete("/photos/{photo_id}", status_code=204)
async def delete_photo(photo_id: str, session: Session = Depends(db_session)):
    storage = get_storage()
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    try:
        await storage.delete(photo.storage_path)
    except Exception:
        pass
    faces = session.exec(select(PhotoFace).where(PhotoFace.photo_id == photo_id)).all()
    for f in faces:
        session.delete(f)
    session.delete(photo)
    session.commit()
    return
