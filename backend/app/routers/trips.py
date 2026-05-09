from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import db_session, get_storage
from ..models import Photo, Trip, TripUser, User
from ..schemas import TripCreate, TripOut, UserOut

router = APIRouter(prefix="/trips", tags=["trips"])


def _user_to_out(u: User, storage) -> UserOut:
    return UserOut(
        id=u.id,
        name=u.name,
        email=u.email,
        has_selfie=u.selfie_path is not None,
        selfie_url=storage.public_url(u.selfie_path) if u.selfie_path else None,
        created_at=u.created_at,
    )


@router.get("", response_model=list[TripOut])
def list_trips(session: Session = Depends(db_session)):
    storage = get_storage()
    trips = session.exec(select(Trip)).all()
    out: list[TripOut] = []
    for t in trips:
        photo_count = len(session.exec(select(Photo.id).where(Photo.trip_id == t.id)).all())
        member_ids = session.exec(
            select(TripUser.user_id).where(TripUser.trip_id == t.id)
        ).all()
        members: list[User] = []
        if member_ids:
            members = session.exec(select(User).where(User.id.in_(list(member_ids)))).all()  # type: ignore[attr-defined]
        out.append(
            TripOut(
                id=t.id,
                name=t.name,
                start_date=t.start_date,
                end_date=t.end_date,
                photo_count=photo_count,
                members=[_user_to_out(u, storage) for u in members],
            )
        )
    return out


@router.post("", response_model=TripOut, status_code=201)
def create_trip(payload: TripCreate, session: Session = Depends(db_session)):
    storage = get_storage()
    trip = Trip(name=payload.name, start_date=payload.start_date, end_date=payload.end_date)
    session.add(trip)
    session.commit()
    session.refresh(trip)

    members: list[User] = []
    for uid in payload.member_user_ids:
        u = session.get(User, uid)
        if u is None:
            continue
        session.add(TripUser(trip_id=trip.id, user_id=uid))
        members.append(u)
    session.commit()

    return TripOut(
        id=trip.id,
        name=trip.name,
        start_date=trip.start_date,
        end_date=trip.end_date,
        photo_count=0,
        members=[_user_to_out(u, storage) for u in members],
    )


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: str, session: Session = Depends(db_session)):
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")
    session.delete(trip)
    session.commit()
    return
