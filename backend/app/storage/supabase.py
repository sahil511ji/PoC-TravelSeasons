from __future__ import annotations

from supabase import Client, create_client

from ..config import get_settings


class SupabaseStorage:
    def __init__(self, client: Client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        # supabase-py is sync; OK for PoC
        self.client.storage.from_(self.bucket).upload(
            path=key,
            file=data,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return key

    async def get_bytes(self, key: str) -> bytes:
        return self.client.storage.from_(self.bucket).download(key)

    def public_url(self, key: str) -> str:
        # supabase-py's get_public_url returns URLs with a trailing "?" which
        # some downstream consumers (e.g. Shotstack) silently fail on.
        url = self.client.storage.from_(self.bucket).get_public_url(key)
        return url.rstrip("?")

    async def delete(self, key: str) -> None:
        try:
            self.client.storage.from_(self.bucket).remove([key])
        except Exception:
            pass


def make_supabase_storage() -> SupabaseStorage:
    s = get_settings()
    client = create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY)
    return SupabaseStorage(client, s.SUPABASE_BUCKET)
