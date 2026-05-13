from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..config import get_settings
from ..deps import db_session
from ..face import get_engine
from ..schemas import HealthOut
from ..services import remotion
from ..tasks.rematch import rematch_all_unmatched

log = logging.getLogger(__name__)
router = APIRouter(tags=["meta"])


@router.get("/")
def root():
    return RedirectResponse(url="/admin/", status_code=307)


@router.get("/admin")
def admin_redirect():
    return RedirectResponse(url="/admin/", status_code=307)


@router.get("/health", response_model=HealthOut)
async def health():
    s = get_settings()
    face_count = 0
    try:
        info = await asyncio.to_thread(get_engine().describe_collection)
        face_count = int(info.get("face_count", 0))
    except Exception:
        log.warning("health: describe_collection unavailable", exc_info=False)
    return HealthOut(
        ok=True,
        mode=s.mode,
        face_engine="rekognition",
        collection=s.REKOGNITION_COLLECTION_ID,
        collection_face_count=face_count,
        threshold=s.REKOGNITION_FACE_MATCH_THRESHOLD,
    )


@router.post("/admin/rematch-all")
async def rematch_all(session: Session = Depends(db_session)):
    """Re-runs Rekognition matching for every active user against unmatched faces in the collection."""
    tagged = await asyncio.to_thread(rematch_all_unmatched, session)
    return {"newly_tagged": tagged}


@router.get("/health/renderer")
def renderer_health():
    """Probe the Remotion renderer service."""
    available = remotion.is_available()
    return {"renderer_available": available, "engine": "remotion"}
