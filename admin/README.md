# Travel Seasons — Admin panel (PoC 2)

A single-page vanilla HTML/JS admin tool for the Photo Gallery PoC. Served by the FastAPI backend at `/admin`.

> Stack: vanilla HTML5 + ES modules-style JS (no bundler, no framework) + plain CSS

## What it does

Three sections, switched by URL hash:

| URL | Screen | Purpose |
|---|---|---|
| `/admin/#users` | Enrolled users | Add / list / delete users with face selfies |
| `/admin/#trips` | Trips | Create trips, list them, click to drill in |
| `/admin/#trip/{trip_id}` | Trip detail | Bulk-upload photos, watch processing progress, review face tags, override mistakes |

## Files

```
admin\
├── index.html       # one page, three sections (templates), hash router
├── app.js           # all logic (~400 lines, vanilla fetch + DOM)
├── style.css        # brand colours match the Flutter app
└── assets\          # placeholder for icons/logos (currently empty)
```

## How to run

The admin panel is served by the FastAPI backend. **Just start the backend and open the URL.**

1. Start backend (see [`../backend/README.md`](../backend/README.md)):
   ```cmd
   cd ..\backend
   .\.venv\Scripts\activate.bat
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. Open in any browser:
   ```
   http://localhost:8000/admin/
   ```

After editing any file in `admin/`, just **F5 / refresh** the browser — FastAPI re-serves the static files; no backend restart needed.

## Typical demo flow

1. Open `http://localhost:8000/admin/`
2. Top-right pill should say `local` or `supabase` — that's the backend mode
3. Go to **Users** tab → enroll 5 test users with selfies (clear face photos work best)
4. Go to **Trips** tab → create a trip, tick the 5 users as members
5. Click the trip row → drag-drop ~10–20 photos containing those people
6. Watch the progress bar fill (~300 ms per photo)
7. Once `done` for all photos, the grid shows each photo with face-tag chips overlaid
8. Click any photo → modal opens → see all detected faces, click **Remove** on a wrong tag, click **Add tag** + pick a user from dropdown for a missed face

## How it talks to the backend

All API calls are simple `fetch()` calls in `app.js`. Same-origin (the page is served from the same FastAPI host), so no CORS config needed for the admin path.

| Action | Endpoint |
|---|---|
| List users | `GET /users` |
| Enroll user | `POST /enrollments` (multipart) |
| Delete user | `DELETE /users/{id}` |
| List trips | `GET /trips` |
| Create trip | `POST /trips` |
| Upload photos | `POST /trips/{id}/photos` (multipart, chunked at 10 files) |
| Poll progress | `GET /trips/{id}/photos/status` (every 2 s while pending/processing) |
| List photos | `GET /trips/{id}/photos?filter={all,me,group}` |
| Override face tags | `PATCH /photos/{id}/faces` |

For "Photos of one user" filter, the panel sends an `X-User-Id: {selected_user_id}` header.

## Decisions worth knowing

- **Plain HTML/JS, no React/Vue** — brief explicitly says "rough is OK"; saves a bundler/build step
- **Hash router** (`location.hash`) — simplest possible client-side routing, no library
- **No drag-drop polish** — drop zone works, but visual feedback is minimal
- **Chunks uploads in batches of 10 files** — to stay under default request size limits
- **Polls every 2 s while photos process** — no WebSockets

## See also

- [`../README.md`](../README.md) — project overview
- [`../backend/README.md`](../backend/README.md) — backend API spec
- [`../CLAUDE.md`](../CLAUDE.md) — context for AI assistants
