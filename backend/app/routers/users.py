from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import db_session, get_storage
from ..face import crop_face, get_engine
from ..models import Photo, PhotoFace, User
from ..schemas import UserOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(session: Session = Depends(db_session)):
    storage = get_storage()
    rows = session.exec(select(User).where(User.deleted_at == None)).all()  # noqa: E711
    return [
        UserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            has_selfie=u.selfie_path is not None,
            selfie_url=storage.public_url(u.selfie_path) if u.selfie_path else None,
            created_at=u.created_at,
        )
        for u in rows
    ]


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: str, session: Session = Depends(db_session)):
    storage = get_storage()
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    # Remove selfie file from storage (best-effort).
    if user.selfie_path:
        try:
            await storage.delete(user.selfie_path)
        except Exception:
            log.warning("delete selfie file failed (non-fatal)", exc_info=True)

    # Release this user's auto/manual face tags back to the "unmatched" pool BEFORE
    # we delete their AWS faces. Each row's bbox is re-cropped from the source photo
    # and re-indexed with ExternalImageId='unmatched:<pf_id>' so a future enrolment
    # can rediscover it. Without this, auto-matched faces become invisible after
    # delete because their AWS anchor (the user's selfie face) is about to vanish.
    pf_rows = session.exec(
        select(PhotoFace).where(PhotoFace.user_id == user_id, PhotoFace.removed == False)  # noqa: E712
    ).all()
    released = 0
    dropped = 0
    if pf_rows:
        eng = get_engine()
        photo_bytes_cache: dict[str, bytes] = {}
        for pf in pf_rows:
            photo = session.get(Photo, pf.photo_id)
            if photo is None:
                dropped += 1
                pf.removed = True
                session.add(pf)
                continue
            try:
                img_bytes = photo_bytes_cache.get(photo.storage_path)
                if img_bytes is None:
                    img_bytes = await storage.get_bytes(photo.storage_path)
                    photo_bytes_cache[photo.storage_path] = img_bytes
                bbox = json.loads(pf.bbox)
                crop_bytes, crop_err = crop_face(img_bytes, bbox)
                if not crop_bytes:
                    raise RuntimeError(f"crop failed: {crop_err}")
                new_face_id = await asyncio.to_thread(eng.index_unmatched, crop_bytes, pf.id)
                if not new_face_id:
                    raise RuntimeError("index_unmatched returned None (quality reject)")
                pf.user_id = None
                pf.rekognition_face_id = new_face_id
                pf.confidence = None
                pf.source = "auto"
                pf.removed = False
                pf.error = None
                session.add(pf)
                released += 1
            except Exception:
                log.warning("release_face_to_unmatched failed pf=%s photo=%s", pf.id, pf.photo_id, exc_info=True)
                pf.removed = True
                session.add(pf)
                dropped += 1
        log.info("delete_user user=%s released=%d dropped=%d", user_id, released, dropped)

    # Remove ALL of the user's faces from the Rekognition collection (canonical
    # selfie + any manual-tag face_ids added later via /manual-tag). The released
    # rows above now reference NEW unmatched: face entries, not these.
    if user.rekognition_face_id is not None:
        try:
            face_ids = await asyncio.to_thread(get_engine().list_user_face_ids, user_id)
            if face_ids:
                try:
                    await asyncio.to_thread(get_engine().bulk_delete_faces, face_ids)
                except Exception:
                    log.warning(
                        "bulk_delete_faces during user-delete had partial failures",
                        exc_info=True,
                    )
        except Exception:
            log.warning("list_user_face_ids failed (non-fatal)", exc_info=True)
        user.rekognition_face_id = None

    # Soft-delete the user row + blank legacy embedding.
    user.face_embedding = None
    user.selfie_path = None
    user.deleted_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return
