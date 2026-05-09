from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Header
from sqlmodel import Session

from .config import get_settings
from .db import get_session
from .storage.base import Storage


def db_session() -> Iterator[Session]:
    yield from get_session()


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    s = get_settings()
    if s.mode == "supabase":
        from .storage.supabase import make_supabase_storage

        return make_supabase_storage()
    from .storage.local import make_local_storage

    return make_local_storage()


def x_user_id(x_user_id: str | None = Header(default=None)) -> str | None:
    return x_user_id
