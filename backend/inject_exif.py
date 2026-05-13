"""One-shot: download every photo in the Supabase bucket, inject EXIF
timestamps spread across the Singapore Day 3 itinerary, re-upload."""
import io
import os
import random
from datetime import datetime, timedelta

import piexif
from PIL import Image
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
bucket = os.environ.get("SUPABASE_BUCKET", "travelseasons-poc")

# Singapore Day 3 itinerary windows
SLOTS = [
    ("Chinatown walking tour",  ( 9, 30), (11, 30), 4),
    ("Maxwell Food Centre",     (12,  0), (13, 30), 3),
    ("Cloud Forest Dome",       (14,  0), (16,  0), 5),
    ("Marina Bay SkyPark",      (16, 30), (18,  0), 3),
    ("Banana Leaf Apolo",       (19,  0), (20, 30), 3),
]

trip_id = "37709f96-d83b-45d1-9094-0f3ce7051d42"
listing = client.storage.from_(bucket).list(f"trip_photos/{trip_id}")
photo_keys = [f"trip_photos/{trip_id}/{x['name']}" for x in listing if x["name"].endswith(".jpg")]
print(f"Found {len(photo_keys)} photos in bucket")

assignments = []
i = 0
random.seed(42)
for slot_name, (sh, sm), (eh, em), count in SLOTS:
    start = datetime(2026, 10, 14, sh, sm)
    end = datetime(2026, 10, 14, eh, em)
    window = int((end - start).total_seconds())
    for _ in range(count):
        if i >= len(photo_keys):
            break
        offset = random.randint(0, window)
        assignments.append((photo_keys[i], start + timedelta(seconds=offset), slot_name))
        i += 1

while i < len(photo_keys):
    base = datetime(2026, 10, 14, 14, 0)
    assignments.append((photo_keys[i], base + timedelta(minutes=random.randint(0, 120)), "Cloud Forest Dome (extra)"))
    i += 1

assignments.sort(key=lambda a: a[1])

for key, ts, slot in assignments:
    data = client.storage.from_(bucket).download(key)
    img = Image.open(io.BytesIO(data))
    if img.mode != "RGB":
        img = img.convert("RGB")
    ts_str = ts.strftime("%Y:%m:%d %H:%M:%S").encode()
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"Apple",
            piexif.ImageIFD.Model: b"iPhone 14",
            piexif.ImageIFD.DateTime: ts_str,
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: ts_str,
            piexif.ExifIFD.DateTimeDigitized: ts_str,
        },
        "GPS": {},
        "1st": {},
        "thumbnail": None,
    }
    exif_bytes = piexif.dump(exif_dict)
    out = io.BytesIO()
    img.save(out, "jpeg", exif=exif_bytes, quality=92)
    out.seek(0)
    client.storage.from_(bucket).upload(
        key, out.read(), {"content-type": "image/jpeg", "upsert": "true"}
    )
    short = key.split("/")[-1][:8]
    print(f"[OK] {short}...  ts={ts.strftime('%H:%M')}  slot={slot}")

print("All done.")
