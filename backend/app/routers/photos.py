from __future__ import annotations

import asyncio
import json
import logging
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
from sqlalchemy import text
from sqlmodel import Session, select

from ..deps import db_session, get_storage, x_user_id
from ..face import crop_face, get_engine
from ..models import Photo, PhotoFace, Trip, User
from ..schemas import (
    FaceOverride,
    FaceTagOut,
    ManualTagIn,
    ManualTagOut,
    PhotoOut,
    PhotoStatusOut,
)
from ..services.exif import match_to_itinerary, read_taken_at
from ..tasks.process_photos import schedule_photo_processing

log = logging.getLogger(__name__)
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

        taken_at = read_taken_at(data)
        itinerary_item_id = (
            match_to_itinerary(session, trip_id=trip_id, taken_at=taken_at) if taken_at else None
        )

        # Default recap_position: append to end of day's existing selection.
        # NULL if photo isn't matched to a day yet.
        recap_position: int | None = None
        if itinerary_item_id is not None:
            recap_position = session.exec(
                text(
                    "SELECT COALESCE(MAX(p.recap_position), 0) + 1 "
                    "FROM photo p JOIN itinerary_item ii ON ii.id = p.itinerary_item_id "
                    "WHERE ii.trip_day_id = (SELECT trip_day_id FROM itinerary_item WHERE id = :iid)"
                ).bindparams(iid=itinerary_item_id)
            ).scalar()

        photo = Photo(
            id=photo_id,
            trip_id=trip_id,
            storage_path=key,
            status="pending",
            taken_at=taken_at,
            itinerary_item_id=itinerary_item_id,
            recap_position=recap_position,
        )
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
                bbox_space=f.bbox_space or "normalised",
            )
        )
    return PhotoOut(
        id=photo.id,
        url=storage.public_url(photo.storage_path),
        status=photo.status,
        width=photo.width,
        height=photo.height,
        uploaded_at=photo.uploaded_at,
        taken_at=photo.taken_at,
        itinerary_item_id=photo.itinerary_item_id,
        recap_position=photo.recap_position,
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
async def override_photo_faces(
    photo_id: str,
    body: FaceOverride,
    session: Session = Depends(db_session),
):
    """Remove face tags. Also cleans up the Rekognition collection for
    `unmatched:*` entries (rows where `user_id IS NULL` AND `rekognition_face_id`
    is set were indexed under an `unmatched:` ExternalImageId).
    """
    storage = get_storage()
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")

    eng = get_engine()
    face_ids_to_delete_in_aws: list[str] = []

    for face_id in body.remove_face_ids:
        f = session.get(PhotoFace, face_id)
        if f and f.photo_id == photo_id and not f.removed:
            # Proxy: user_id IS NULL + rekognition_face_id IS NOT NULL → it's an
            # unmatched:* AWS entry, safe to delete. Real-user face_ids stay in
            # the collection (they may be a user's canonical or manual tag).
            if f.user_id is None and f.rekognition_face_id:
                face_ids_to_delete_in_aws.append(f.rekognition_face_id)
            f.removed = True
            f.source = "manual"
            session.add(f)

    session.commit()

    # Post-commit AWS cleanup (best-effort)
    if face_ids_to_delete_in_aws:
        try:
            await asyncio.to_thread(eng.bulk_delete_faces, face_ids_to_delete_in_aws)
        except Exception:
            log.warning("bulk_delete_faces after remove failed; orphans remain", exc_info=True)

    faces = session.exec(
        select(PhotoFace).where(PhotoFace.photo_id == photo_id, PhotoFace.removed == False)  # noqa: E712
    ).all()
    user_ids = {f.user_id for f in faces if f.user_id}
    users_by_id: dict[str, User] = {}
    if user_ids:
        for u in session.exec(select(User).where(User.id.in_(list(user_ids)))).all():  # type: ignore[attr-defined]
            users_by_id[u.id] = u

    return _photo_to_out(photo, faces, users_by_id, storage)


@router.post("/photos/{photo_id}/manual-tag", response_model=ManualTagOut)
async def manual_tag(
    photo_id: str,
    body: ManualTagIn,
    session: Session = Depends(db_session),
):
    """Admin draws a bbox + picks a user → backend crops, indexes into AWS,
    propagates to all matching `unmatched:*` entries across the collection."""
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    # Block while photo is mid-processing; auto pipeline would race the manual tag.
    if photo.status in ("pending", "processing"):
        raise HTTPException(
            status_code=409,
            detail=f"photo still {photo.status} — try again shortly",
        )

    user = session.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.deleted_at is not None:
        raise HTTPException(status_code=410, detail="user has been deleted")

    replaced: PhotoFace | None = None
    if body.replace_photoface_id:
        replaced = session.get(PhotoFace, body.replace_photoface_id)
        if replaced and replaced.photo_id != photo_id:
            raise HTTPException(
                status_code=400, detail="replace_photoface_id is on a different photo"
            )

    storage = get_storage()
    try:
        image_bytes = await storage.get_bytes(photo.storage_path)
    except Exception as e:
        log.exception("get_bytes failed for photo %s", photo_id)
        raise HTTPException(status_code=502, detail="photo storage unreachable") from e

    crop_bytes, crop_err = crop_face(image_bytes, body.bbox)
    if crop_bytes is None:
        raise HTTPException(
            status_code=400, detail=f"selection too small after 15% padding ({crop_err})"
        )

    eng = get_engine()
    try:
        new_face_id = await asyncio.to_thread(eng.index_manual_face, crop_bytes, user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    linked_face_ids: list[str] = []
    propagated_photo_ids: list[str] = []
    try:
        pf = PhotoFace(
            photo_id=photo_id,
            user_id=user.id,
            bbox=json.dumps(body.bbox),
            bbox_space="normalised",
            embedding=None,
            rekognition_face_id=new_face_id,
            confidence=None,
            source="manual",
            removed=False,
            error=None,
        )
        session.add(pf)

        if replaced and not replaced.removed:
            # Proxy: user_id IS NULL → unmatched:* entry, queue for cleanup
            if replaced.user_id is None and replaced.rekognition_face_id:
                linked_face_ids.append(replaced.rekognition_face_id)
            replaced.removed = True
            replaced.source = "manual"
            session.add(replaced)

        if user.rekognition_face_id is None:
            user.rekognition_face_id = new_face_id
            session.add(user)

        # Propagation across the entire collection (cross-trip is intentional).
        matches = await asyncio.to_thread(
            eng.search_unmatched_for_user, new_face_id, user.id
        )
        for face_id, ext_id, sim in matches:
            pf_id = ext_id.split(":", 1)[1]
            tgt = session.get(PhotoFace, pf_id)
            if tgt is None or tgt.removed or tgt.user_id is not None:
                continue
            tgt.user_id = user.id
            tgt.rekognition_face_id = user.rekognition_face_id
            tgt.confidence = sim
            tgt.source = "auto"
            tgt.error = None
            session.add(tgt)
            propagated_photo_ids.append(tgt.photo_id)
            linked_face_ids.append(face_id)

        # Commit DB FIRST — AWS leftovers recoverable, post-commit DB rollback is not.
        session.commit()
    except Exception:
        session.rollback()
        try:
            await asyncio.to_thread(eng.delete_face, new_face_id)
        except Exception:
            log.exception(
                "CRITICAL: orphaned AWS face_id=%s after DB failure", new_face_id
            )
        raise

    # Post-commit AWS cleanup
    if linked_face_ids:
        try:
            await asyncio.to_thread(eng.bulk_delete_faces, linked_face_ids)
        except Exception:
            log.warning(
                "bulk_delete_faces post-commit failed; orphans remain", exc_info=True
            )

    log.info(
        "manual_tag photo_id=%s user_id=%s new_face_id=%s propagated=%d replaced=%s",
        photo_id, user.id, new_face_id, len(propagated_photo_ids), bool(replaced),
    )

    # Re-query for response (uses existing _photo_to_out signature)
    faces = session.exec(
        select(PhotoFace).where(
            PhotoFace.photo_id == photo_id, PhotoFace.removed == False  # noqa: E712
        )
    ).all()
    user_ids = {f.user_id for f in faces if f.user_id}
    users_by_id: dict[str, User] = {}
    if user_ids:
        for u in session.exec(select(User).where(User.id.in_(list(user_ids)))).all():  # type: ignore[attr-defined]
            users_by_id[u.id] = u

    return ManualTagOut(
        photo=_photo_to_out(photo, faces, users_by_id, storage),
        propagated_count=len(propagated_photo_ids),
        propagated_photo_ids=sorted(set(propagated_photo_ids)),
    )


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
