"""Re-run face matching on photo_faces rows that didn't match a user when first processed.

Triggered after a new enrollment so previously-uploaded photos get tagged automatically.
"""
from __future__ import annotations

import json
import logging

from sqlmodel import Session, select

from ..face.matcher import best_match
from ..models import PhotoFace, User

log = logging.getLogger(__name__)


def rematch_unmatched_faces(session: Session, *, only_user: User | None = None) -> int:
    """Re-runs matching on every unmatched, non-removed PhotoFace row.

    If `only_user` is provided, only checks that user's embedding (faster path
    after a single new enrollment). Returns count of newly-tagged faces.
    """
    if only_user is not None:
        users = [only_user] if only_user.face_embedding else []
    else:
        users = session.exec(
            select(User).where(
                User.face_embedding != None,  # noqa: E711
                User.deleted_at == None,  # noqa: E711
            )
        ).all()

    if not users:
        return 0

    unmatched = session.exec(
        select(PhotoFace).where(
            PhotoFace.user_id == None,  # noqa: E711
            PhotoFace.removed == False,  # noqa: E712
        )
    ).all()

    tagged = 0
    for face in unmatched:
        try:
            embedding = json.loads(face.embedding)
        except (json.JSONDecodeError, TypeError):
            continue
        match = best_match(embedding, users)
        if match is None:
            continue
        face.user_id = match.user.id
        face.confidence = match.similarity
        face.source = "auto"
        session.add(face)
        tagged += 1

    if tagged:
        session.commit()
        log.info("rematch tagged %d face(s)", tagged)
    return tagged
