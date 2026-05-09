# Testing guide — Face Recognition PoC (PoC 2)

Step-by-step walkthrough to evaluate the face-tagging pipeline end-to-end. Use this if you're the reviewer or someone new picking up the project.

---

## Prereqs

- Backend running (`uvicorn` on port 8000)
- Admin panel reachable at `http://localhost:8000/admin/`
- (Optional) Flutter app running on a phone or emulator
- 5 face photos of different people (any portraits — Google works fine for fakes)
- 10–20 group / candid photos containing those same people (mix of solo and group shots)

If anything above isn't ready, see the run instructions in [`README.md`](README.md), [`backend/README.md`](backend/README.md), and [`app/README.md`](app/README.md).

---

## Test 1 — Backend health (30 seconds)

```cmd
curl http://localhost:8000/health
```

**Expected:** JSON with `mode`, `model`, `threshold`. Example:
```json
{"ok":true,"mode":"local","model":"vggface2","threshold":0.5}
```

If `mode` says `local` → using SQLite + local disk.
If `mode` says `supabase` → using hosted Postgres + Supabase Storage.

**If it fails:** backend isn't running. Start it per `backend/README.md`.

---

## Test 2 — Enroll 5 users via admin (5 minutes)

1. Open `http://localhost:8000/admin/` in Chrome
2. Click the **Users** tab in the top nav
3. For each of your 5 face photos:
   - Type a name (e.g. `Alice`, `Bob`, ...)
   - Click **Choose selfie…** → pick the photo
   - Click **Enroll**
4. After all 5: the grid should show 5 user cards with thumbnails

### What this proves

- Backend can detect a face in an uploaded image (face-detection works)
- Backend can extract a 512-dim embedding (face-recognition works)
- Storage abstraction (local disk OR Supabase) is writing the selfie files
- Database is persisting the user + embedding

### Failure modes

| Symptom | Cause |
|---|---|
| Red toast "No face detected — try a clearer photo" | The selfie has no clearly visible face. Use a tight portrait |
| Red toast says HTTP 500 | Check the uvicorn console — likely a Supabase connection issue (storage bucket not created? RLS blocking?) |
| Card appears but thumbnail is blank | Storage write succeeded but URL is wrong — likely Supabase bucket not Public, or local-storage mount wrong |

---

## Test 3 — Create a trip + bulk upload photos (5 minutes)

1. Click the **Trips** tab
2. Form at top: name `Bhutan Demo`, leave dates blank, **tick all 5 users** as members
3. Click **Create trip**
4. Click the trip row in the list → trip detail page opens
5. Drag-drop your 10–20 trip photos onto the upload zone (or click and pick)
6. **Watch the progress bar** — it polls `/photos/status` every 2 s
7. Once it reaches 100%:
   - Photo grid shows each uploaded photo
   - Each photo has chips overlaid showing detected/matched faces
   - Format: `Alice · 87%` (green chip) for matched, `?` (yellow chip) for unmatched

### What this proves

- Bulk upload works (multipart, chunked at 10 files)
- Background processing pipeline runs (FastAPI BackgroundTasks)
- Face detection runs on group photos (multiple faces per image)
- Cosine similarity matching finds correct users
- Status endpoint returns accurate progress

### What to verify

- **At least one solo photo of Alice → tagged Alice with high confidence (~80%+)**
- **At least one group photo with 2+ enrolled people → multiple chips**
- **Some photos have no detected faces (scenery shots) → empty face row, that's fine**

---

## Test 4 — Inspect tag accuracy (5 minutes)

1. Scan the grid for **false positives** (wrong person tagged) — count and note
2. Scan for **false negatives** (person clearly in photo but no chip) — count and note
3. Click any photo → modal opens with detected faces and confidence scores
4. Note the confidence distribution: hand-picked single-face photos should be 0.7–0.95; angle/lit-poor photos drop to 0.5–0.7

### Tuning the threshold

Default is **0.5 cosine similarity**. To experiment:

1. Stop backend (Ctrl+C)
2. Edit `backend/.env` → change `FACE_MATCH_THRESHOLD=0.45` (more permissive) or `0.6` (stricter)
3. Restart backend
4. In admin, hit `POST /admin/rematch-all` (e.g. via browser console or `curl`):
   ```cmd
   curl -X POST http://localhost:8000/admin/rematch-all
   ```
5. Refresh the trip detail page — tags should update

### Acceptance criterion (from brief)

> "Confidence threshold tunable; reported on false positives and false negatives"

You're done with this test when you can articulate the false-positive / false-negative count for your sample at the default threshold.

---

## Test 5 — Override a wrong tag (2 minutes)

1. Pick a photo where you spot a wrong tag (e.g. `Alice` shown but it's actually Bob)
2. Click the photo → modal opens
3. In the **Detected faces** list, find the wrong row → click **Remove**
4. The face row disappears; modal refreshes
5. Click the **Add tag** dropdown → pick the correct user (Bob) → click **Add tag**
6. New row appears with `manual` source label
7. Close modal — grid updates immediately to reflect the override

### What this proves

- Manual override flow works (`PATCH /photos/{id}/faces`)
- Override marks `source='manual'` and `removed=true` so it's distinguishable from auto-matches
- Customer's "Photos of you" filter respects overrides (removed=true → not shown for that user)

### Acceptance criterion (from brief)

> "One admin override flow works (untag a wrong match)"

---

## Test 6 — Customer "Photos of you" filter (5 minutes)

### Via admin (quickest)

1. In trip detail, find the filter dropdown above the photo grid
2. Change to **Photos of one user…** → second dropdown appears → pick `Alice`
3. Grid filters to only photos where Alice was matched

### Via Flutter app (real-world flow)

1. Open the Flutter app on your phone or emulator
2. Bottom nav → **Profile** (last tab)
3. Tap **Photo galleries**
4. First time: prompts for selfie → upload a selfie of one of your 5 enrolled people (e.g. take Alice's photo on the phone, or upload from gallery)
5. After enrolling, you see the trip list → tap **Bhutan Demo**
6. Three tabs: **All** / **Photos of you** / **Group**
7. **Photos of you** should show only the photos containing the face you uploaded as selfie

### What this proves

- Filter logic works for both admin and customer views
- "Photos of you" is correctly scoped per-trip (only that trip's photos)
- Auto-rematch works: even photos uploaded before you enrolled are now tagged with you

### Edge case to test

- After Flutter enrollment, **"Photos of you" shows your photos immediately** — that's the auto-rematch feature. If it shows nothing, the rematch isn't running (check `tasks/rematch.py` logic)

---

## Test 7 — Delete a user (DPDP-style) (1 minute)

1. Admin → **Users** tab
2. Click **Delete** on Alice's card
3. Confirm prompt
4. Alice disappears from the user list
5. Go back to the trip detail → photos previously tagged with Alice show **no Alice chips**

### What this proves

- DELETE endpoint cascades correctly:
  - User row soft-deleted (`deleted_at` set, `face_embedding` nulled)
  - Selfie file deleted from storage
  - All `photo_faces` rows for Alice marked `removed=true`
- Customer's "Photos of you" for Alice would now return empty
- Photos themselves are NOT deleted (they belong to the trip / admin)

### Acceptance criterion (from brief)

> "DPDP-aligned: explicit consent shown before face enrollment, deletion endpoint exists"

(Consent UI is intentionally skipped for the PoC, but deletion endpoint works.)

---

## Test 8 — Verify data in Supabase (only if running mode=supabase) (2 minutes)

If your backend is in `mode=supabase`, you can inspect the data directly:

### Via Supabase dashboard

- Sidebar → **Table editor** → click `user`, `trip`, `photo`, `photoface` to browse rows
- Sidebar → **Storage** → click `travelseasons-poc` bucket → see `selfies/` and `trip_photos/` folders

### Via SQL editor

```sql
-- count things
SELECT
  (SELECT COUNT(*) FROM "user" WHERE deleted_at IS NULL) AS users,
  (SELECT COUNT(*) FROM trip) AS trips,
  (SELECT COUNT(*) FROM photo WHERE status='done') AS photos_done,
  (SELECT COUNT(*) FROM photoface WHERE removed=false AND user_id IS NOT NULL) AS auto_tags,
  (SELECT COUNT(*) FROM photoface WHERE removed=false AND source='manual') AS manual_tags;

-- which users have how many tagged photos
SELECT u.name, COUNT(pf.id) AS photo_count
FROM "user" u
LEFT JOIN photoface pf ON pf.user_id = u.id AND pf.removed = false
GROUP BY u.name
ORDER BY photo_count DESC;
```

### Via Claude Code (Supabase MCP enabled)

If you have the Supabase MCP server connected (see `CLAUDE.md`):
```
Use the mcp__supabase__execute_sql tool to run any SQL above.
```

---

## Acceptance scorecard

This is the brief's acceptance criteria — tick as you go:

- [ ] 5 test users enrolled with selfies of different ages and lighting conditions (Test 2)
- [ ] 100 trip photos uploaded and processed (Test 3 — scale up)
- [ ] Each test user sees a correctly filtered "photos of me" view (Test 6)
- [ ] Confidence threshold tunable; reported on false positives and false negatives (Test 4)
- [ ] One admin override flow works (untag a wrong match) (Test 5)
- [ ] DPDP-aligned: deletion endpoint exists (Test 7) *(consent UI skipped per owner's call)*

---

## Troubleshooting cheatsheet

| Symptom | First place to look |
|---|---|
| `mode=local` when you wanted Supabase | `backend/.env` — all 3 SUPABASE_ vars must be set |
| Photos upload but never reach `done` status | uvicorn console — face engine probably crashed mid-process. Check stack trace |
| Selfie thumbnails show as broken images | If Supabase: bucket is not Public. If local: `/storage` mount is wrong |
| 0 matched faces despite uploaded photos | Threshold too strict, OR users were enrolled AFTER upload but the rematch didn't fire (bug) |
| First request takes 10+ seconds | Normal — face models are loading. Pre-warm with `python -c "from app.face.engine import get_engine; get_engine()"` |
| Flutter app shows "Network error" | Phone can't reach `192.168.1.11:8000`. Check Wi-Fi + LAN IP — see `app/README.md` |

---

## Performance reference (current setup)

- Face detection: ~80 ms / face on CPU (MTCNN)
- Face embedding: ~120 ms / face on CPU (InceptionResnetV1, VGGFace2)
- 100 photos × 3 faces avg = ~60 seconds total processing time
- Memory: ~1.5 GB peak during inference
- Cold start: ~10 s for first request (model load), <500 ms thereafter

---

## What's NOT covered by this PoC (out of scope per brief)

- Production-grade upload UI
- Bulk download or WhatsApp share
- 90-day auto-delete
- Mobile upload from TM device
- Auto-rotate, "best of" sorter
- Image classification (Wildlife / Landscapes / Sunset filters from the screenshots) — that's a different model
- AI Daily Recap Video card on the gallery — that's PoC 1, not built yet

---

## See also

- [`README.md`](README.md) — top-level overview
- [`backend/README.md`](backend/README.md) — backend internals + Supabase migration SQL
- [`app/README.md`](app/README.md) — Flutter run + APK build
- [`admin/README.md`](admin/README.md) — admin panel
- [`CLAUDE.md`](CLAUDE.md) — context for AI assistants
