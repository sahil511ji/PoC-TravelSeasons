# Travel Seasons — PoC Repository

Three proofs-of-concept for the Travel Seasons mobile app (a senior-traveller, 60+, tour operator).
Each PoC validates one risky feature before the production build.

> Owner: Nitin Gupta · Ekam Apps
> Client: Travel Seasons Pvt Ltd
> Phase: Pre-build
> Brief: [`TravelSeasons - PoC Brief for Developer.docx.md`](TravelSeasons%20-%20PoC%20Brief%20for%20Developer.docx.md)

---

## Status at a glance

| PoC | What it tests | Status |
|---|---|---|
| **PoC 3 — Travel Games** | Two travel-themed quizzes (Guess the Flag, Cuisine Quiz) using free public APIs, with mocked loyalty wallet integration | ✅ **Done** — runs entirely in Flutter, no backend needed |
| **PoC 2 — Photo Gallery + Face Tagging** | Auto face-tagging on bulk-uploaded trip photos, "photos of me" filtered view, admin override flow | ✅ **Done** — FastAPI backend + admin panel + Flutter screens, runs on Supabase or local SQLite |
| **PoC 1 — AI Daily Recap Video** | TM uploads raw clips → AI cuts a 30-sec narrated recap → admin approves → customer sees it | ⏳ **Not started** |

---

## Folder layout

```
c:\travelseason_POC\
├── README.md                    # this file
├── CLAUDE.md                    # context for AI assistants working on this repo
├── .mcp.json                    # Supabase MCP config (gitignored — has token)
├── .gitignore                   # secrets + build artefacts
│
├── TravelSeasons - PoC Brief for Developer.docx.md   # the original brief
│
├── app\                         # Flutter app (customer-facing, mobile + web)
│   ├── lib\
│   │   ├── main.dart            # entry point, theme, MainScaffold
│   │   ├── theme\               # design tokens (colors, fonts)
│   │   ├── screens\             # Discover, Games, Profile, etc. (bottom nav)
│   │   ├── games\               # PoC 3 — quiz logic + screens
│   │   ├── photos\              # PoC 2 — selfie enrollment + gallery
│   │   └── profile\             # Profile screen (entry to Photo galleries)
│   ├── android\                 # Android build (AndroidManifest, gradle)
│   ├── ios\                     # iOS build
│   ├── web\                     # Flutter web (used during dev)
│   ├── pubspec.yaml             # Flutter deps
│   └── README.md                # Flutter-specific run + build instructions
│
├── backend\                     # PoC 2 — FastAPI + face recognition
│   ├── app\
│   │   ├── main.py              # FastAPI app, mounts /admin and /storage
│   │   ├── config.py            # env vars, mode auto-detection
│   │   ├── db.py                # SQLite or Postgres engine
│   │   ├── models.py            # SQLModel tables (User, Trip, Photo, etc.)
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── storage\             # storage abstraction (LocalDisk + Supabase)
│   │   ├── face\                # face engine (facenet-pytorch) + matcher
│   │   ├── routers\             # API endpoints (enrollments, users, trips, photos)
│   │   └── tasks\               # background processing (face matching, rematch)
│   ├── data\                    # gitignored — SQLite DB lives here in local mode
│   ├── storage_local\           # gitignored — files in local mode
│   ├── .venv\                   # gitignored — Python virtualenv
│   ├── .env                     # gitignored — secrets (Supabase URL, keys)
│   ├── .env.example             # template
│   ├── requirements.txt         # Python deps (pinned)
│   └── README.md                # backend-specific docs
│
└── admin\                       # PoC 2 — admin panel (vanilla HTML/JS)
    ├── index.html               # single-page app (hash-routed)
    ├── app.js                   # all logic, ~400 lines
    ├── style.css
    └── README.md                # admin-specific notes
```

---

## Tech stack summary

| Concern | Choice | Why |
|---|---|---|
| **Customer app (mobile + web)** | Flutter 3.38 (Dart 3.10) | Cross-platform, single codebase |
| **Customer auth (PoC)** | Hardcoded `X-User-Id` header | No real auth — PoC quality |
| **Backend** | FastAPI (Python 3.11) | Mature ecosystem for ML + APIs |
| **Face recognition** | `facenet-pytorch` (MTCNN + InceptionResnetV1, VGGFace2 weights, 512-dim L2-normalised embeddings) | Free, no AWS, prebuilt Windows wheels |
| **Database** | Postgres (Supabase) — SQLite fallback for local dev | Same SQLModel code path for both |
| **File storage** | Supabase Storage — local disk fallback for local dev | DPDP-friendly when in Mumbai region |
| **Admin UI** | Plain HTML/JS, served by FastAPI at `/admin` | "Rough is OK" per the brief; zero build step |
| **Game APIs (PoC 3)** | RestCountries + FlagCDN + TheMealDB (all free, no keys) | Per brief recommendations |
| **AI MCP server** | Supabase MCP (`@supabase/mcp-server-supabase`, installed globally) | Lets Claude Code apply schema migrations and query DB directly |

---

## How to run everything end-to-end

### Prereqs (one-time per machine)

- **Python 3.11** — `py -3.11 --version`
- **Flutter SDK** — `flutter --version` (3.10+)
- **Node.js 18+** — `node --version` (only needed for the Supabase MCP server)
- **Android Studio** with an emulator or a real Android device with USB debugging enabled
- **Chrome** (for admin panel + Flutter web testing)

### 1. Backend (terminal 1)

```cmd
cd c:\travelseason_POC\backend
py -3.11 -m venv .venv                    :: first time only
.\.venv\Scripts\activate.bat
pip install -r requirements.txt           :: first time only
copy .env.example .env                    :: first time only
python -c "from app.face.engine import get_engine; get_engine()"   :: warm-load model (~120 MB download, first time only)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Verify:** open `http://localhost:8000/health` — should return JSON with `mode`, `model`, `threshold`.

### 2. Admin panel (Chrome)

Just open: `http://localhost:8000/admin/`

The admin panel auto-loads from FastAPI's static mount.

### 3. Flutter app (terminal 2 OR Android Studio)

**Option A — Android Studio:** Open `c:\travelseason_POC\app` as project → pick device from dropdown → press play (▶).

**Option B — Command line:**
```cmd
cd c:\travelseason_POC\app
flutter pub get                           :: first time only
flutter run                               :: picks up connected device
```

For real Android device testing, the backend URL is hardcoded to `http://192.168.1.11:8000` in `lib/photos/services/api_client.dart` — change it if your laptop's LAN IP differs (`ipconfig` to check).

See [`app/README.md`](app/README.md) for full Flutter run/build details.

---

## Building an APK

```cmd
cd c:\travelseason_POC\app
flutter build apk --release
```

Output: `app\build\app\outputs\flutter-apk\app-release.apk` (~25 MB).

For a smaller build split by ABI (recommended): `flutter build apk --split-per-abi`.

See [`app/README.md`](app/README.md) for signed builds, Play Store packaging, and bundle (`.aab`) options.

---

## Supabase integration (PoC 2 only)

PoC 2 supports two modes, auto-detected from `.env`:

| Mode | When | Database | Storage |
|---|---|---|---|
| **`local`** | Supabase env vars empty | SQLite at `backend/data/poc.db` | Local disk under `backend/storage_local/` |
| **`supabase`** | All Supabase env vars set | Hosted Postgres | Supabase Storage bucket `travelseasons-poc` |

Mode is logged at uvicorn startup: `starting backend mode=local|supabase ...`

### Switching to Supabase

1. Create a free Supabase project (no credit card required).
2. Pick **`ap-south-1` (Mumbai)** region for DPDP — though for this PoC we used `ap-northeast-1`.
3. SQL Editor → paste schema block from `backend/README.md` → Run.
4. Storage → New bucket `travelseasons-poc` → toggle Public ON.
5. Settings → API → copy Project URL + service_role key.
6. Settings → Database → copy Transaction-pooler URI.
7. Fill `backend/.env`:
   ```
   SUPABASE_URL=https://xxxx.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJh...
   SUPABASE_DB_URL=postgresql://postgres.xxx:PWD@aws-0-...pooler.supabase.com:6543/postgres
   SUPABASE_BUCKET=travelseasons-poc
   ```
8. Restart uvicorn.

### Supabase MCP (for AI assistants)

The repo's `.mcp.json` configures Claude Code to talk to your Supabase project directly (apply migrations, query DB). Requires:
- A Personal Access Token from `supabase.com/dashboard/account/tokens`
- Globally installed MCP server: `npm i -g @supabase/mcp-server-supabase @modelcontextprotocol/sdk zod`
- See [`CLAUDE.md`](CLAUDE.md) for details.

---

## Decisions worth knowing

| Decision | Why |
|---|---|
| **No DPDP consent screen** | User explicitly skipped for the PoC ("we are testing, not shipping to Play Store") |
| **No real auth** | Hardcoded `X-User-Id` header — PoC quality |
| **Trip membership not enforced** | "Photos of you" filter is purely face-based; you don't need to be a trip member to see your photos in it. Admin sets membership only as a label |
| **`facenet-pytorch` over InsightFace** | InsightFace 0.7.3 has no Python 3.11 Windows wheels and would need MSVC build tools. facenet-pytorch is equivalent and just installs |
| **Plain HTML admin (not Flutter Web)** | "Rough is OK" per brief; faster to ship a few hundred lines of vanilla JS |
| **Embeddings as TEXT JSON** | Same code works on SQLite and Postgres without `pgvector`. Linear scan over 5 PoC users is fine |
| **Auto-rematch on enrollment** | New users automatically tag any photos already uploaded that contain their face — no admin re-upload needed |

---

## Known limitations / known-OK trade-offs

- **No Row-Level Security on Supabase tables.** Backend uses service_role key which bypasses RLS anyway. Production must enable RLS + policies.
- **InceptionResnetV1 (VGGFace2) backbone.** ~99.6% on LFW. For 5-user PoC: invisible difference vs InsightFace. For 10K-user production: would re-evaluate.
- **Cold-start: first request takes ~10s** while face models load into RAM. The `python -c "from app.face.engine import get_engine; get_engine()"` step in setup pre-warms.
- **~1.5 GB peak RAM** during inference (PyTorch + model). For lower memory, swap to `face_recognition` (dlib) — ~400 MB peak, 128-dim embeddings.
- **Android cleartext HTTP** allowed via `usesCleartextTraffic="true"` (PoC only — production needs HTTPS).

---

## Useful URLs (when running)

| What | URL |
|---|---|
| Backend health | http://localhost:8000/health |
| Admin panel | http://localhost:8000/admin/ |
| FastAPI docs (Swagger) | http://localhost:8000/docs |
| Static storage (local mode) | http://localhost:8000/storage/{key} |

---

## What's next

- **PoC 1 — AI Daily Recap Video** (Shotstack + ElevenLabs). Not started.
- **Production migration plan** for PoC 2: enable RLS + add policies; replace `X-User-Id` with Supabase Auth JWT; move face inference to a dedicated worker; consider switching to AWS Rekognition for managed scaling.

---

## See also

- [`CLAUDE.md`](CLAUDE.md) — context for AI assistants working on this code
- [`backend/README.md`](backend/README.md) — backend deep-dive (API spec, face engine, Supabase migration SQL)
- [`app/README.md`](app/README.md) — Flutter app run/build guide
- [`admin/README.md`](admin/README.md) — admin panel notes
- [`TravelSeasons - PoC Brief for Developer.docx.md`](TravelSeasons%20-%20PoC%20Brief%20for%20Developer.docx.md) — the original PoC brief
