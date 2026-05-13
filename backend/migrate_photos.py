"""One-shot: move existing 18 photos into a fresh Singapore trip and backfill
taken_at from EXIF. Safe to delete after first run."""
import io
import os
import uuid
from datetime import datetime

import piexif
from PIL import Image
from dotenv import load_dotenv
from sqlmodel import Session, create_engine, text
from supabase import create_client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

db_url = os.environ["SUPABASE_DB_URL"]
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(db_url)

client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
bucket = os.environ.get("SUPABASE_BUCKET", "travelseasons-poc")

with Session(engine) as s:
    new_trip_id = str(uuid.uuid4())
    s.execute(
        text(
            'insert into trip (id, name, start_date, end_date) '
            'values (:id, :name, :sd, :ed)'
        ),
        {"id": new_trip_id, "name": "Singapore Senior Special", "sd": "2026-10-12", "ed": "2026-10-18"},
    )
    print(f"Created trip: {new_trip_id}")

    res = s.execute(text("update photo set trip_id = :tid returning id, storage_path"), {"tid": new_trip_id})
    rows = res.fetchall()
    print(f"Moved {len(rows)} photos")

    updated = 0
    for photo_id, storage_path in rows:
        try:
            data = client.storage.from_(bucket).download(storage_path)
            img = Image.open(io.BytesIO(data))
            exif = piexif.load(img.info.get("exif", b""))
            dto = exif["Exif"].get(piexif.ExifIFD.DateTimeOriginal)
            if not dto:
                continue
            ts = datetime.strptime(dto.decode(), "%Y:%m:%d %H:%M:%S")
            s.execute(text("update photo set taken_at = :ta where id = :pid"), {"ta": ts.isoformat(), "pid": photo_id})
            updated += 1
        except Exception as e:
            print(f"  warn: photo {photo_id[:8]} -> {e}")

    s.commit()
    print(f"Backfilled taken_at on {updated} photos")
    print(f"\nNew trip_id = {new_trip_id}")
