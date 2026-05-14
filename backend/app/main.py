from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load .env so os.environ has the keys for service wrappers that don't go through Settings.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

import asyncio

from .config import get_settings
from .db import init_db
from .face import get_engine
from .routers import admin_pages, enrollments, photos, trip_days, trips, users, videos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ts")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    log.info(
        "starting backend mode=%s face_engine=rekognition collection=%s threshold=%.0f",
        s.mode, s.REKOGNITION_COLLECTION_ID, s.REKOGNITION_FACE_MATCH_THRESHOLD,
    )
    if s.mode == "local" and not s.AWS_ACCESS_KEY_ID:
        raise RuntimeError(
            "Face engine requires AWS credentials; local mode (SQLite) is unsupported. "
            "Configure SUPABASE_* + AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY."
        )
    init_db()
    # Ensure Rekognition collection exists. Soft-fail at startup if AWS unreachable
    # so the rest of the app (admin static, photo upload queue) still boots.
    try:
        result = await asyncio.to_thread(get_engine().ensure_collection)
        log.info("rekognition collection ready face_count=%d status=%s",
                 result["face_count"], result["status"])
    except Exception:
        log.exception("ensure_collection failed; face features will not work")

    yield


app = FastAPI(title="Travel Seasons PoC2", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# routers
app.include_router(admin_pages.router)
app.include_router(enrollments.router)
app.include_router(users.router)
app.include_router(trips.router)
app.include_router(photos.router)
app.include_router(trip_days.router)
app.include_router(videos.router)

# Static mounts
ROOT = Path(__file__).resolve().parent.parent  # backend/
ADMIN_DIR = (ROOT / ".." / "admin").resolve()
if ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")
    log.info("mounted /admin -> %s", ADMIN_DIR)
else:
    log.warning("admin dir not found at %s", ADMIN_DIR)

if settings.mode == "local":
    storage_dir = (ROOT / settings.LOCAL_STORAGE_DIR).resolve()
    os.makedirs(storage_dir, exist_ok=True)
    app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")
    log.info("mounted /storage -> %s", storage_dir)
