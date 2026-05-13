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
    TripDayCreate,
    TripDayOut,
    TripDaySummaryOut,
    TripDayUpdate,
    VideoRenderOut,
)
from ..services.exif import match_to_itinerary
from ..services.llm import LLMError, structure_itinerary

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


@router.delete("/trip-days/{day_id}", status_code=204)
def delete_trip_day(day_id: str, session: Session = Depends(db_session)):
    day = session.get(TripDay, day_id)
    if day is None:
        raise HTTPException(status_code=404, detail="trip_day not found")
    session.delete(day)
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
    session.commit()
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


# ---------- helpers ----------

def _rematch_photos_in_day(session: Session, day: TripDay) -> int:
    """For photos in this trip whose taken_at date matches this day's date,
    re-assign itinerary_item_id."""
    photos = session.exec(
        select(Photo).where(Photo.trip_id == day.trip_id, Photo.taken_at.is_not(None))  # type: ignore[attr-defined]
    ).all()
    matched = 0
    for p in photos:
        if not p.taken_at or p.taken_at.date() != day.date:
            continue
        item_id = match_to_itinerary(session, trip_id=day.trip_id, taken_at=p.taken_at)
        if item_id and p.itinerary_item_id != item_id:
            p.itinerary_item_id = item_id
            session.add(p)
            matched += 1
    return matched


def _day_to_out(session: Session, day: TripDay) -> TripDayOut:
    storage = get_storage()

    items = session.exec(
        select(ItineraryItem)
        .where(ItineraryItem.trip_day_id == day.id)
        .order_by(ItineraryItem.position)  # type: ignore[arg-type]
    ).all()

    item_counts: dict[str, int] = {}
    photo_count = 0
    for i in items:
        n = len(session.exec(
            select(Photo.id).where(Photo.itinerary_item_id == i.id)
        ).all())
        item_counts[i.id] = n
        photo_count += n

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
            photo_count=item_counts[i.id],
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
        photo_count=photo_count,
        latest_video=latest_out,
    )
