from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..config import get_settings
from ..deps import db_session
from ..schemas import HealthOut
from ..tasks.rematch import rematch_unmatched_faces

router = APIRouter(tags=["meta"])


@router.get("/")
def root():
    return RedirectResponse(url="/admin/", status_code=307)


@router.get("/admin")
def admin_redirect():
    return RedirectResponse(url="/admin/", status_code=307)


@router.get("/health", response_model=HealthOut)
def health():
    s = get_settings()
    return HealthOut(
        ok=True,
        mode=s.mode,
        model=s.FACE_MODEL,
        threshold=s.FACE_MATCH_THRESHOLD,
    )


@router.post("/admin/rematch-all")
def rematch_all(session: Session = Depends(db_session)):
    """Re-runs matching on all unmatched, non-removed face rows."""
    tagged = rematch_unmatched_faces(session)
    return {"newly_tagged": tagged}
