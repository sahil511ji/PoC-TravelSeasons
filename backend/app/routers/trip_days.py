from __future__ import annotations

import json
import uuid
from datetime import time as time_type

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import db_session, get_storage
from ..models import ItineraryItem, Photo, Trip, TripDay, VideoRender
from ..schemas import (
    ItineraryItemOut,
    ItineraryItemUpdate,
    RecapPhotosUpdate,
    TripDayCreate,
    TripDayOut,
    TripDaySummaryOut,
    TripDayUpdate,
    VideoRenderOut,
)
from ..services.exif import match_to_itinerary
from ..services.llm import LLMError, edit_voiceover_script, structure_itinerary

SECONDS_PER_PHOTO = 3  # admin-chosen pacing: ~3s of voiceover per selected photo

router = APIRouter(tags=["trip_days"])


def _parse_time(s: str | None) -> time_type | None:
    if not s:
        return None
    try:
        h, m = s.split(":")
        return time_type(hour=int(h), minute=int(m))
    except (ValueError, AttributeError):
        return None


@router.post("/trips/{trip_id}/days", response_model=TripDayOut, status_code=201)
def create_trip_day(
    trip_id: str,
    payload: TripDayCreate,
    session: Session = Depends(db_session),
):
    """Send raw TM text → Gemini structures itinerary + writes voiceover script → store."""
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")

    try:
        parsed = structure_itinerary(payload.raw_text, payload.date)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM failed: {e}") from e

    # Use explicit fields if user supplied them; else what Gemini extracted.
    day = TripDay(
        trip_id=trip_id,
        date=payload.date,
        raw_text=payload.raw_text,
        theme=payload.theme or parsed.get("theme"),
        weather=payload.weather or parsed.get("weather"),
        tour_manager=payload.tour_manager or parsed.get("tour_manager"),
        voiceover_script=parsed.get("voiceover_script"),
        filmable_moments=parsed.get("filmable_moments"),
    )
    session.add(day)
    session.flush()

    items_data = parsed.get("items") or []
    # Safety net: even if Gemini ignores the rule, never persist zero-duration
    # windows. Tile end_time = next item's start_time; last item gets +15 min.
    parsed_pairs: list[tuple[time_type | None, time_type | None]] = [
        (_parse_time(d.get("start_time")), _parse_time(d.get("end_time")))
        for d in items_data
    ]
    from datetime import datetime as _dt, timedelta as _td
    for i, (st, et) in enumerate(parsed_pairs):
        if st is None:
            continue
        if et is None or et <= st:
            # Find next item's start to tile against
            next_st = None
            for j in range(i + 1, len(parsed_pairs)):
                if parsed_pairs[j][0] is not None:
                    next_st = parsed_pairs[j][0]
                    break
            if next_st is not None and next_st > st:
                parsed_pairs[i] = (st, next_st)
            else:
                # Last item or no later start — add 15 minutes
                end = (_dt.combine(_dt.today(), st) + _td(minutes=15)).time()
                parsed_pairs[i] = (st, end)

    items_out: list[ItineraryItem] = []
    for pos, (item_data, (st, et)) in enumerate(zip(items_data, parsed_pairs)):
        item = ItineraryItem(
            trip_day_id=day.id,
            start_time=st,
            end_time=et,
            title=item_data.get("title", "Untitled"),
            description=item_data.get("description"),
            caption=item_data.get("caption"),
            importance=int(item_data.get("importance") or 5),
            position=pos,
        )
        session.add(item)
        items_out.append(item)
    session.commit()
    for i in items_out:
        session.refresh(i)
    session.refresh(day)

    # Auto-match existing photos in this trip that fall in this day's date
    matched = _rematch_photos_in_day(session, day)
    if matched:
        session.commit()

    return _day_to_out(session, day)


@router.post("/trip-days/{day_id}/rematch-photos")
def rematch_photos(day_id: str, session: Session = Depends(db_session)):
    day = session.get(TripDay, day_id)
    if day is None:
        raise HTTPException(status_code=404, detail="trip_day not found")
    matched = _rematch_photos_in_day(session, day)
    session.commit()
    return {"matched": matched}


@router.get("/trips/{trip_id}/days", response_model=list[TripDaySummaryOut])
def list_days(trip_id: str, session: Session = Depends(db_session)):
    days = session.exec(
        select(TripDay).where(TripDay.trip_id == trip_id).order_by(TripDay.date)  # type: ignore[arg-type]
    ).all()
    out: list[TripDaySummaryOut] = []
    for d in days:
        photos_count = len(session.exec(
            select(Photo.id)
            .join(ItineraryItem, ItineraryItem.id == Photo.itinerary_item_id)
            .where(ItineraryItem.trip_day_id == d.id)
        ).all())
        approved = session.exec(
            select(VideoRender.id).where(
                VideoRender.trip_day_id == d.id,
                VideoRender.status == "approved",
            )
        ).first()
        out.append(TripDaySummaryOut(
            id=d.id,
            date=d.date,
            theme=d.theme,
            photo_count=photos_count,
            has_approved_video=approved is not None,
        ))
    return out


@router.get("/trip-days/{day_id}", response_model=TripDayOut)
def get_trip_day(day_id: str, session: Session = Depends(db_session)):
    day = session.get(TripDay, day_id)
    if day is None:
        raise HTTPException(status_code=404, detail="trip_day not found")
    return _day_to_out(session, day)


@router.patch("/trip-days/{day_id}", response_model=TripDayOut)
def update_trip_day(
    day_id: str, payload: TripDayUpdate, session: Session = Depends(db_session)
):
    day = session.get(TripDay, day_id)
    if day is None:
        raise HTTPException(status_code=404, detail="trip_day not found")
    if payload.theme is not None:
        day.theme = payload.theme
    if payload.tour_manager is not None:
        day.tour_manager = payload.tour_manager
    if payload.weather is not None:
        day.weather = payload.weather
    if payload.voiceover_script is not None:
        day.voiceover_script = payload.voiceover_script
    session.add(day)
    session.commit()
    session.refresh(day)
    return _day_to_out(session, day)


@router.post("/trip-days/{day_id}/edit-script-ai")
def edit_script_ai(
    day_id: str, payload: dict, session: Session = Depends(db_session)
):
    """Rewrite the day's voiceover_script via Gemini, given admin instructions.

    Target duration is derived from the number of currently-selected photos
    (recap_position IS NOT NULL) at SECONDS_PER_PHOTO seconds each. AI only sees
    the existing script + the admin's instructions + the target word count —
    it does NOT see per-photo metadata.
    """
    day = session.get(TripDay, day_id)
    if day is None:
        raise HTTPException(status_code=404, detail="trip_day not found")
    instructions = (payload or {}).get("instructions", "").strip()
    if not instructions:
        raise HTTPException(status_code=400, detail="instructions are required")
    if not (day.voiceover_script or "").strip():
        raise HTTPException(
            status_code=400,
            detail="day has no voiceover_script yet — generate it first",
        )

    photo_count = session.exec(
        select(Photo.id)
        .join(ItineraryItem, ItineraryItem.id == Photo.itinerary_item_id)
        .where(
            ItineraryItem.trip_day_id == day_id,
            Photo.recap_position.is_not(None),  # type: ignore[attr-defined]
        )
    ).all()
    n_photos = len(photo_count)
    # If zero photos selected, fall back to a 30s default so AI still produces useful output.
    target_seconds = max(15, n_photos * SECONDS_PER_PHOTO) if n_photos else 30

    try:
        new_script = edit_voiceover_script(
            day.voiceover_script, instructions, target_seconds
        )
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"Gemini edit failed: {e}") from e

    day.voiceover_script = new_script
    session.add(day)
    session.commit()
    session.refresh(day)
    return {
        "voiceover_script": new_script,
        "photo_count": n_photos,
        "target_seconds": target_seconds,
        "target_words": target_seconds * 2,
    }


@router.delete("/trip-days/{day_id}", status_code=204)
def delete_trip_day(day_id: str, session: Session = Depends(db_session)):
    from sqlalchemy import text as _text
    day = session.get(TripDay, day_id)
    if day is None:
        raise HTTPException(status_code=404, detail="trip_day not found")
    trip_id = day.trip_id
    session.delete(day)  # cascade deletes items; FK SET NULL on photos.itinerary_item_id
    session.commit()
    # Stale recap_position values on the now-orphaned photos → null them.
    session.exec(
        _text(
            "UPDATE photo SET recap_position = NULL "
            "WHERE trip_id = :tid AND itinerary_item_id IS NULL"
        ).bindparams(tid=trip_id)
    )
    session.commit()


@router.patch("/itinerary-items/{item_id}", response_model=ItineraryItemOut)
def update_itinerary_item(
    item_id: str,
    payload: ItineraryItemUpdate,
    session: Session = Depends(db_session),
):
    """Edit an itinerary item (title/times/importance). Auto-rematches photos
    in the parent day to keep linkages fresh."""
    item = session.get(ItineraryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="itinerary_item not found")
    if payload.start_time is not None:
        item.start_time = payload.start_time
    if payload.end_time is not None:
        item.end_time = payload.end_time
    if payload.title is not None:
        item.title = payload.title
    if payload.description is not None:
        item.description = payload.description
    if payload.importance is not None:
        item.importance = max(1, min(10, int(payload.importance)))
    session.add(item)
    session.flush()        # write without committing — single transaction
    session.refresh(item)

    # Auto-rematch photos in this day so the photo counts update immediately.
    day = session.get(TripDay, item.trip_day_id)
    if day is not None:
        _rematch_photos_in_day(session, day)
    session.commit()

    photo_count = len(session.exec(
        select(Photo.id).where(Photo.itinerary_item_id == item.id)
    ).all())
    return ItineraryItemOut(
        id=item.id,
        position=item.position,
        start_time=item.start_time,
        end_time=item.end_time,
        title=item.title,
        description=item.description,
        caption=item.caption,
        importance=item.importance,
        photo_count=photo_count,
    )


@router.patch("/trip-days/{day_id}/recap-photos")
def update_recap_photos(
    day_id: str,
    payload: RecapPhotosUpdate,
    session: Session = Depends(db_session),
):
    """Replace-all selection + order for a day's recap photos.

    Body: ``{ordered_photo_ids: [...]}``. Photos in the list get
    ``recap_position`` assigned by index (1-based). Every other photo in this
    day gets ``recap_position = NULL``.
    """
    from sqlalchemy import text as _text

    import logging as _logging
    _log = _logging.getLogger("recap-order")
    _log.info("[PATCH /recap-photos] day=%s payload ordered_photo_ids=%s",
              day_id, payload.ordered_photo_ids)

    day = session.get(TripDay, day_id)
    if day is None:
        raise HTTPException(status_code=404, detail="trip_day not found")

    # Collect the day's items
    items = session.exec(
        select(ItineraryItem.id).where(ItineraryItem.trip_day_id == day_id)
    ).all()
    item_ids = [i for i in items]
    if not item_ids:
        # No items → only valid request is an empty list
        if payload.ordered_photo_ids:
            raise HTTPException(
                status_code=400,
                detail="Day has no itinerary items — no photos can be in its recap.",
            )
        return {"selected": 0, "deselected": 0}

    # Validate every id belongs to this day. Reject all on any mismatch.
    if payload.ordered_photo_ids:
        valid_ids = set(session.exec(
            select(Photo.id).where(
                Photo.id.in_(payload.ordered_photo_ids),  # type: ignore[attr-defined]
                Photo.itinerary_item_id.in_(item_ids),  # type: ignore[attr-defined]
            )
        ).all())
        invalid = [pid for pid in payload.ordered_photo_ids if pid not in valid_ids]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Photos no longer in this day: {invalid}. Refresh the page.",
            )

    # Apply replace-all in a single transaction.
    if payload.ordered_photo_ids:
        # 1) Set recap_position for selected ids — one round-trip per photo.
        #    Could use a single VALUES round-trip; PoC volume makes this trivial.
        for idx, pid in enumerate(payload.ordered_photo_ids, start=1):
            p = session.get(Photo, pid)
            if p is not None:
                p.recap_position = idx
                session.add(p)

    # 2) NULL out everything else in this day.
    keep_ids = set(payload.ordered_photo_ids)
    others = session.exec(
        select(Photo).where(
            Photo.itinerary_item_id.in_(item_ids),  # type: ignore[attr-defined]
            Photo.recap_position.is_not(None),  # type: ignore[attr-defined]
        )
    ).all()
    for p in others:
        if p.id not in keep_ids:
            p.recap_position = None
            session.add(p)
    session.commit()

    # Count for response
    selected = len(payload.ordered_photo_ids)
    total = session.exec(
        select(Photo.id).where(Photo.itinerary_item_id.in_(item_ids))  # type: ignore[attr-defined]
    ).all()
    deselected = len(total) - selected

    # Verbose verification log: read back recap_position state
    verify = session.exec(
        select(Photo.id, Photo.recap_position)
        .where(Photo.itinerary_item_id.in_(item_ids))  # type: ignore[attr-defined]
        .order_by(Photo.recap_position.asc().nulls_last())  # type: ignore[attr-defined]
    ).all()
    _log.info(
        "[PATCH /recap-photos] day=%s after-save state (id, recap_position): %s",
        day_id, [(pid[:8], pos) for pid, pos in verify],
    )
    return {"selected": selected, "deselected": deselected}


# ---------- helpers ----------

def _rematch_photos_in_day(session: Session, day: TripDay) -> int:
    """For photos in this trip whose taken_at date matches this day's date,
    re-assign itinerary_item_id. Preserves admin's recap curation:

    - Same-day item swap → recap_position untouched (drag order stays).
    - Photo joining the day for the first time (old_iid was None) → recap_position
      set to max+1 (appended).
    - Photo falling out of all items in this day → itinerary_item_id + recap_position
      both NULLed.
    """
    from sqlalchemy import text as _text  # local import to keep file's top tidy
    photos = session.exec(
        select(Photo).where(Photo.trip_id == day.trip_id, Photo.taken_at.is_not(None))  # type: ignore[attr-defined]
    ).all()
    matched = 0
    new_day_max: int | None = None  # cache; populated on first "new entrant"
    for p in photos:
        if not p.taken_at or p.taken_at.date() != day.date:
            continue
        old_iid = p.itinerary_item_id
        new_iid = match_to_itinerary(session, trip_id=day.trip_id, taken_at=p.taken_at)
        if new_iid == old_iid:
            continue
        if new_iid is None:
            # Photo no longer fits any item in this day → drop from recap.
            p.itinerary_item_id = None
            p.recap_position = None
        else:
            p.itinerary_item_id = new_iid
            if old_iid is None:
                # Photo joining the day for the first time → append.
                if new_day_max is None:
                    new_day_max = session.exec(
                        _text(
                            "SELECT COALESCE(MAX(p.recap_position), 0) "
                            "FROM photo p JOIN itinerary_item ii ON ii.id = p.itinerary_item_id "
                            "WHERE ii.trip_day_id = :did"
                        ).bindparams(did=day.id)
                    ).scalar() or 0
                new_day_max += 1
                p.recap_position = new_day_max
            # else: same-day swap → recap_position preserved.
        session.add(p)
        matched += 1
    return matched


def _day_to_out(session: Session, day: TripDay) -> TripDayOut:
    from ..models import PhotoFace, User
    from .photos import _photo_to_out
    storage = get_storage()

    items = session.exec(
        select(ItineraryItem)
        .where(ItineraryItem.trip_day_id == day.id)
        .order_by(ItineraryItem.position)  # type: ignore[arg-type]
    ).all()
    item_ids = [i.id for i in items]

    # Per-item photo counts (used in items_out)
    item_counts: dict[str, int] = {i.id: 0 for i in items}

    # Photos for this day — selected first by recap_position, then unselected (NULLS LAST)
    photos: list[Photo] = []
    if item_ids:
        photos = list(session.exec(
            select(Photo)
            .where(Photo.itinerary_item_id.in_(item_ids))  # type: ignore[attr-defined]
            .order_by(
                Photo.recap_position.asc().nulls_last(),  # type: ignore[attr-defined]
                Photo.taken_at,
                Photo.id,
            )
        ).all())
    for p in photos:
        item_counts[p.itinerary_item_id] = item_counts.get(p.itinerary_item_id, 0) + 1
    photo_count = sum(item_counts.values())

    # Batched face fetch (one query, group in Python)
    photo_ids = [p.id for p in photos]
    face_rows: list[PhotoFace] = []
    if photo_ids:
        face_rows = list(session.exec(
            select(PhotoFace).where(
                PhotoFace.photo_id.in_(photo_ids),  # type: ignore[attr-defined]
                PhotoFace.removed == False,  # noqa: E712
            )
        ).all())
    faces_by_photo: dict[str, list[PhotoFace]] = {}
    for f in face_rows:
        faces_by_photo.setdefault(f.photo_id, []).append(f)

    # Users named in faces — single fetch
    user_ids = {f.user_id for f in face_rows if f.user_id}
    users_by_id: dict[str, User] = {}
    if user_ids:
        users_by_id = {
            u.id: u for u in session.exec(
                select(User).where(User.id.in_(list(user_ids)))  # type: ignore[attr-defined]
            ).all()
        }

    photos_out = [
        _photo_to_out(p, faces_by_photo.get(p.id, []), users_by_id, storage)
        for p in photos
    ]

    items_out = [
        ItineraryItemOut(
            id=i.id,
            position=i.position,
            start_time=i.start_time,
            end_time=i.end_time,
            title=i.title,
            description=i.description,
            caption=i.caption,
            importance=i.importance,
            photo_count=item_counts.get(i.id, 0),
        )
        for i in items
    ]

    latest_render = session.exec(
        select(VideoRender)
        .where(VideoRender.trip_day_id == day.id)
        .order_by(VideoRender.version.desc())  # type: ignore[attr-defined]
    ).first()

    latest_out = None
    if latest_render is not None:
        latest_out = VideoRenderOut(
            id=latest_render.id,
            trip_day_id=latest_render.trip_day_id,
            version=latest_render.version,
            status=latest_render.status,
            mp4_url=(storage.public_url(latest_render.mp4_storage_path)
                     if latest_render.mp4_storage_path else None),
            duration_seconds=latest_render.duration_seconds,
            admin_notes=latest_render.admin_notes,
            error=latest_render.error,
            created_at=latest_render.created_at,
            reviewed_at=latest_render.reviewed_at,
        )

    moments = day.filmable_moments
    if isinstance(moments, str):
        try:
            moments = json.loads(moments)
        except (TypeError, json.JSONDecodeError):
            moments = None

    return TripDayOut(
        id=day.id,
        trip_id=day.trip_id,
        date=day.date,
        theme=day.theme,
        weather=day.weather,
        tour_manager=day.tour_manager,
        voiceover_script=day.voiceover_script,
        filmable_moments=moments,
        items=items_out,
        photos=photos_out,
        photo_count=photo_count,
        latest_video=latest_out,
    )
