"""Background pipeline: detect faces in a photo, match to enrolled users, persist."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone

from fastapi import BackgroundTasks
from PIL import Image
from sqlmodel import select

from ..db import session_scope
from ..deps import get_storage
from ..face.engine import get_engine
from ..face.matcher import best_match
from ..models import Photo, PhotoFace, User

log = logging.getLogger(__name__)

# Limit concurrent face inference to avoid CPU thrash.
_engine_semaphore = threading.Semaphore(2)


def schedule_photo_processing(background: BackgroundTasks, photo_id: str) -> None:
    background.add_task(_run_async, photo_id)


def _run_async(photo_id: str) -> None:
    """Entry point for FastAPI BackgroundTasks (sync function executed in threadpool)."""
    try:
        asyncio.run(_process_one_photo(photo_id))
    except Exception:
        log.exception("Background photo processing crashed for %s", photo_id)


async def _process_one_photo(photo_id: str) -> None:
    storage = get_storage()
    with session_scope() as session:
        photo = session.get(Photo, photo_id)
        if photo is None:
            log.warning("Photo %s missing at processing time", photo_id)
            return
        photo.status = "processing"
        session.add(photo)
        session.commit()

    try:
        image_bytes = await storage.get_bytes(
            (await _get_storage_path(photo_id)) or ""
        )
        # Image dims for UI sizing
        width = height = None
        try:
            from io import BytesIO

            with Image.open(BytesIO(image_bytes)) as img:
                width, height = img.size
        except Exception:
            pass

        # Inference (CPU-bound) — guarded by semaphore.
        with _engine_semaphore:
            faces = get_engine().detect_faces(image_bytes)

        with session_scope() as session:
            users = session.exec(
                select(User).where(User.face_embedding != None, User.deleted_at == None)  # noqa: E711
            ).all()

            for face in faces:
                match = best_match(face.embedding, users)
                pf = PhotoFace(
                    photo_id=photo_id,
                    user_id=match.user.id if match else None,
                    bbox=json.dumps(face.bbox),
                    embedding=json.dumps(face.embedding),
                    confidence=match.similarity if match else None,
                    source="auto",
                    removed=False,
                )
                session.add(pf)

            ph = session.get(Photo, photo_id)
            if ph is not None:
                ph.status = "done"
                ph.processed_at = datetime.now(timezone.utc)
                ph.width = width
                ph.height = height
                session.add(ph)
            session.commit()

    except Exception as e:  # noqa: BLE001
        log.exception("Failed processing photo %s", photo_id)
        with session_scope() as session:
            ph = session.get(Photo, photo_id)
            if ph is not None:
                ph.status = "failed"
                ph.error = str(e)[:500]
                session.add(ph)
                session.commit()


async def _get_storage_path(photo_id: str) -> str | None:
    with session_scope() as session:
        ph = session.get(Photo, photo_id)
        return ph.storage_path if ph else None
