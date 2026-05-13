# PoC 1 — AI Daily Recap Video Pipeline · Plan

## Goal

Take one trip-day's raw uploads (photos + clips) + its itinerary, produce one approved 30-second narrated recap video, surfaced via API to the Flutter app. End-to-end demo per the brief's acceptance criteria.

## Scope

| In | Out |
|---|---|
| One day of one trip end-to-end (Singapore Day 3 as the demo case) | Multi-language voiceover |
| Itinerary tables + markdown parser | Face-aware cuts |
| Photo timestamp → itinerary matching | Production music licensing |
| Shotstack rendering | Regional-language captions |
| ElevenLabs voiceover | Mobile TM upload UI (web/REST is fine) |
| Admin review (approve / regenerate / reject) | Bulk recap generation across many days |
| Customer Flutter recap card | |

## External services to sign up for

| Service | What | Free tier | Signup needs |
|---|---|---|---|
| Shotstack | Render JSON timeline → MP4 | ~20 min/month rendering, sandbox watermark | Email |
| ElevenLabs | TTS for voiceover | ~10K chars/month | Email |
| Music | Bundle a CC0 royalty-free track | — | None — I'll grab one from Pixabay/FMA |

## New DB tables (3)

```
trip_day
  id pk, trip_id fk, date, theme, weather, tour_manager,
  voiceover_script text,            -- pulled from itinerary markdown
  filmable_moments jsonb,           -- ranked list [{title, importance}]
  created_at

itinerary_item
  id pk, trip_day_id fk,
  start_time time, end_time time,
  title, description,
  importance int default 5,         -- 1-10, from "filmable moments" list
  created_at

video_render
  id pk, trip_day_id fk,
  version int,                       -- v1, v2, ... per regenerate
  status text,                       -- queued | rendering | pending_review | approved | rejected
  shotstack_render_id text,
  mp4_storage_path text,
  voiceover_storage_path text,
  duration_seconds int,
  admin_notes text,
  created_at, reviewed_at
```

Plus one column on existing `photo`:
```
photo.itinerary_item_id  fk nullable  -- matched by EXIF timestamp
photo.taken_at           timestamptz nullable  -- from EXIF, pulled at upload time
```

## Pipeline flow (one trip-day)

```
[admin uploads itinerary markdown]
        ↓
parse → trip_day + itinerary_items rows
        ↓
[TM uploads photos + clips throughout day]
        ↓
backend: read EXIF taken_at →
         match to itinerary_item (timestamp ∈ [start, end])
         set photo.itinerary_item_id
         (also: face detection per PoC 2)
        ↓
[admin or auto-trigger: POST /trip-days/{id}/generate-recap]
        ↓
backend:
  1. Load itinerary_items (ordered) + photos/clips for the day
  2. Generate voiceover script (use stored one, or template)
  3. ElevenLabs API → TTS → MP3 → store
  4. Build Shotstack timeline JSON:
       - importance ≥ 8 → 3-4 sec hold
       - importance 5-7 → 2-3 sec hold
       - importance < 5 → 1.5-2 sec hold
       - text overlay per high-importance item
       - audio: voiceover track + ducked music
       - end card: "Travel Seasons · Tomorrow [next item]"
  5. POST to Shotstack /render → store shotstack_render_id
  6. video_render row, status=rendering
        ↓
[Shotstack callback hits /webhooks/shotstack]
        ↓
backend:
  - Download MP4 from Shotstack URL
  - Save to Supabase Storage: recap_videos/{trip_day_id}/v{n}.mp4
  - status=pending_review
        ↓
[admin opens /admin/#videos]
        ↓
sees row, plays MP4 inline, clicks Approve / Regenerate / Reject
        ↓
Approve  → status=approved, customer can fetch
Reject   → status=rejected, dead
Regen    → new version v{n+1}, optional param tweaks
        ↓
[customer opens trip day in Flutter]
        ↓
GET /trip-days/{id} returns approved recap URL + itinerary-grouped photos
shows recap card at top of gallery
```

## API endpoints (new)

| Method | Path | Purpose |
|---|---|---|
| `POST /trips/{trip_id}/itinerary` | multipart: `markdown` file | Parse + create trip_day + itinerary_items |
| `GET /trips/{trip_id}/days` | — | List trip_days with item counts |
| `GET /trip-days/{id}` | — | Day details + itinerary items + photos grouped by item + approved recap URL |
| `POST /trip-days/{id}/rematch-photos` | — | Re-run timestamp matching on existing photos |
| `POST /trip-days/{id}/generate-recap` | optional JSON: voice, music | Kick off pipeline → returns video_render id |
| `GET /video-renders/{id}` | — | Status + URL |
| `POST /video-renders/{id}/approve` | — | Mark approved |
| `POST /video-renders/{id}/reject` | — | Mark rejected |
| `POST /webhooks/shotstack` | Shotstack callback | Internal — download MP4, mark pending_review |

Existing `POST /trips/{id}/photos` gets EXIF parsing + itinerary_item assignment added.

## Admin panel additions

New `#videos` section in `admin/index.html`:

- List of pending/recent video_renders across all trip_days
- Each row: thumbnail (1st frame), inline `<video>` player, status pill, Approve/Regen/Reject buttons
- Regenerate opens a modal: pick voice (dropdown from ElevenLabs voices), pick music (dropdown from bundled tracks), optional voiceover override

Itinerary upload form goes into the trip-detail screen (existing `#trip/:id`): "Upload itinerary markdown" button + a list of trip-days that get created.

## Flutter additions

- New screen: `TripDayScreen` (replaces opening straight into gallery)
  - Top: horizontal day selector chip row (Day 1, Day 2, ...)
  - Top of selected day: recap video card (if approved) using `video_player` package
  - Below: photo sections grouped by itinerary item, each section header = activity title + time

- Update `TripGalleryScreen`: tap on a trip now goes to TripDayScreen first; the existing "All / Photos of you / Group" tabs become a filter inside each day

- One new pubspec dep: `video_player: ^2.9.2`

## Implementation order (phased)

**Phase 1 — Itinerary foundation** (~2-3 hours)
1. Add `trip_day` + `itinerary_item` tables (Supabase migration via MCP)
2. Add `photo.itinerary_item_id` + `photo.taken_at` columns
3. Markdown parser for the Singapore sample format
4. EXIF reader in upload pipeline + rematch endpoint
5. `POST /trips/{id}/itinerary` endpoint + admin form

**Phase 2 — Recap pipeline backend** (~3-4 hours)
1. `video_render` table
2. ElevenLabs TTS client wrapper
3. Shotstack timeline builder (helpers + the JSON shape)
4. Shotstack render submit + webhook handler
5. Bundle one CC0 music track in `backend/assets/`
6. `generate-recap` endpoint + status polling endpoints
7. Approve/reject/regenerate endpoints

**Phase 3 — Admin UI** (~1-2 hours)
1. `#videos` section in admin (list + player + actions)
2. Itinerary upload button in trip detail

**Phase 4 — Flutter** (~2-3 hours)
1. Add `video_player` dep
2. New `TripDayScreen` with day selector + recap card
3. Group photos by itinerary_item in the gallery
4. Wire up navigation from trip list → trip days

**Phase 5 — End-to-end test** (~1 hour)
1. Upload Singapore Day 3 markdown
2. Re-run rematch on existing 18 photos (already have EXIF)
3. Trigger generate-recap
4. Watch Shotstack render, hit webhook
5. Approve in admin
6. View in Flutter

**Total estimate: ~10-13 hours of build time.**

## Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Shotstack timeline JSON is complex; first attempts may produce ugly/broken videos | High | Start with a hardcoded simple template (5 cuts, voiceover, music). Iterate on quality after end-to-end works |
| 2 | ElevenLabs free-tier voice may sound generic; brief says "warm Indian female" | Medium | Default to ElevenLabs `Bella` or `Charlotte` voice. Document as a client decision for production |
| 3 | Shotstack render times spike to 90+ sec under load → admin sees stuck "rendering" | Low | Webhook handles async; if missing, poll-fallback every 10 sec for 5 min |
| 4 | Photos without EXIF won't match itinerary | Medium (covered) | "Unsorted" bucket + admin manual drag; we've already injected EXIF on the demo set |
| 5 | Shotstack free tier has watermark | Cosmetic | Acceptable for PoC; documented in deliverable notes |

## What I need from you (after plan approval)

1. **Shotstack API key** (sandbox is fine) — from dashboard after email signup
2. **ElevenLabs API key** — from profile after email signup
3. **Sample video clip** (optional) — a 10-20 sec clip from the Singapore trip, or I'll grab CC0 stock footage from Pexels for the demo

Both keys go in `backend/.env` as `SHOTSTACK_API_KEY` and `ELEVENLABS_API_KEY`. Won't be committed (already gitignored).

## What's NOT in this plan (deferred)

- LLM-based voiceover script generation (we'll use the markdown-provided script for the PoC)
- Multiple voice/music presets in the regenerate flow
- Vertical 9:16 cut for in-app phone view (brief out-of-scope notes only require 16:9)
- AWS Rekognition pivot for PoC 2 — separate work, can happen before or after this

---

When you approve this plan, sign up for Shotstack + ElevenLabs and share keys. I'll start Phase 1 (itinerary foundation) which doesn't need either key — so we can begin while you're signing up.
