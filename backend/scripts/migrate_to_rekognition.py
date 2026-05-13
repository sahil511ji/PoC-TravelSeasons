"""Migrate facenet-era face data to AWS Rekognition.

Phases:
  A. ensure_collection
  B. enrol existing users (idempotent via ListFaces pre-check)
  C. preserve any source='manual' photoface rows by converting bbox_space pixel→normalised
  D. wipe source='auto' photoface rows and re-process all photos via the Rekognition pipeline
  E. summary

Run from backend/ folder:
    python -m scripts.migrate_to_rekognition --dry-run
    python -m scripts.migrate_to_rekognition

--dry-run: performs read-only AWS calls (ListFaces, DescribeCollection, DetectFaces)
            and NO IndexFaces / DeleteFaces / DELETE FROM photoface / UPDATE photo.

CRITICAL: stop the backend before running for real. Phase D wipes + reprocesses
photos and is racy with concurrent uploads.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

# .env is one directory above this script (backend/.env).
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# Add the backend root to sys.path so we can import `app.*`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlmodel import Session, create_engine, text  # noqa: E402

from app.face import get_engine, resize_if_oversized  # noqa: E402
from app.tasks.process_photos import _process_one_photo  # noqa: E402


@dataclass
class MigrationSummary:
    enrolled: int = 0
    already_enrolled: int = 0
    selfie_missing: int = 0
    quality_rejected: int = 0
    multi_face_selfie: int = 0
    manual_converted: int = 0
    photos_reprocessed: int = 0
    photos_failed: int = 0
    errors: list[str] = field(default_factory=list)

    def report(self) -> None:
        print()
        print("=" * 60)
        print("Migration summary")
        print("=" * 60)
        for k, v in self.__dict__.items():
            if k == "errors":
                continue
            print(f"  {k:<24} {v}")
        if self.errors:
            print()
            print("Errors:")
            for e in self.errors[:20]:
                print(f"  - {e}")
            if len(self.errors) > 20:
                print(f"  ... ({len(self.errors) - 20} more)")


def _db_engine():
    db_url = os.environ["SUPABASE_DB_URL"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(db_url)


def _supabase_storage():
    """Lazy-create a Supabase storage client for selfie + photo downloads."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    bucket = os.environ.get("SUPABASE_BUCKET", "travelseasons-poc")
    sb = create_client(url, key)
    return sb.storage.from_(bucket)


def phase_a_ensure_collection(dry_run: bool, summary: MigrationSummary) -> int:
    print("\n[Phase A] ensure collection")
    eng = get_engine()
    info = eng.describe_collection()
    face_count = int(info.get("face_count", 0))
    print(f"  current face_count = {face_count}")
    if dry_run:
        print("  --dry-run: not creating if missing")
    else:
        result = eng.ensure_collection()
        print(f"  ensure_collection → {result['status']} face_count={result['face_count']}")
    return face_count


def phase_b_enrol_users(dry_run: bool, summary: MigrationSummary) -> None:
    print("\n[Phase B] enrol existing users in Rekognition")
    eng = get_engine()
    storage = _supabase_storage()
    db = _db_engine()

    # Build collection-side index ONCE.
    print("  listing existing collection faces...")
    collection_eid_to_face = eng.list_all_faces()
    print(f"  collection contains {len(collection_eid_to_face)} face(s) with ExternalImageId")

    with Session(db) as s:
        rows = s.execute(text(
            "SELECT id, name, selfie_path, rekognition_face_id "
            "FROM \"user\" WHERE deleted_at IS NULL ORDER BY created_at"
        )).fetchall()
        print(f"  found {len(rows)} active user(s)")

        for row in rows:
            user_id, name, selfie_path, current_face_id = row
            tag = f"  - {name} ({user_id[:8]}):"

            # Already enrolled?
            if current_face_id:
                if current_face_id in collection_eid_to_face.values():
                    print(f"{tag} already enrolled (face_id={current_face_id[:8]}). skip.")
                    summary.already_enrolled += 1
                    continue
                else:
                    # DB thinks user is enrolled but AWS doesn't have them — fall through to re-enrol.
                    print(f"{tag} DB has face_id but collection doesn't — re-enrolling")

            # Does collection have them under our user_id ExternalImageId?
            existing_face_id = collection_eid_to_face.get(user_id)
            if existing_face_id and not current_face_id:
                print(f"{tag} collection has face_id={existing_face_id[:8]}, syncing to DB")
                if not dry_run:
                    s.execute(text(
                        "UPDATE \"user\" SET rekognition_face_id = :fid WHERE id = :uid"
                    ), {"fid": existing_face_id, "uid": user_id})
                    s.commit()
                summary.already_enrolled += 1
                continue

            if not selfie_path:
                msg = f"{tag} no selfie_path, skip"
                print(msg)
                summary.selfie_missing += 1
                summary.errors.append(msg)
                continue

            # Download selfie from Supabase Storage.
            try:
                bytes_ = storage.download(selfie_path)
            except Exception as e:
                msg = f"{tag} selfie download failed: {e}"
                print(msg)
                summary.selfie_missing += 1
                summary.errors.append(msg)
                continue

            bytes_ = resize_if_oversized(bytes_)

            if dry_run:
                print(f"{tag} would index ({len(bytes_)} bytes)")
                continue

            try:
                face_id = eng.index_selfie(bytes_, external_id=user_id)
            except ValueError as e:
                msg = f"{tag} index_selfie rejected: {e}"
                print(msg)
                if "multiple" in str(e).lower():
                    summary.multi_face_selfie += 1
                else:
                    summary.quality_rejected += 1
                summary.errors.append(msg)
                continue

            # Save in DB (same transaction).
            try:
                s.execute(text(
                    "UPDATE \"user\" SET rekognition_face_id = :fid WHERE id = :uid"
                ), {"fid": face_id, "uid": user_id})
                s.commit()
            except Exception as e:
                # DB write failed → undo the AWS index so we don't orphan the FaceId.
                msg = f"{tag} DB write failed after IndexFaces — rolling back AWS face_id={face_id}: {e}"
                print(msg)
                try:
                    eng.delete_face(face_id)
                except Exception:
                    pass
                summary.errors.append(msg)
                continue

            print(f"{tag} enrolled face_id={face_id[:8]}")
            summary.enrolled += 1


def phase_c_preserve_manual(dry_run: bool, summary: MigrationSummary) -> None:
    print("\n[Phase C] preserve source='manual' photoface rows (convert bbox to normalised)")
    db = _db_engine()
    with Session(db) as s:
        rows = s.execute(text("""
            SELECT pf.id, pf.bbox, ph.width, ph.height
            FROM photoface pf JOIN photo ph ON pf.photo_id = ph.id
            WHERE pf.source = 'manual' AND pf.removed = false AND pf.bbox_space = 'pixel'
        """)).fetchall()
        print(f"  found {len(rows)} manual row(s) to convert")

        for pf_id, bbox_json, w, h in rows:
            if not w or not h:
                msg = f"  - skip {pf_id[:8]}: photo width/height missing"
                print(msg)
                summary.errors.append(msg)
                continue
            try:
                bbox = json.loads(bbox_json)
                if len(bbox) != 4:
                    raise ValueError(f"bad bbox len {len(bbox)}")
                normalised = [bbox[0] / w, bbox[1] / h, bbox[2] / w, bbox[3] / h]
            except Exception as e:
                msg = f"  - skip {pf_id[:8]}: bbox parse failed: {e}"
                print(msg)
                summary.errors.append(msg)
                continue
            if dry_run:
                print(f"  - would convert {pf_id[:8]}: {bbox} → {normalised}")
            else:
                s.execute(text("""
                    UPDATE photoface SET bbox = :b, bbox_space = 'normalised' WHERE id = :id
                """), {"b": json.dumps(normalised), "id": pf_id})
            summary.manual_converted += 1
        if not dry_run:
            s.commit()


def phase_d_reprocess_photos(dry_run: bool, summary: MigrationSummary) -> None:
    print("\n[Phase D] wipe source='auto' photoface rows + re-process photos")
    db = _db_engine()
    with Session(db) as s:
        photo_count = s.execute(text("SELECT count(*) FROM photo WHERE status = 'done'")).scalar() or 0
        auto_count = s.execute(text(
            "SELECT count(*) FROM photoface WHERE source = 'auto' AND removed = false"
        )).scalar() or 0
        print(f"  {photo_count} done photo(s), {auto_count} auto photoface row(s)")
        if dry_run:
            print("  --dry-run: not deleting + not re-processing")
            return

        confirm = input(
            "  This will DELETE all source='auto' photoface rows and re-process every done photo. "
            "Type 'yes' to continue: "
        ).strip().lower()
        if confirm != "yes":
            print("  aborted by user")
            return

        s.execute(text("DELETE FROM photoface WHERE source = 'auto'"))
        s.execute(text(
            "UPDATE photo SET status = 'pending', error = NULL "
            "WHERE status IN ('done', 'failed', 'processing')"
        ))
        s.commit()
        pending = s.execute(text(
            "SELECT id FROM photo WHERE status = 'pending' ORDER BY uploaded_at"
        )).fetchall()
        print(f"  re-processing {len(pending)} photo(s) sequentially...")

        for i, (pid,) in enumerate(pending, 1):
            print(f"  [{i}/{len(pending)}] {pid[:8]} ...", end=" ", flush=True)
            t0 = time.monotonic()
            try:
                _process_one_photo(pid)
            except Exception as e:
                print(f"FAILED ({e})")
                summary.photos_failed += 1
                continue
            # Read back status
            with Session(db) as s2:
                status = s2.execute(
                    text("SELECT status FROM photo WHERE id = :id"), {"id": pid}
                ).scalar()
            elapsed = time.monotonic() - t0
            print(f"{status} ({elapsed:.1f}s)")
            if status == "done":
                summary.photos_reprocessed += 1
            else:
                summary.photos_failed += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-phase-d", action="store_true",
                    help="Skip wiping + re-processing photos (use for testing phase B/C only)")
    args = ap.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no AWS writes, no DB writes ===")
    else:
        print("=== LIVE RUN — backend MUST be stopped before phase D ===")

    summary = MigrationSummary()
    phase_a_ensure_collection(args.dry_run, summary)
    phase_b_enrol_users(args.dry_run, summary)
    phase_c_preserve_manual(args.dry_run, summary)
    if not args.skip_phase_d:
        phase_d_reprocess_photos(args.dry_run, summary)
    else:
        print("\n[Phase D] SKIPPED (--skip-phase-d)")
    summary.report()


if __name__ == "__main__":
    main()
