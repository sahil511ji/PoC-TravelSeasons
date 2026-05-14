"""Re-link unmatched faces to a user — Rekognition era.

The pipeline auto-indexes every detected face that has no matching enrolled
user, with ``ExternalImageId='unmatched:<photoface_id>'``. When a new user
enrols, we ask Rekognition which of those unmatched faces match the new
user's selfie and update the linkage.

The unmatched entries are deleted from the collection after linking, so
future searches stay clean.
"""
from __future__ import annotations

import logging

from sqlmodel import Session, select

from ..face import get_engine
from ..models import PhotoFace, User

log = logging.getLogger(__name__)


def rematch_unmatched_after_enrol(session: Session, new_user: User) -> int:
    """Called after IndexFaces succeeds for ``new_user``. Returns count of newly-tagged faces."""
    if not new_user.rekognition_face_id:
        return 0
    eng = get_engine()
    matches = eng.search_unmatched_for_user(new_user.rekognition_face_id, caller_user_id=new_user.id)
    # matches is already filtered to ExternalImageId starting with "unmatched:"
    tagged_face_ids: list[str] = []
    for face_id, eid, sim in matches:
        pf_id = eid.split(":", 1)[1]
        pf = session.get(PhotoFace, pf_id)
        if pf is None or pf.removed or pf.user_id is not None:
            continue
        pf.user_id = new_user.id
        pf.rekognition_face_id = new_user.rekognition_face_id
        pf.confidence = sim
        pf.source = "auto"
        pf.error = None
        session.add(pf)
        tagged_face_ids.append(face_id)
    if tagged_face_ids:
        session.commit()
        # Cleanup: drop the unmatched entries we just linked to keep the collection clean.
        try:
            eng.bulk_delete_faces(tagged_face_ids)
        except Exception:
            log.exception("bulk_delete_faces after rematch failed (non-fatal)")
        log.info("rematch tagged %d face(s) for user_id=%s", len(tagged_face_ids), new_user.id)
    return len(tagged_face_ids)


def rematch_all_unmatched(session: Session) -> int:
    """Admin endpoint helper: rematch for every enrolled, non-deleted user."""
    users = session.exec(
        select(User).where(
            User.deleted_at == None,  # noqa: E711
            User.rekognition_face_id != None,  # noqa: E711
        )
    ).all()
    return sum(rematch_unmatched_after_enrol(session, u) for u in users)
