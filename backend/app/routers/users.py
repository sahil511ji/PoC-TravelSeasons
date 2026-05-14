from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, update

from ..deps import db_session, get_storage
from ..face import get_engine
from ..models import PhotoFace, User
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

    # Remove ALL of the user's faces from the Rekognition collection (canonical
    # selfie + any manual-tag face_ids added later via /manual-tag).
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

    # Mark all face tags pointing at this user as removed.
    session.exec(
        update(PhotoFace).where(PhotoFace.user_id == user_id).values(removed=True)
    )
    session.commit()
    return
