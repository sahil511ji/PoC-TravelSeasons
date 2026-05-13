# PoC 2 → AWS Rekognition migration plan (v3 — final)

> Two rounds of parallel-agent review folded in (~55 findings total). Critical/high fixes annotated **🛠**.

---

## Table of contents

0. [Pre-flight (do these first)](#0-pre-flight)
1. [Goal & constraints](#1-goal--constraints)
2. [AWS resources & limits](#2-aws-resources--limits)
3. [Live DB snapshot (current state)](#3-live-db-snapshot)
4. [API mapping](#4-api-mapping)
5. [Schema migration](#5-schema-migration)
6. [Config changes](#6-config-changes)
7. [Code changes file-by-file](#7-code-changes-file-by-file)
8. [Edge cases catalog](#8-edge-cases-catalog)
9. [Migration script](#9-migration-script)
10. [Verification & smoke test](#10-verification--smoke-test)
11. [Logging contract](#11-logging-contract)
12. [Rollback (honest)](#12-rollback-honest)
13. [Execution order on the day](#13-execution-order-on-the-day)
14. [Open questions / decisions to lock](#14-open-questions--decisions-to-lock)
15. [Effort estimate](#15-effort-estimate)

---

## 0. Pre-flight

🛠 **Must happen before any code change:**

1. **Rotate the leaked AWS key.** The key pasted in chat is compromised. IAM Console → Users → deactivate `AKIA4WZLSZLHW6GERVWY` → create new access key → paste into `backend/.env` only (never chat).
2. **Get the account ID.** `aws sts get-caller-identity --query Account --output text` → paste into IAM policy below replacing the wildcard.
3. **Set a $5/mo billing budget** in AWS Console → Billing → Budgets, with email alert at 80%. (PoC volume is $0.30 — anything above $1 means a bug.)
4. **Update CLAUDE.md now** (not after migration). If this session dies mid-run, the next Claude session must read the new constraint or it'll panic. Replace the "No AWS" hard-constraint with:
   > AWS allowed for face recognition only (PoC 2 uses Rekognition `ap-south-1` collection `travelseasons-poc`). Free-tier covers PoC volume. No S3, no Lambda, no other AWS services without discussion.

---

## 1. Goal & constraints

Replace `facenet-pytorch` (MTCNN + InceptionResnetV1) with **AWS Rekognition** for PoC 2 face engine. Keep DB / storage / admin UI / Flutter app working.

Constraints:
- **Backwards-compatible schema** (additive only; nullable legacy columns kept for 1 commit cycle for partial rollback).
- **PoC quality** — surface AWS errors in `photo.error`, don't add retry/circuit-breaker overkill.
- **Region: `ap-south-1`** (Mumbai). Full Face Collection feature GA.
- **One collection per backend instance** — `travelseasons-poc`.
- 🛠 **Supabase mode only.** Local mode (SQLite + local disk) is not supported on the new face engine. Startup will refuse to boot if `settings.mode == 'local'` AND `AWS_ACCESS_KEY_ID` is empty.

---

## 2. AWS resources & limits

### Verified limits

| Limit | Value |
|---|---|
| Inline image size (`Bytes=...`) | **5 MB** (15 MB only via S3) |
| Inline image format | JPEG or PNG only |
| `MaxFaces` for `DetectFaces`/`IndexFaces` | default 10, max 100 |
| Face min size for search | ~40×40 px (we'll use 80 px to be safe) |
| Default API TPS (new accounts) | ~5–10 TPS; boto3 adaptive retry handles bursts |
| `ExternalImageId` charset | `[a-zA-Z0-9_.\-:]+` (max 255) — colon allowed for `unmatched:<uuid>` |
| `BoundingBox` values | `Left, Top, Width, Height` as 0-1 floats; **can be negative or >1** — clamp to `[0,1]` |
| `UnindexedFaces[].Reasons` | `LOW_CONFIDENCE`, `LOW_BRIGHTNESS`, `LOW_SHARPNESS`, `LOW_FACE_QUALITY`, `EXCEEDS_MAX_FACES`, `SMALL_BOUNDING_BOX` |

### Pricing (ap-south-1)

| Item | Cost |
|---|---|
| `IndexFaces`, `SearchFacesByImage`, `DetectFaces`, etc. | $0.001 per face / image (first 1M) |
| Face storage in collection | **$0.001 per face per month** |
| AWS Free Tier (new account, 12 months) | 5,000 IndexFaces + 1,000 stored faces / mo — covers whole PoC |

PoC total estimate: **~$0.30**, fully under Free Tier.

### IAM policy — explicit account ID, two statements

🛠 Reviewer noted `ListCollections` is account-level (wildcard required), but resource-scoped actions go on the collection ARN. Split into 2 statements.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListAccountLevel",
      "Effect": "Allow",
      "Action": ["rekognition:ListCollections"],
      "Resource": "*"
    },
    {
      "Sid": "CollectionScoped",
      "Effect": "Allow",
      "Action": [
        "rekognition:CreateCollection",
        "rekognition:DeleteCollection",
        "rekognition:DescribeCollection",
        "rekognition:IndexFaces",
        "rekognition:SearchFacesByImage",
        "rekognition:SearchFaces",
        "rekognition:DetectFaces",
        "rekognition:DeleteFaces",
        "rekognition:ListFaces"
      ],
      "Resource": "arn:aws:rekognition:ap-south-1:<ACCOUNT_ID>:collection/travelseasons-poc"
    }
  ]
}
```

Replace `<ACCOUNT_ID>` with the 12-digit account ID from step 0.2.

---

## 3. Live DB snapshot

(Captured during review; reference for migration sizing.)

| Table | Rows | Notes |
|---|---|---|
| `user` (deleted_at IS NULL) | **3** — sahil, jimmy, jk; all have selfie + facenet embedding |
| `photo` (status=done) | **22** — all have width/height populated |
| `photoface` | **56** — 100% `source='auto'`, 0 `manual` |

Implication for migration: no manual-tag preservation needed in the current snapshot. Phase C of the script becomes a no-op but **must still be implemented** for any future re-run where manual tags may exist.

---

## 4. API mapping

| Use | Call | Notes |
|---|---|---|
| **Enrol selfie** | (1) `DetectFaces` → reject if count ≠ 1. (2) `IndexFaces(CollectionId, Image={Bytes}, MaxFaces=1, ExternalImageId=<user_id>, QualityFilter='AUTO', DetectionAttributes=['DEFAULT'])`. (3) If `len(response.FaceRecords) == 0` → reject with 400 (faces blocked by quality filter — error message includes `UnindexedFaces[0].Reasons`). Return `FaceRecords[0].Face.FaceId`. | 🛠 `IndexFaces(MaxFaces=1)` does NOT reject multi-face — DetectFaces gate is mandatory. 🛠 Reject when `FaceRecords` empty regardless of `UnindexedFaces` presence. |
| **Photo pipeline (per uploaded photo)** | (1) `DetectFaces(Image={Bytes}, MaxFaces=20, Attributes=['DEFAULT'])`. (2) Per detected face: crop with 15% pad + clamp + skip if final side <80 px. (3) `SearchFacesByImage(CollectionId, Image={Bytes:crop}, MaxFaces=1, FaceMatchThreshold=80, QualityFilter='AUTO')`. (4) Persist one `photoface` row per face (matched or not). | 1 detect + N searches, N+1 acceptable at PoC scale. |
| **Rematch on new enrol** | `SearchFaces(CollectionId, FaceId=<new_user_face_id>, MaxFaces=4096, FaceMatchThreshold=80)`. **Filter** results to `ExternalImageId.startswith("unmatched:")`. Update `photoface.user_id`. Then `DeleteFaces` the linked `unmatched:` entries. | 🛠 `SearchFaces` returns matches against ALL FaceIds — filtering is mandatory or two enrolled users could cross-tag. 🛠 Cleanup is mandatory or collection bloats and future searches get poisoned. |
| **Delete user** | `DeleteFaces(CollectionId, FaceIds=[user.rekognition_face_id])` — tolerate `ResourceNotFoundException`. | |

Future option (not in PoC): `SearchUsersByImage` (Rekognition User Collections, 2023+) — single-call N-face match. Worth a future refactor when face count exceeds ~50.

---

## 5. Schema migration

```sql
-- 1. user: add face id
ALTER TABLE "user" ADD COLUMN rekognition_face_id text NULL;
CREATE UNIQUE INDEX user_rekognition_face_id_uniq
  ON "user" (rekognition_face_id)
  WHERE rekognition_face_id IS NOT NULL;

-- 2. photoface: add face id, error column, bbox space marker
ALTER TABLE "photoface"
  ADD COLUMN rekognition_face_id text NULL,
  ADD COLUMN error text NULL,                                        -- 🛠 was missing from v2
  ADD COLUMN bbox_space text NOT NULL DEFAULT 'pixel';

-- 3. relax NOT NULL on legacy embedding (new rows won't populate it)
ALTER TABLE "photoface" ALTER COLUMN embedding DROP NOT NULL;        -- 🛠 CRITICAL; v2 missed this

-- 4. enum check for bbox_space
ALTER TABLE "photoface" ADD CONSTRAINT photoface_bbox_space_chk
  CHECK (bbox_space IN ('pixel','normalised'));

-- 5. index to speed rematch (filter user_id IS NULL AND removed=false)
CREATE INDEX photoface_user_removed_idx
  ON "photoface" (user_id, removed);

-- 6. index to find a photoface by its rekognition_face_id (for unmatched-cleanup lookups)
CREATE INDEX photoface_rekognition_face_id_idx
  ON "photoface" (rekognition_face_id);
```

Apply via `mcp__supabase__apply_migration`. The `ADD COLUMN ... NOT NULL DEFAULT` rewrites the table — instant at 56 rows; would need a 2-step migration at production scale.

**Legacy columns kept:** `user.face_embedding`, `photoface.embedding` (now nullable). Used only for partial rollback during the 24-hour soak; drop in a follow-up commit if migration sticks.

**Model changes** (`backend/app/models.py`):
```python
class User(SQLModel, table=True):
    ...
    rekognition_face_id: str | None = None

class PhotoFace(SQLModel, table=True):
    ...
    embedding: str | None = None                       # was: str (NOT NULL)
    rekognition_face_id: str | None = None
    error: str | None = None
    bbox_space: str = "normalised"                     # 🛠 default for new rows
```

Note the SQLModel `bbox_space` default is `'normalised'` (the new behaviour) even though the column DEFAULT in SQL is `'pixel'` (correct backfill for existing rows). New `PhotoFace()` constructions don't pass `bbox_space=` and inherit `'normalised'`.

---

## 6. Config changes

### `backend/app/config.py`

```python
AWS_ACCESS_KEY_ID: str = ""
AWS_SECRET_ACCESS_KEY: str = ""
AWS_REGION: str = "ap-south-1"
AWS_ACCOUNT_ID: str = ""                              # 🛠 startup asserts identity matches
REKOGNITION_COLLECTION_ID: str = "travelseasons-poc"
REKOGNITION_FACE_MATCH_THRESHOLD: float = 80.0        # percent 0-100
REKOGNITION_QUALITY_FILTER: str = "AUTO"              # NONE | LOW | MEDIUM | HIGH | AUTO
ALLOW_COLLECTION_DRIFT: bool = False                  # 🛠 lifespan guard
```

🛠 Remove the dangling old vars — sweep 4 references:
- `backend/app/config.py:25` — `FACE_MATCH_THRESHOLD`, `FACE_MODEL`
- `backend/app/main.py:27` — startup log
- `backend/app/routers/admin_pages.py:32-33` — both fields
- `backend/.env.example:14`

### `backend/.env`

```
AWS_ACCESS_KEY_ID=<rotated key>
AWS_SECRET_ACCESS_KEY=<rotated secret>
AWS_REGION=ap-south-1
AWS_ACCOUNT_ID=<12 digits from sts get-caller-identity>
REKOGNITION_COLLECTION_ID=travelseasons-poc
REKOGNITION_FACE_MATCH_THRESHOLD=80
```

### `backend/requirements.txt`

```
+ boto3>=1.34.0
- facenet-pytorch
- torch
- torchvision
- numpy                          # 🛠 confirmed only used in deleted face/engine.py
```

Keep `pillow` (used in 5 places outside `face/`).

---

## 7. Code changes file-by-file

### 7.1 `backend/app/face/aws.py` (NEW)

Thin Rekognition wrapper. **Sync methods** (boto3 is sync); called via `asyncio.to_thread` from async sites.

```python
from functools import lru_cache
from botocore.config import Config

_BOTO_CFG = lambda s: Config(
    region_name=s.AWS_REGION,
    retries={"mode": "adaptive", "max_attempts": 5},  # experimental but covers throttling
)

@lru_cache(maxsize=1)
def get_engine() -> "AwsFaceEngine":
    s = get_settings()
    if not (s.AWS_ACCESS_KEY_ID and s.AWS_SECRET_ACCESS_KEY):
        raise RuntimeError("AWS credentials missing — refusing to use boto3's credential chain")
    client = boto3.client(
        "rekognition",
        aws_access_key_id=s.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=s.AWS_SECRET_ACCESS_KEY,
        config=_BOTO_CFG(s),
    )
    # Sanity-check account identity to prevent accidentally hitting a dev's personal AWS.
    sts = boto3.client("sts", aws_access_key_id=s.AWS_ACCESS_KEY_ID, aws_secret_access_key=s.AWS_SECRET_ACCESS_KEY)
    if s.AWS_ACCOUNT_ID and sts.get_caller_identity()["Account"] != s.AWS_ACCOUNT_ID:
        raise RuntimeError(f"AWS account mismatch — refusing")
    return AwsFaceEngine(client, s.REKOGNITION_COLLECTION_ID)
```

🛠 Explicit credentials (don't trust env-var fallback). 🛠 Account-identity guard.

#### `AwsFaceEngine` public API

| Method | Returns | Notes |
|---|---|---|
| `ensure_collection()` | None | Idempotent; verifies `DescribeCollection.FaceCount` ≥ `SELECT count(*) FROM user WHERE rekognition_face_id IS NOT NULL`. If drift detected and `not ALLOW_COLLECTION_DRIFT`, raises — operator must run migration script or set the flag. 🛠 |
| `index_selfie(image_bytes, external_id) -> str` | AWS FaceId | Raises `ValueError` on 0 faces, >1 faces, or all rejected by quality filter (`len(FaceRecords) == 0`). Error message includes the `UnindexedFaces[0].Reasons` list. |
| `detect_and_match(image_bytes) -> DetectResult` | structured result | Never raises on per-face errors; packs them into the result. Raises only on `DetectFaces` itself failing or `AccessDeniedException`. |
| `index_unmatched(crop_bytes, photoface_id) -> str \| None` | AWS FaceId or None on quality reject | ExternalImageId = `unmatched:<photoface_id>` |
| `search_unmatched_for_user(user_face_id) -> list[(face_id, external_image_id, similarity)]` | matches against the collection | Calls `SearchFaces(MaxFaces=4096, FaceMatchThreshold=80)`. Filters to `external_image_id.startswith("unmatched:")`. |
| `delete_face(face_id)` | None | Tolerates `ResourceNotFoundException` |
| `bulk_delete_faces(face_ids: list[str])` | None | Up to 4096 per call |
| `describe_collection() -> int` | face count | Used by `/health` |

#### `DetectResult` dataclass

```python
@dataclass
class FaceItem:
    bbox: list[float]                  # 0-1 normalised, clamped to [0,1]
    detection_confidence: float        # 0-100
    matched_face_id: str | None        # AWS FaceId of matched person, if any
    matched_external_id: str | None    # our user_id, if matched
    match_similarity: float | None     # 0-100
    error: str | None                  # per-face: "throttled" | "too_small" | "quality_reject"

@dataclass
class DetectResult:
    faces: list[FaceItem]
    photo_error: str | None            # photo-level error (DetectFaces failure)
```

#### Cropping spec

```python
def crop_face(image_bytes: bytes, bbox: BoundingBox) -> tuple[bytes | None, str | None]:
    """Returns (crop_bytes, error)."""
    # 1. Clamp BoundingBox to [0, 1]
    L = max(0.0, min(1.0, bbox["Left"]))
    T = max(0.0, min(1.0, bbox["Top"]))
    W = max(0.0, min(1.0, bbox["Width"]))
    H = max(0.0, min(1.0, bbox["Height"]))
    # 2. Pixel coords
    img = Image.open(BytesIO(image_bytes))
    w, h = img.size
    px = (round(L*w), round(T*h), round((L+W)*w), round((T+H)*h))
    # 3. Pad 15%
    pad_w = round(0.15 * W * w); pad_h = round(0.15 * H * h)
    px = (max(0, px[0]-pad_w), max(0, px[1]-pad_h),
          min(w, px[2]+pad_w), min(h, px[3]+pad_h))
    # 4. Min-size check (Rekognition minimum is 40px; we use 80 for margin)
    if (px[2]-px[0]) < 80 or (px[3]-px[1]) < 80:
        return None, "too_small"
    # 5. Encode JPEG q=85
    crop = img.crop(px).convert("RGB")
    buf = BytesIO(); crop.save(buf, "JPEG", quality=85)
    return buf.getvalue(), None
```

### 7.2 `backend/app/face/engine.py` → DELETE
### 7.3 `backend/app/face/matcher.py` → DELETE
### 7.4 `backend/app/face/__init__.py`

```python
from .aws import get_engine, FaceItem, DetectResult
```

### 7.5 `backend/app/tasks/process_photos.py`

🛠 Drop the `asyncio.run(_process_one_photo(photo_id))` wrapper — that spawns a fresh event loop inside the Starlette threadpool worker, doubling thread usage when boto3 calls also go via `to_thread`. Make `_process_one_photo` synchronous; call boto3 directly; keep `threading.Semaphore(4)` around Pillow ops.

```python
def _run_async(photo_id: str) -> None:
    """Entry point for FastAPI BackgroundTasks (sync function in Starlette threadpool)."""
    try:
        _process_one_photo(photo_id)
    except Exception:
        log.exception(...)

_engine_semaphore = threading.Semaphore(4)        # CPU-bound Pillow ops only

def _process_one_photo(photo_id: str) -> None:
    storage = get_storage()
    with session_scope() as s:
        photo = s.get(Photo, photo_id)
        if photo is None: return
        photo.status = "processing"
        s.commit()
    try:
        image_bytes = asyncio.run(storage.get_bytes(...))     # storage abstraction is async
        # Pre-resize if >5 MB
        if len(image_bytes) > 5 * 1024 * 1024:                # 5MB AWS hard limit; pre-resize
            image_bytes = _resize_to_fit(image_bytes, max_side=4000, max_bytes=4_500_000)
        with _engine_semaphore:
            width, height = _read_dims(image_bytes)
        result = get_engine().detect_and_match(image_bytes)
        with session_scope() as s:
            if result.photo_error:
                ph = s.get(Photo, photo_id); ph.status="failed"; ph.error=result.photo_error
            else:
                for face in result.faces:
                    pf = PhotoFace(
                        photo_id=photo.id,
                        user_id=_user_id_from_eid(face.matched_external_id),
                        bbox=json.dumps(face.bbox),         # 0-1 normalised
                        bbox_space="normalised",
                        rekognition_face_id=face.matched_face_id,
                        confidence=face.match_similarity,   # 0-100
                        source="auto",
                        removed=False,
                        error=face.error,
                        embedding=None,                      # legacy column nullable
                    )
                    s.add(pf); s.flush()
                    # Index unmatched faces for future rematch
                    if face.matched_external_id is None and face.error is None:
                        crop_bytes, _ = crop_face(image_bytes, face.bbox)
                        if crop_bytes:
                            rek_id = get_engine().index_unmatched(crop_bytes, pf.id)
                            if rek_id:
                                pf.rekognition_face_id = rek_id
                                s.add(pf)
                ph = s.get(Photo, photo_id); ph.status="done"; ph.width=width; ph.height=height
                ph.processed_at = datetime.now(timezone.utc)
            s.commit()
    except Exception as e:
        log.exception(...)
        with session_scope() as s:
            ph = s.get(Photo, photo_id)
            if ph is not None:
                ph.status = "failed"; ph.error = str(e)[:500]
                s.commit()
```

`_user_id_from_eid()` — returns the user.id if `external_image_id` is a UUID, None if it's `unmatched:...`.

### 7.6 `backend/app/tasks/rematch.py`

```python
def rematch_unmatched_after_enrol(session: Session, new_user: User) -> int:
    """Called after a successful IndexFaces for a new user."""
    eng = get_engine()
    matches = eng.search_unmatched_for_user(new_user.rekognition_face_id)
    # matches: [(face_id, external_image_id, similarity)] already filtered to unmatched:*
    tagged_face_ids: list[str] = []
    for face_id, eid, sim in matches:
        pf_id = eid.split(":", 1)[1]
        pf = session.get(PhotoFace, pf_id)
        if pf is None or pf.removed or pf.user_id is not None:
            continue
        pf.user_id = new_user.id
        pf.rekognition_face_id = new_user.rekognition_face_id
        pf.confidence = sim
        pf.source = "auto"
        session.add(pf)
        tagged_face_ids.append(face_id)
    session.commit()
    if tagged_face_ids:
        eng.bulk_delete_faces(tagged_face_ids)               # 🛠 cleanup mandatory
    return len(tagged_face_ids)


def rematch_all_unmatched(session: Session) -> int:
    """Admin endpoint /admin/rematch-all. Runs rematch for every active user."""
    users = session.exec(select(User).where(
        User.deleted_at == None, User.rekognition_face_id != None,
    )).all()
    return sum(rematch_unmatched_after_enrol(session, u) for u in users)
```

🛠 The admin endpoint `/admin/rematch-all` (which v2 missed) now points at `rematch_all_unmatched` instead of the deleted facenet-era `rematch_unmatched_faces`.

### 7.7 `backend/app/routers/enrollments.py`

```python
async def create_enrollment(name, email, selfie, user_id, session):
    image_bytes = await selfie.read()
    if not image_bytes: raise 400
    if len(image_bytes) > 5*1024*1024:
        image_bytes = _resize_to_fit(image_bytes, max_side=4000, max_bytes=4_500_000)
    if len(image_bytes) > 5*1024*1024:
        raise HTTPException(413, "selfie too large even after resize")

    # Replace flow: delete old AWS face first
    existing = session.get(User, user_id) if user_id else None
    if existing and existing.rekognition_face_id:
        await asyncio.to_thread(get_engine().delete_face, existing.rekognition_face_id)
        existing.rekognition_face_id = None

    try:
        face_id = await asyncio.to_thread(
            get_engine().index_selfie, image_bytes, external_id=user_id_or_new
        )
    except ValueError as e:
        raise HTTPException(400, str(e))             # 0, >1 faces, or quality reject

    # ... save selfie to Supabase, save user with rekognition_face_id ...
    await asyncio.to_thread(rematch_unmatched_after_enrol, session, user)
    return UserOut(...)
```

🛠 `embed_single_face` call site replaced with `index_selfie`. Update README smoke-test snippet too.

### 7.8 `backend/app/routers/users.py`

```python
DELETE /users/{user_id}:
    user.soft-delete (deleted_at)
    if user.rekognition_face_id:
        await asyncio.to_thread(get_engine().delete_face, user.rekognition_face_id)
        user.rekognition_face_id = None
    mark photoface.removed=true where user_id=user_id  (unchanged)
```

### 7.9 `backend/app/main.py`

Existing `@asynccontextmanager` lifespan ALREADY in use (`main.py:24-29`). Add to it:
```python
@asynccontextmanager
async def lifespan(app):
    s = get_settings()
    if s.mode == "local" and not s.AWS_ACCESS_KEY_ID:
        raise RuntimeError("face engine requires AWS creds; local mode unsupported")
    await asyncio.to_thread(get_engine().ensure_collection)
    log.info("face_engine=rekognition collection=%s", s.REKOGNITION_COLLECTION_ID)
    yield
```

🛠 Drop the `FACE_MATCH_THRESHOLD` / `FACE_MODEL` from any current startup log.

### 7.10 `/health` endpoint (in `main.py` or `routers/admin_pages.py`)

Required fields:
```json
{
  "ok": true,
  "mode": "supabase",
  "face_engine": "rekognition",
  "collection": "travelseasons-poc",
  "collection_face_count": 4,
  "threshold": 80
}
```

🛠 `face_engine`, `collection`, `collection_face_count` are required for the smoke test in §10.

### 7.11 `backend/app/routers/admin_pages.py`

```python
# line 11 was: from ..tasks.rematch import rematch_unmatched_faces
from ..tasks.rematch import rematch_all_unmatched                   # 🛠 renamed
# line 32-33 was: model=s.FACE_MODEL, threshold=s.FACE_MATCH_THRESHOLD,
threshold=s.REKOGNITION_FACE_MATCH_THRESHOLD,                       # 🛠 sweep
# line 40 was: tagged = rematch_unmatched_faces(session)
tagged = rematch_all_unmatched(session)                              # 🛠 new name
```

### 7.12 `admin/app.js`

🛠 **No change needed.** Reviewer verified admin renders chips only, not bbox rectangles.

### 7.13 `app/lib/photos/models/photo.dart`

Pre-coding task: grep for `bbox` usage. If the Flutter app renders the bbox rectangle, multiply normalised coords by photo dims. If not (likely), no change.

### 7.14 `backend/README.md`

🛠 Replace the `embed_single_face` smoke-test snippet (line ~33) with a curl recipe (see §10).

---

## 8. Edge cases catalog

| # | Case | Handling |
|---|---|---|
| 1 | Selfie 0 faces | 400 (DetectFaces count==0) |
| 2 | Selfie >1 faces | 400 (DetectFaces count>1). Plain `IndexFaces(MaxFaces=1)` does NOT enforce this. |
| 3 | Selfie blurry/poor quality | 400. After `IndexFaces`, if `FaceRecords` empty → reject with reason from `UnindexedFaces[0].Reasons`. |
| 4 | Selfie >5 MB | Pre-resize to ≤4 MB; if still too big → 413. |
| 5 | Selfie corrupt / non-JPEG/PNG | `InvalidImageFormatException` → 400 |
| 6 | Re-enrol same user_id | DeleteFaces old → IndexFaces new → update DB |
| 7 | Soft-deleted user re-enrolled | clear `deleted_at`, fresh IndexFaces, new face_id |
| 8 | Photo 0 faces | OK — status=done, no rows |
| 9 | Photo >20 faces | `DetectFaces(MaxFaces=20)` — top 20 by detection confidence |
| 10 | Network failure mid-photo | `photo.status='failed'`, `photo.error=str(e)[:500]` |
| 11 | `ThrottlingException` | boto3 adaptive retry handles; if still fails, that face's row gets `error='throttled'`, photo overall stays `done` |
| 12 | IAM creds wrong | `AccessDeniedException` at startup `ensure_collection()`. Refuse to boot. |
| 13 | Collection deleted in AWS console | Startup re-creates empty; all `face_id`s stale. Lifespan **drift check** refuses boot unless `ALLOW_COLLECTION_DRIFT=1`. Recovery: run migration script in re-enroll mode. |
| 14 | Two users similar faces | `SearchFacesByImage` returns top match above threshold. Same as current. |
| 15 | Same face N times in one photo | N independent searches → N rows |
| 16 | Manual override `PATCH .../faces` | Unchanged. Manual rows preserved through migration. |
| 17 | bbox space mismatch old vs new | Old rows: `bbox_space='pixel'`. New rows: `bbox_space='normalised'`. CHECK constraint enforced. |
| 18 | First selfie before collection exists | Lifespan ensures it. |
| 19 | Photo deleted from Supabase mid-processing | `storage.get_bytes` raises → status=failed |
| 20 | `InvalidImageFormatException` / `InvalidParameterException` | 400 |
| 21 | `ImageTooLargeException` (post-resize sanity) | 413 |
| 22 | `ServiceQuotaExceededException` | 503 |
| 23 | `IndexFaces.UnindexedFaces` populated for selfie | 400 with reasons list |
| 24 | bbox negative or >1 | Clamp to `[0,1]` before persist |
| 25 | Crop <80 px | Skip face; row written with `error='too_small'` |
| 26 | `unmatched:` cross-contamination | Filter `SearchFaces` results to `unmatched:` prefix |
| 27 | `unmatched:` pollution | `DeleteFaces` after linking |
| 28 | Concurrent enrol races on same `rekognition_face_id` | UNIQUE partial index catches; PoC has 1 enroller at a time |
| 29 | Concurrent uploads of unknown faces | Tolerated — duplicate `unmatched:` entries linked on next enrol |
| 30 | Collection drift on rename | Lifespan asserts count match unless `ALLOW_COLLECTION_DRIFT=1` |
| 31 | Selfie URL 404 during migration | Skip user, log `migration_status='selfie_missing'`, continue |
| 32 | `photo.width IS NULL` during phase C | Skip row, log warning |

---

## 9. Migration script

**Location:** `backend/scripts/migrate_to_rekognition.py` (mirrors `backend/scripts/backfill_captions.py` convention — `load_dotenv(dotenv_path='../.env')`, direct `create_engine(SUPABASE_DB_URL)`).

**Phases:**

```
A. ensure_collection()

B. Build collection-side index (ONCE, then reuse):
   resp = client.list_faces(CollectionId, MaxResults=4096)
   collection_eid_to_face = {f.ExternalImageId: f.FaceId for f in resp.Faces}
   while resp.NextToken: ... (paginate)

   For each User where deleted_at IS NULL:
      if user.rekognition_face_id:
          # already enrolled (idempotent skip)
          continue
      if user.id in collection_eid_to_face:
          # AWS has them but DB doesn't — save the face_id, no AWS write
          user.rekognition_face_id = collection_eid_to_face[user.id]
          commit
          continue
      try:
          bytes = storage.get_bytes(user.selfie_path)
      except NotFoundError:
          log "selfie missing for {user.id}"; continue
      bytes = resize_if_needed(bytes)
      # Pre-DetectFaces gate to mirror enrolments router
      faces = DetectFaces(bytes)
      if len(faces) != 1: log + continue
      resp = IndexFaces(bytes, ExternalImageId=user.id, MaxFaces=1)
      if not resp.FaceRecords:
          log "quality reject"; continue
      user.rekognition_face_id = resp.FaceRecords[0].Face.FaceId
      commit IN SAME TXN

C. Preserve manual photoface rows:
   For each photoface where source='manual' AND removed=false AND bbox_space='pixel':
      ph = session.get(Photo, pf.photo_id)
      if ph.width is None or ph.height is None: log + skip
      bbox_px = json.loads(pf.bbox)
      bbox_norm = [bbox_px[0]/ph.width, bbox_px[1]/ph.height,
                   bbox_px[2]/ph.width, bbox_px[3]/ph.height]
      pf.bbox = json.dumps(bbox_norm); pf.bbox_space = 'normalised'
      session.add(pf)
   commit
   # NOTE: current DB has 0 manual rows; phase is a no-op today.

D. Wipe + re-process auto rows:
   # Stop the backend before this phase — concurrent uploads would race the wipe.
   DELETE FROM photoface WHERE source='auto' AND removed=false
   UPDATE photo SET status='pending' WHERE status='done'
   # Backfill is sequential — call _process_one_photo directly, NOT BackgroundTasks
   from app.tasks.process_photos import _process_one_photo
   for photo_id in pending_photos:
       _process_one_photo(photo_id)

E. Summary log: enrolled / skipped / missing-selfie / manual-preserved / photos-reprocessed
```

### Idempotency invariants

- Already-enrolled user (DB and AWS in sync) → skip.
- DB has `rekognition_face_id` but collection doesn't → re-index, update DB.
- Collection has face for `user.id` but DB doesn't → save face_id, no AWS write.
- Selfie 404 → flag, continue.
- Each user is its own transaction.
- Phase D runs only after backend is stopped (avoid race with live uploads).

### `--dry-run` semantics

Read-only AWS calls (`ListFaces`, `DescribeCollection`, `DetectFaces`) execute; **no** `IndexFaces`, `DeleteFaces`, `CreateCollection` calls. Assert this in code:

```python
if dry_run:
    assert called_api not in {"IndexFaces", "DeleteFaces", "CreateCollection"}
```

### Resume drill (if script crashes)

- **Phase B crash:** re-run with same args. Pre-check catches already-enrolled users; will skip.
- **Phase D crash mid-photo:** `SELECT count(*) FROM photo WHERE status='processing'` — those need their status reset to `pending`. Re-run the script (or just phase D).

---

## 10. Verification & smoke test

### Test fixtures

```
backend/testdata/me.jpg       # single clear face
backend/testdata/group.jpg    # 2+ faces incl. me.jpg's face
```

Get the test data from the existing real selfies in Supabase Storage (download manually) or use freshly captured photos.

### Smoke test

```bash
# 1) health
curl -s http://localhost:8000/health | jq '.face_engine, .collection, .collection_face_count'
# expect: "rekognition" "travelseasons-poc" <N>

# 2) create test trip
export TRIP=$(curl -s -X POST http://localhost:8000/trips \
  -H "Content-Type: application/json" -d '{"name":"smoke"}' | jq -r .id)

# 3) enrol a test user
export USER_ID=$(curl -s -F "name=Test" -F "selfie=@backend/testdata/me.jpg" \
  http://localhost:8000/enrollments | jq -r .id)

# 4) collection face count should be N+1
curl -s http://localhost:8000/health | jq '.collection_face_count'

# 5) upload group photo + wait
curl -s -F "files=@backend/testdata/group.jpg" \
  http://localhost:8000/trips/$TRIP/photos
until [ "$(curl -s http://localhost:8000/trips/$TRIP/photos/status | jq -r .pending)" = "0" ]; do sleep 2; done

# 6) inspect tagged faces
curl -s "http://localhost:8000/trips/$TRIP/photos?filter=me" \
  -H "X-User-Id: $USER_ID" | jq '.[0].faces'
# expect: ≥1 face with user_id == $USER_ID

# 7) delete user — face count should go back down
curl -s -X DELETE http://localhost:8000/users/$USER_ID
curl -s http://localhost:8000/health | jq '.collection_face_count'
# expect: N again
```

Pass criteria:
- Step 4 == Step 1 + 1
- Step 6 returns ≥1 face with `user_id == $USER_ID`
- Step 7 == Step 1

---

## 11. Logging contract

Every Rekognition call must log:

| Event | Log fields |
|---|---|
| `ensure_collection()` | `collection=, face_count=, status=created\|exists\|drift_warning` |
| `index_selfie()` entry | `user_id=, image_bytes=` |
| `index_selfie()` exit | `user_id=, face_id=, unindexed_reasons=, request_id=, ms=` |
| `detect_and_match()` | `photo_id=, detected_count=, matched_count=, unmatched_count=, quality_rejected_count=, errors=, request_id=, ms=` |
| Per face | `photo_id=, face_idx=, bbox=, det_conf=, matched_user_id=, similarity=, error=` |
| `delete_face()` | `face_id=, status=ok\|not_found\|error` |
| `bulk_delete_faces()` | `count=, status=ok` |
| `search_unmatched_for_user()` | `user_face_id=, match_count=, filtered_count=` |
| Migration script | per-user line + final summary table |

All AWS error logs MUST include the AWS request ID: `response['ResponseMetadata']['RequestId']`.

---

## 12. Rollback (honest)

🛠 No more "one-line rollback" claim.

| Path | What it gets you |
|---|---|
| **Code-only revert (24h window)** | The 3 existing users + 22 photos already in the DB still tag correctly (legacy `face_embedding` columns intact). NEW uploads after migration have no embeddings → they'd need facenet to be re-run on those bytes. Backend boot would fail because `models.py` no longer matches the migrated schema — schema rollback is required too. |
| **Schema + code revert** | Reverse the 6 ALTER statements (drop columns, restore NOT NULL). Old behaviour fully restored for old data. New data still has no embeddings. |
| **Hard rollback after a week** | Run facenet against all new photos to backfill embeddings. ~30 min of compute on ~100 photos. |
| **AWS cleanup** | `aws rekognition delete-collection --collection-id travelseasons-poc` to stop the storage charge. |

In practice: if rollback is needed within 24h, do the code+schema revert. Past that, dual-run facenet to backfill, then revert.

---

## 13. Execution order on the day

0. **Pre-flight** (§0). Rotate key, set billing alert, update CLAUDE.md, get account ID.
1. Apply schema migration (Supabase MCP `apply_migration`).
2. Update `requirements.txt`; `pip install -r requirements.txt`; `pip uninstall torch torchvision facenet-pytorch numpy`.
3. Write `backend/app/face/aws.py`.
4. Delete `backend/app/face/engine.py` + `matcher.py`.
5. Update `process_photos.py`, `rematch.py`, `enrollments.py`, `users.py`, `main.py`, `config.py`, `admin_pages.py`.
6. Update `backend/README.md` smoke-test snippet, `.env.example`.
7. Restart backend. `/health` should show `face_engine: rekognition`, `collection_face_count: 0`. (Should NOT show `model:` field.)
8. **Stop backend.** Run `python -m backend.scripts.migrate_to_rekognition --dry-run`; review output. Then run without `--dry-run`.
9. **Start backend.** Run smoke test from §10.
10. Test admin: enrol via admin UI, upload via admin UI, verify tags appear, delete user → tags disappear.
11. Commit + push.
12. (Optional, after 24h soak) Drop the `face_embedding`, `embedding` legacy columns in a follow-up commit.

🛠 `facenet model cache cleanup` (rollback safety): `rm -rf %USERPROFILE%\.cache\torch\hub\checkpoints\` ONLY after the 24h soak passes.

---

## 14. Open questions / decisions to lock

| Decision | Choice |
|---|---|
| bbox coordinate space | **normalised 0-1** (Rekognition native). Old manual rows tagged `bbox_space='pixel'`. |
| Match threshold | **80** (Rekognition default). Tune via admin if needed. |
| Quality filter | **AUTO**. Switch to `NONE` only if real faces are being dropped. |
| Re-process idempotency | delete-then-insert for `source='auto'` rows. Manual preserved. |
| Max faces per photo | 20 (`DetectFaces.MaxFaces=20`). |
| `SearchUsersByImage` (User Collections, 2023+) | **Not** in PoC. Future refactor when count > 50. |
| Local mode (SQLite) | **Unsupported**. Startup refuses to boot. |
| Migration script invocation | `python -m backend.scripts.migrate_to_rekognition [--dry-run]` |

---

## 15. Effort estimate

| Step | Time |
|---|---|
| Pre-flight (rotate key, billing alarm, CLAUDE.md) | 15 min |
| Schema migration + config sweep | 20 min |
| `aws.py` + factory + crop math | 75 min |
| Rewire 5 routers/tasks (including `admin_pages.py`) | 60 min |
| Migration script with phases A–E + `--dry-run` | 60 min |
| Verification (smoke test + admin path) | 30 min |
| Buffer for AWS gotchas | 20 min |
| **Total** | **~4.5 hours** |
