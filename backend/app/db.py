from __future__ import annotations

import os
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings


def _build_engine():
    settings = get_settings()
    if settings.mode == "supabase":
        url = settings.SUPABASE_DB_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return create_engine(url, echo=False, pool_pre_ping=True)
    # local SQLite
    db_path = settings.LOCAL_DB_PATH
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    sqlite_url = f"sqlite:///{db_path}"
    return create_engine(
        sqlite_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def init_db() -> None:
    # Import models so SQLModel metadata is populated.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def session_scope() -> Session:
    """Direct session for background tasks (manage commit/close yourself)."""
    return Session(get_engine())
