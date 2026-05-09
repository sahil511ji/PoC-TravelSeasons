from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_DB_URL: str = ""
    SUPABASE_BUCKET: str = "travelseasons-poc"

    LOCAL_DB_PATH: str = "./data/poc.db"
    LOCAL_STORAGE_DIR: str = "./storage_local"

    FACE_MATCH_THRESHOLD: float = 0.40
    FACE_MODEL: str = "buffalo_s"

    PUBLIC_BASE_URL: str = "http://localhost:8000"
    CORS_ORIGINS: str = "http://localhost:8000,http://localhost:3000,http://localhost:5173"

    @property
    def mode(self) -> Literal["local", "supabase"]:
        if self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY and self.SUPABASE_DB_URL:
            return "supabase"
        return "local"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
