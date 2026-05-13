"""EXIF helpers + itinerary matching."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

import piexif
from PIL import Image
from sqlmodel import Session, select

from ..models import ItineraryItem, TripDay


def read_taken_at(image_bytes: bytes) -> datetime | None:
    """Returns the EXIF DateTimeOriginal (or DateTime) as a naive datetime, or None."""
    try:
        img = Image.open(BytesIO(image_bytes))
        exif = piexif.load(img.info.get("exif", b""))
    except Exception:
        return None
    dto = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
    if not dto:
        dto = exif.get("0th", {}).get(piexif.ImageIFD.DateTime)
    if not dto:
        return None
    try:
        s = dto.decode() if isinstance(dto, bytes) else dto
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def match_to_itinerary(
    session: Session, *, trip_id: str, taken_at: datetime
) -> str | None:
    """Returns itinerary_item_id whose [start_time, end_time] window contains taken_at,
    AND whose trip_day.date matches the photo's date."""
    if not taken_at:
        return None
    day = session.exec(
        select(TripDay).where(TripDay.trip_id == trip_id, TripDay.date == taken_at.date())
    ).first()
    if not day:
        return None
    target_time = taken_at.time()
    items = session.exec(
        select(ItineraryItem)
        .where(ItineraryItem.trip_day_id == day.id)
        .order_by(ItineraryItem.position)  # type: ignore[arg-type]
    ).all()
    for item in items:
        st = item.start_time
        et = item.end_time
        if st is None and et is None:
            continue
        if st and et and st <= target_time <= et:
            return item.id
        if st and not et and target_time >= st:
            return item.id
    return None
