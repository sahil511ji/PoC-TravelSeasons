from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import db_session, get_storage
from ..models import TripDay, VideoRender
from ..schemas import VideoGenerateRequest, VideoRenderOut, VideoReviewRequest
from ..tasks.build_recap import run_recap

router = APIRouter(tags=["videos"])


def _to_out(vr: VideoRender, storage) -> VideoRenderOut:
    return VideoRenderOut(
        id=vr.id,
        trip_day_id=vr.trip_day_id,
        version=vr.version,
        status=vr.status,
        engine=vr.engine or "shotstack",
        mp4_url=storage.public_url(vr.mp4_storage_path) if vr.mp4_storage_path else None,
        duration_seconds=vr.duration_seconds,
        admin_notes=vr.admin_notes,
        created_at=vr.created_at,
        reviewed_at=vr.reviewed_at,
    )


@router.post("/trip-days/{day_id}/generate-recap", response_model=VideoRenderOut, status_code=202)
def generate_recap(
    day_id: str,
    background: BackgroundTasks,
    payload: VideoGenerateRequest | None = None,
    session: Session = Depends(db_session),
):
    day = session.get(TripDay, day_id)
    if day is None:
        raise HTTPException(status_code=404, detail="trip_day not found")
    if not (day.voiceover_script or "").strip():
        raise HTTPException(status_code=400, detail="voiceover_script empty — write/regenerate it first")

    # Determine next version
    latest = session.exec(
        select(VideoRender)
        .where(VideoRender.trip_day_id == day_id)
        .order_by(VideoRender.version.desc())  # type: ignore[attr-defined]
    ).first()
    next_version = (latest.version + 1) if latest else 1

    engine = (payload.renderer if payload else "remotion") or "remotion"

    vr = VideoRender(
        trip_day_id=day_id,
        version=next_version,
        status="queued",
        engine=engine,
    )
    session.add(vr)
    session.commit()
    session.refresh(vr)

    background.add_task(run_recap, vr.id)

    return _to_out(vr, get_storage())


@router.get("/video-renders", response_model=list[VideoRenderOut])
def list_video_renders(session: Session = Depends(db_session)):
    rows = session.exec(
        select(VideoRender).order_by(VideoRender.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    storage = get_storage()
    return [_to_out(r, storage) for r in rows]


@router.get("/video-renders/{video_id}", response_model=VideoRenderOut)
def get_video_render(video_id: str, session: Session = Depends(db_session)):
    vr = session.get(VideoRender, video_id)
    if vr is None:
        raise HTTPException(status_code=404, detail="video_render not found")
    return _to_out(vr, get_storage())


@router.post("/video-renders/{video_id}/approve", response_model=VideoRenderOut)
def approve_video(
    video_id: str,
    payload: VideoReviewRequest | None = None,
    session: Session = Depends(db_session),
):
    vr = session.get(VideoRender, video_id)
    if vr is None:
        raise HTTPException(status_code=404, detail="video_render not found")
    if vr.status != "pending_review":
        raise HTTPException(status_code=400, detail=f"cannot approve, status={vr.status}")
    vr.status = "approved"
    vr.reviewed_at = datetime.now(timezone.utc)
    if payload and payload.admin_notes is not None:
        vr.admin_notes = payload.admin_notes
    session.add(vr)
    session.commit()
    session.refresh(vr)
    return _to_out(vr, get_storage())


@router.post("/video-renders/{video_id}/reject", response_model=VideoRenderOut)
def reject_video(
    video_id: str,
    payload: VideoReviewRequest | None = None,
    session: Session = Depends(db_session),
):
    vr = session.get(VideoRender, video_id)
    if vr is None:
        raise HTTPException(status_code=404, detail="video_render not found")
    if vr.status not in ("pending_review", "approved"):
        raise HTTPException(status_code=400, detail=f"cannot reject, status={vr.status}")
    vr.status = "rejected"
    vr.reviewed_at = datetime.now(timezone.utc)
    if payload and payload.admin_notes is not None:
        vr.admin_notes = payload.admin_notes
    session.add(vr)
    session.commit()
    session.refresh(vr)
    return _to_out(vr, get_storage())
