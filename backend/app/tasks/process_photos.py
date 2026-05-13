"""Background pipeline: detect faces in a photo via AWS Rekognition, persist.

Synchronous flow — boto3 is sync; running under FastAPI's BackgroundTasks
threadpool. We wrap the storage abstraction (async) in ``asyncio.run`` since
this function itself is sync.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from io import BytesIO

from fastapi import BackgroundTasks
from PIL import Image
from sqlmodel import select

from ..db import session_scope
from ..deps import get_storage
from ..face import crop_face, get_engine
from ..models import Photo, PhotoFace

log = logging.getLogger(__name__)

# CPU-bound Pillow ops still benefit from a small bound.
_engine_semaphore = threading.Semaphore(4)


def schedule_photo_processing(background: BackgroundTasks, photo_id: str) -> None:
    background.add_task(_run, photo_id)


def _run(photo_id: str) -> None:
    """Entry point for FastAPI BackgroundTasks (sync function in Starlette threadpool)."""
    try:
        _process_one_photo(photo_id)
    except Exception:
        log.exception("Background photo processing crashed for %s", photo_id)


def _process_one_photo(photo_id: str) -> None:
    storage = get_storage()

    # 1. Mark processing
    with session_scope() as s:
        photo = s.get(Photo, photo_id)
        if photo is None:
            log.warning("Photo %s missing at processing time", photo_id)
            return
        photo.status = "processing"
        s.add(photo)
        s.commit()
        storage_path = photo.storage_path

    try:
        # 2. Load bytes (storage abstraction is async — run from sync context)
        image_bytes = asyncio.run(storage.get_bytes(storage_path))

        # 3. Image dimensions for UI sizing (in semaphore — CPU work)
        width: int | None = None
        height: int | None = None
        with _engine_semaphore:
            try:
                with Image.open(BytesIO(image_bytes)) as img:
                    width, height = img.size
            except Exception:
                pass

        # 4. AWS Rekognition: detect + match
        result = get_engine().detect_and_match(image_bytes)

        # 5. Persist
        with session_scope() as s:
            ph = s.get(Photo, photo_id)
            if ph is None:
                return

            if result.photo_error:
                ph.status = "failed"
                ph.error = result.photo_error[:500]
                s.add(ph)
                s.commit()
                return

            for face in result.faces:
                # A match against an "unmatched:<id>" ExternalImageId means the
                # face matches another previously-unmatched face, not a real user.
                # Treat as unmatched for DB purposes.
                eid = face.matched_external_id
                is_real_user_match = eid is not None and not eid.startswith("unmatched:")

                pf = PhotoFace(
                    photo_id=photo_id,
                    user_id=eid if is_real_user_match else None,
                    bbox=json.dumps(face.bbox),
                    bbox_space="normalised",
                    embedding=None,
                    rekognition_face_id=face.matched_face_id if is_real_user_match else None,
                    confidence=face.match_similarity if is_real_user_match else None,
                    source="auto",
                    removed=False,
                    error=face.error,
                )
                s.add(pf)
                s.flush()  # need pf.id below

                # For unmatched faces (no enrolled user yet), index the crop into
                # the collection so a future enrol can link it via SearchFaces.
                if not is_real_user_match and face.error is None:
                    try:
                        with _engine_semaphore:
                            crop_bytes, crop_err = crop_face(image_bytes, face.bbox)
                        if crop_bytes:
                            rek_id = get_engine().index_unmatched(crop_bytes, pf.id)
                            if rek_id:
                                pf.rekognition_face_id = rek_id
                                s.add(pf)
                    except Exception:
                        log.exception("index_unmatched failed photoface_id=%s", pf.id)

            ph.status = "done"
            ph.processed_at = datetime.now(timezone.utc)
            ph.width = width
            ph.height = height
            ph.error = None
            s.add(ph)
            s.commit()

    except Exception as e:
        log.exception("Failed processing photo %s", photo_id)
        with session_scope() as s:
            ph = s.get(Photo, photo_id)
            if ph is not None:
                ph.status = "failed"
                ph.error = str(e)[:500]
                s.add(ph)
                s.commit()
