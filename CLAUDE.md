# CLAUDE.md — guidance for AI assistants working on this repo

You are working on the **Travel Seasons PoC** repo. Read this file before doing anything substantial. Then read [`README.md`](README.md) for the project overview.

## What this repo is

Three proofs-of-concept for a senior-traveller mobile app, built before the production engagement:

1. **PoC 3 — Travel Games** (✅ done) — Flutter, no backend
2. **PoC 2 — Photo Gallery + Face Tagging** (✅ done) — FastAPI + facenet-pytorch + Supabase
3. **PoC 1 — AI Daily Recap Video** (⏳ not started) — Shotstack + ElevenLabs planned

Owner is non-technical-leaning (uses casual language, not deep into ML/infra terminology). Match that register — be concrete, skip jargon, use small tables for comparisons. Owner is on Windows 11 with PowerShell + cmd.exe.

## Hard constraints (do not violate)

- **No AWS** — owner has no credit card, cannot sign up. So no Rekognition, S3, Lambda, etc.
- **No paid services** — everything must use free tiers (Supabase free, free public APIs, local-running ML)
- **PoC quality, not production** — no real auth, no rate limiting, no observability, no test suites. Owner has explicitly said "we are testing, not shipping to Play Store"
- **DPDP consent flow is SKIPPED** — owner removed it. Do not re-add unless asked
- **Hardcoded user ID via `X-User-Id` header** — no JWT, no OAuth
- **Windows host** — InsightFace 0.7.3 has no Python 3.11 wheels and needs MSVC; we use `facenet-pytorch` instead. If you ever consider switching back, account for this

## Architecture mental model

```
[Flutter app on phone]                [Browser at /admin]
         |                                     |
         |  HTTP (X-User-Id header)            |  HTTP
         v                                     v
                  [FastAPI backend (uvicorn)]
                            |
        +-------------------+-------------------+
        v                                       v
  [SQLModel/SQLAlchemy]                  [Storage abstraction]
        |                                       |
   either: SQLite (local)                  either: local disk
   or:     Supabase Postgres               or:     Supabase Storage
                                                   (auto-detected from .env)

Face engine (facenet-pytorch):
  - MTCNN for detection
  - InceptionResnetV1 (VGGFace2) for 512-dim embeddings
  - Cosine similarity matching, threshold 0.5
  - Linear scan (only ~5 users in PoC, no pgvector)
```

## Folder map (specifics)

| Path | What lives there |
|---|---|
| `app/lib/main.dart` | Flutter entry, theme, MainScaffold (5 bottom-nav tabs) |
| `app/lib/screens/main_scaffold.dart` | Bottom nav: Discover (0), My Trips (1), Documents (2), Games (3), Profile (4) |
| `app/lib/screens/home_screen.dart` | Discover tab UI (mocked content, no backend) |
| `app/lib/screens/games_screen.dart` | Games tab UI |
| `app/lib/games/` | PoC 3 — quiz logic (RestCountries + TheMealDB) |
| `app/lib/photos/` | PoC 2 — selfie enrollment, photo galleries, trip gallery |
| `app/lib/photos/services/api_client.dart` | **All backend HTTP calls.** Base URL hardcoded for Android: `http://192.168.1.11:8000` (owner's LAN IP). Change if running on different network |
| `app/lib/profile/profile_screen.dart` | Profile tab; entry point to Photo galleries |
| `app/android/app/src/main/AndroidManifest.xml` | Has `usesCleartextTraffic="true"` + INTERNET + CAMERA permissions |
| `backend/app/main.py` | FastAPI app, mounts `/admin` static, mounts `/storage` static (local mode only), CORS open for localhost |
| `backend/app/config.py` | Reads `.env`. Mode auto-detects: `supabase` if all 3 Supabase vars set, else `local` |
| `backend/app/models.py` | 5 tables: `user`, `trip`, `tripuser`, `photo`, `photoface`. Embeddings stored as JSON-encoded TEXT |
| `backend/app/face/engine.py` | facenet-pytorch wrapper. **Heavy module — lazy-loads MTCNN + InceptionResnetV1 on first call.** ~120 MB model download |
| `backend/app/face/matcher.py` | `cosine()` + `best_match()`. Threshold from `.env` (default 0.5) |
| `backend/app/tasks/process_photos.py` | Background pipeline: detect faces → match each → write `photoface` rows |
| `backend/app/tasks/rematch.py` | Auto-rematches unmatched faces when a new user enrolls |
| `backend/app/storage/local.py` | Filesystem storage (PoC default) |
| `backend/app/storage/supabase.py` | Supabase Storage client (production-mode) |
| `admin/index.html` + `app.js` | Vanilla JS admin panel — Users / Trips / Trip detail with override flow |

## Database schema (current)

```
user      (id pk, name, email?, selfie_path?, face_embedding (JSON TEXT, len=512), created_at, deleted_at?)
trip      (id pk, name, start_date?, end_date?, created_at)
tripuser  (trip_id fk, user_id fk) — composite pk; just a label
photo     (id pk, trip_id fk, storage_path, width?, height?, status [pending|processing|done|failed], error?, uploaded_at, processed_at?)
photoface (id pk, photo_id fk, user_id? fk, bbox (JSON), embedding (JSON), confidence?, source [auto|manual], removed bool)
```

Same SQL works on SQLite + Postgres. No `pgvector` (linear scan is fine at PoC scale).

**To inspect tables when MCP is connected:** use `mcp__supabase__list_tables` and `mcp__supabase__execute_sql`.

## Supabase MCP setup

The repo's `.mcp.json` lets Claude Code call Supabase directly (apply migrations, query DB). Required steps:

1. Owner generates a Personal Access Token from `supabase.com/dashboard/account/tokens` (one-time).
2. Token + project ref live in `.mcp.json` (gitignored).
3. **Globally installed** via `npm i -g @supabase/mcp-server-supabase @modelcontextprotocol/sdk zod` (the npx fetch is broken — peer deps don't get installed; we use the global binary instead).
4. `.mcp.json` points at `mcp-server-supabase.cmd` (the global binary).
5. After config changes, Claude Code must be restarted to pick up new MCP servers.

If MCP errors with `-32000 Connection closed`, run the binary directly to see the real error:
```cmd
set SUPABASE_ACCESS_TOKEN=sbp_...
mcp-server-supabase --project-ref=axvwidbrlugecjekpehd --read-only
```
Most likely it's a missing peer dep — `npm i -g <missing-pkg>` to fix.

## Environment / mode behaviour

```
backend/.env  (gitignored)
├─ SUPABASE_URL=...               → mode flips to "supabase" if all three set
├─ SUPABASE_SERVICE_ROLE_KEY=...
├─ SUPABASE_DB_URL=...
├─ SUPABASE_BUCKET=travelseasons-poc
├─ LOCAL_DB_PATH=./data/poc.db    → SQLite path in local mode
├─ LOCAL_STORAGE_DIR=./storage_local
├─ FACE_MATCH_THRESHOLD=0.50      → cosine sim cutoff for "same person"
├─ FACE_MODEL=vggface2            → facenet-pytorch pretrained weights ('vggface2' or 'casia-webface')
├─ PUBLIC_BASE_URL=http://localhost:8000
└─ CORS_ORIGINS=http://localhost:8000,...
```

## Common tasks

**Run the backend:**
```cmd
cd c:\travelseason_POC\backend
.\.venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Run the Flutter app on Android:**
- Open `c:\travelseason_POC\app` in Android Studio → press play
- Or `cd app && flutter run`

**Apply a schema change to Supabase:** use `mcp__supabase__apply_migration` (DDL) or `mcp__supabase__execute_sql` (DML).

**Re-tag all unmatched faces (after threshold change):** `POST http://localhost:8000/admin/rematch-all`

**Check what mode the backend is in:** `curl http://localhost:8000/health`

## Things to be careful about

- **Don't auto-add an InsightFace dep** without first checking Python version + MSVC availability. We deliberately use facenet-pytorch.
- **Don't enable RLS on Supabase tables** without adding policies — would block backend access.
- **Don't paste Supabase credentials in chat output.** They live in `.env` and `.mcp.json` (both gitignored).
- **Don't add tests "for completeness"** — the brief says PoC quality, no test suites.
- **Don't auto-add image classification (Wildlife/Landscapes/Sunset filters)** — those are out of PoC 2 scope.
- **The `Add Sage` button on the Discover screen is a placeholder.** Not wired up.
- **The PoC 1 AI video card on the Kenya screenshot is decorative.** That's PoC 1, separate work.

## Workflow conventions

- Auto mode is usually on — execute first, ask only when blocked.
- Owner uses casual phrasing ("u" "ok" "huh"). Match the energy in concise replies; don't over-elaborate.
- Owner's environment: Windows 11, PowerShell + cmd.exe, Python 3.11, Flutter 3.38, Node 22.
- Owner's LAN IP at time of writing: `192.168.1.11`. May change between sessions — verify with `ipconfig`.
- Owner's Supabase project ref: `axvwidbrlugecjekpehd`, region `ap-northeast-1` (Tokyo).
