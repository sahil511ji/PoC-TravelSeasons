from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from ..deps import db_session, get_storage
from ..face.engine import get_engine
from ..models import User
from ..schemas import UserOut
from ..tasks.rematch import rematch_unmatched_faces

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
    try:
        embedding = get_engine().embed_single_face(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    user = None
    if user_id:
        existing = session.get(User, user_id)
        if existing:
            user = existing
            user.name = name
            user.email = email
            user.face_embedding = json.dumps(embedding)
        else:
            user = User(id=user_id, name=name, email=email, face_embedding=json.dumps(embedding))
    if user is None:
        user = User(name=name, email=email, face_embedding=json.dumps(embedding))

    selfie_key = f"selfies/{user.id}.jpg"
    await storage.put(selfie_key, image_bytes, selfie.content_type or "image/jpeg")
    user.selfie_path = selfie_key

    session.add(user)
    session.commit()
    session.refresh(user)

    # Auto-tag any photos already uploaded that contain this user's face.
    rematch_unmatched_faces(session, only_user=user)

    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        has_selfie=user.selfie_path is not None,
        selfie_url=storage.public_url(user.selfie_path) if user.selfie_path else None,
        created_at=user.created_at,
    )
