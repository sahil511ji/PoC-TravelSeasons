from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from ..deps import db_session, get_storage
from ..face import get_engine, resize_if_oversized
from ..models import User
from ..schemas import UserOut
from ..tasks.rematch import rematch_unmatched_after_enrol

log = logging.getLogger(__name__)
router = APIRouter(prefix="/enrollments", tags=["enrollments"])


@router.post("", response_model=UserOut, status_code=201)
async def create_enrollment(
    name: str = Form(...),
    email: str | None = Form(default=None),
    selfie: UploadFile = File(...),
    user_id: str | None = Form(default=None),
    session: Session = Depends(db_session),
):
    storage = get_storage()
    image_bytes = await selfie.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty selfie file")

    # Pre-resize if needed to fit Rekognition's 5 MB inline limit.
    image_bytes = await asyncio.to_thread(resize_if_oversized, image_bytes)
    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Selfie too large even after resize")

    eng = get_engine()

    # Re-enrolment path: if user already has an AWS face_id, delete the old one first.
    existing = session.get(User, user_id) if user_id else None

    # Auto-merge: if this is a fresh enrollment (no existing user row for this
    # user_id) AND the selfie matches an already-enrolled user at >=80%, treat
    # the enrolment as a login for that user instead of creating a duplicate.
    # Covers the common flow: admin pre-tags photos to create user X; later the
    # real X opens the Flutter app and uploads their selfie.
    if existing is None:
        matched_user_id, matched_sim = await asyncio.to_thread(
            eng.find_existing_user_for_selfie, image_bytes
        )
        if matched_user_id:
            candidate = session.get(User, matched_user_id)
            if candidate and candidate.deleted_at is None:
                log.info(
                    "enrollment auto-merge: selfie matched existing user_id=%s name=%r similarity=%.1f",
                    candidate.id, candidate.name, matched_sim,
                )
                # Update display name/email if caller provided them.
                if name:
                    candidate.name = name
                if email is not None:
                    candidate.email = email
                # Save the selfie file under the existing user's id.
                selfie_key = f"selfies/{candidate.id}.jpg"
                await storage.put(selfie_key, image_bytes, selfie.content_type or "image/jpeg")
                candidate.selfie_path = selfie_key
                session.add(candidate)
                session.commit()
                session.refresh(candidate)
                return UserOut(
                    id=candidate.id,
                    name=candidate.name,
                    email=candidate.email,
                    has_selfie=candidate.selfie_path is not None,
                    selfie_url=storage.public_url(candidate.selfie_path) if candidate.selfie_path else None,
                    created_at=candidate.created_at,
                )

    if existing and existing.rekognition_face_id:
        try:
            await asyncio.to_thread(eng.delete_face, existing.rekognition_face_id)
        except Exception:
            log.warning("delete_face during re-enrol failed (non-fatal)", exc_info=True)
        existing.rekognition_face_id = None

    # Build/reuse the User row so we know the user_id to set as ExternalImageId.
    user = None
    if user_id:
        if existing:
            user = existing
            user.name = name
            user.email = email
        else:
            user = User(id=user_id, name=name, email=email)
    if user is None:
        user = User(name=name, email=email)

    # Reactivate soft-deleted users on re-enrolment.
    if user.deleted_at is not None:
        user.deleted_at = None

    # Index against the Rekognition collection.
    try:
        face_id = await asyncio.to_thread(eng.index_selfie, image_bytes, user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    user.rekognition_face_id = face_id
    user.face_embedding = None  # legacy column — kept nullable, not populated

    # Upload selfie to storage for admin thumbnail + future recovery.
    selfie_key = f"selfies/{user.id}.jpg"
    await storage.put(selfie_key, image_bytes, selfie.content_type or "image/jpeg")
    user.selfie_path = selfie_key

    session.add(user)
    session.commit()
    session.refresh(user)

    # Auto-link previously-unmatched faces to this newly enrolled user.
    try:
        await asyncio.to_thread(rematch_unmatched_after_enrol, session, user)
    except Exception:
        log.exception("rematch_unmatched_after_enrol failed (non-fatal)")

    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        has_selfie=user.selfie_path is not None,
        selfie_url=storage.public_url(user.selfie_path) if user.selfie_path else None,
        created_at=user.created_at,
    )
