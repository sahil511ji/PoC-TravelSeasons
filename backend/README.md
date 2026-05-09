# Travel Seasons — PoC 2 backend

FastAPI + facenet-pytorch + Supabase (with SQLite/local-disk fallback).

## What this is

Implements the **Photo Gallery + Face Tagging** PoC end-to-end:

- Customer enrollment with selfie → face embedding stored
- Admin bulk uploads trip photos → background pipeline detects faces, matches to enrolled users, persists tags
- Customer / admin can list trip photos with filters: `all` / `me` / `group`
- Admin can override (remove / add) tags on any photo
- Soft-delete users (DPDP-style endpoint, even though consent UI is skipped for PoC)

## Stack

- **FastAPI 0.115** + uvicorn
- **facenet-pytorch 2.6** (MTCNN detector + InceptionResnetV1 encoder, VGGFace2 weights, 512-dim L2-normalised embeddings)
- **SQLModel / SQLAlchemy** — same model classes work on SQLite + Postgres
- **Supabase** for hosted Postgres + Storage when env vars are set; otherwise SQLite + local disk

## Quick start (Windows / PowerShell)

```powershell
cd c:\travelseason_POC\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel
pip install -r requirements.txt
Copy-Item .env.example .env

# (Optional) warm-load the face models so first request isn't slow (~120 MB download)
python -c "from app.face.engine import get_engine; get_engine()"

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

- Admin panel: <http://localhost:8000/admin/>
- Health: <http://localhost:8000/health>
- Swagger: <http://localhost:8000/docs>

### Why facenet-pytorch (not InsightFace)

The plan originally specified InsightFace, but `insightface==0.7.3` does not ship Windows wheels for Python ≥ 3.11 — it tries to compile a Cython extension and needs MSVC build tools. To keep the install dependency-free on Windows, we pivoted to **facenet-pytorch**, which provides equivalent functionality (MTCNN detection + 512-dim face embeddings) with prebuilt wheels for all current Python versions. Production migration to either InsightFace or AWS Rekognition is a localised change to `app/face/engine.py` only — the API surface (`detect_faces`, `embed_single_face`) is the same.

## Environment variables

See `.env.example`. Key ones:

| Var | Default | Notes |
|---|---|---|
| `SUPABASE_URL` | (empty) | If set, mode = `supabase`; otherwise SQLite + local disk |
| `SUPABASE_SERVICE_ROLE_KEY` | (empty) | Service-role key (NOT anon) |
| `SUPABASE_DB_URL` | (empty) | `postgresql+psycopg://…` connection string |
| `SUPABASE_BUCKET` | `travelseasons-poc` | Public bucket name in Supabase Storage |
| `LOCAL_DB_PATH` | `./data/poc.db` | SQLite file (local mode) |
| `LOCAL_STORAGE_DIR` | `./storage_local` | Where files go in local mode |
| `FACE_MATCH_THRESHOLD` | `0.50` | Cosine similarity threshold for "same person" |
| `FACE_MODEL` | `vggface2` | Pretrained weights — `vggface2` or `casia-webface` |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Used to build photo URLs in local mode |
| `CORS_ORIGINS` | local hosts | Comma-separated list |

Mode is logged at startup — look for `mode=local|supabase model=… threshold=…`.

## Switching to Supabase later

1. Sign up at supabase.com (free tier, no credit card). Pick **`ap-south-1` (Mumbai)** region.
2. SQL editor → New query → paste the schema below → run.
3. Storage → New bucket → name `travelseasons-poc` → toggle **Public** on.
4. Settings → API: copy **Project URL** and **`service_role`** key.
5. Settings → Database → Connection string (URI) → use the **Transaction pooler** URL (port 6543).
6. Update `backend/.env`:
   ```ini
   SUPABASE_URL=https://xxxx.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJh…
   SUPABASE_DB_URL=postgresql+psycopg://postgres.xxx:PWD@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
   SUPABASE_BUCKET=travelseasons-poc
   ```
7. Restart `uvicorn`. Startup log must say `mode=supabase`. Zero code changes.

### Schema for Supabase

```sql
create table if not exists "user" (
  id text primary key,
  name text not null,
  email text,
  selfie_path text,
  face_embedding text,
  created_at timestamptz default now(),
  deleted_at timestamptz
);
create table if not exists trip (
  id text primary key,
  name text not null,
  start_date date,
  end_date date,
  created_at timestamptz default now()
);
create table if not exists tripuser (
  trip_id text references trip(id) on delete cascade,
  user_id text references "user"(id) on delete cascade,
  primary key (trip_id, user_id)
);
create table if not exists photo (
  id text primary key,
  trip_id text references trip(id) on delete cascade,
  storage_path text not null,
  width int,
  height int,
  status text default 'pending',
  error text,
  uploaded_at timestamptz default now(),
  processed_at timestamptz
);
create index if not exists ix_photo_trip on photo(trip_id);
create table if not exists photoface (
  id text primary key,
  photo_id text references photo(id) on delete cascade,
  user_id text references "user"(id) on delete set null,
  bbox text not null,
  embedding text not null,
  confidence double precision,
  source text default 'auto',
  removed boolean default false,
  created_at timestamptz default now()
);
create index if not exists ix_photoface_photo on photoface(photo_id);
create index if not exists ix_photoface_user on photoface(user_id);
```

## API summary

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/enrollments` | Multipart: `name`, `email?`, `user_id?`, `selfie` file → creates user + face embedding |
| `GET` | `/users` | List enrolled users |
| `DELETE` | `/users/{id}` | Soft-delete user, blank embedding, mark face tags removed |
| `POST` | `/trips` | JSON: `{name, start_date?, end_date?, member_user_ids[]}` |
| `GET` | `/trips` | List with photo counts + members |
| `POST` | `/trips/{id}/photos` | Multipart `files[]` → schedules per-photo background task |
| `GET` | `/trips/{id}/photos` | `?filter=all\|me\|group`, `X-User-Id` header for `me` |
| `GET` | `/trips/{id}/photos/status` | Processing progress |
| `PATCH` | `/photos/{id}/faces` | `{remove_face_ids[], add[]}` — admin override |
| `DELETE` | `/photos/{id}` | Remove photo + cascade |
| `GET` | `/health` | `{ok, mode, model, threshold}` |

## Smoke test

```powershell
# 1. Enroll a user (face required in selfie)
curl -X POST http://localhost:8000/enrollments `
     -F "name=Alice" -F "selfie=@C:\path\to\alice.jpg"

# 2. Create a trip
curl -X POST http://localhost:8000/trips `
     -H "Content-Type: application/json" `
     -d '{"name":"Bhutan Demo"}'

# 3. Upload trip photos (substitute the trip ID)
curl -X POST http://localhost:8000/trips/TRIP_ID/photos `
     -F "files=@photo1.jpg" -F "files=@photo2.jpg"

# 4. Watch progress
curl http://localhost:8000/trips/TRIP_ID/photos/status

# 5. List Alice's photos
curl -H "X-User-Id: ALICE_USER_ID" `
     "http://localhost:8000/trips/TRIP_ID/photos?filter=me"
```

Or just open `http://localhost:8000/admin/` and do it in the UI.
