"""AWS Rekognition face engine.

Replaces the facenet-pytorch local engine. boto3 is synchronous; callers in
async contexts should wrap method calls with ``asyncio.to_thread(...)``.

Collection: one per backend instance, name from ``settings.REKOGNITION_COLLECTION_ID``.
Face matching is done server-side by Rekognition — we don't store embeddings.
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from PIL import Image, ImageOps

from ..config import get_settings

log = logging.getLogger(__name__)


@dataclass
class FaceItem:
    bbox: list[float]                   # [x, y, w, h] in 0-1 normalised, clamped to [0,1]
    detection_confidence: float         # 0-100
    matched_face_id: str | None = None  # AWS FaceId of matched person
    matched_external_id: str | None = None  # our user_id (None if unmatched)
    match_similarity: float | None = None   # 0-100
    error: str | None = None            # per-face: "throttled" | "too_small" | "quality_reject"


@dataclass
class DetectResult:
    faces: list[FaceItem] = field(default_factory=list)
    photo_error: str | None = None      # photo-level error (DetectFaces failure)


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _bbox_to_xywh_normalised(b: dict[str, float]) -> list[float]:
    """Rekognition BoundingBox → [x, y, w, h], clamped to [0,1]."""
    return [
        _clamp01(b["Left"]),
        _clamp01(b["Top"]),
        _clamp01(b["Width"]),
        _clamp01(b["Height"]),
    ]


def _open_rgb(image_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _is_jpeg_or_png(image_bytes: bytes) -> bool:
    """Cheap magic-byte sniff — Rekognition only accepts JPEG and PNG."""
    if len(image_bytes) < 8:
        return False
    # JPEG: FF D8 FF
    if image_bytes[0:3] == b"\xff\xd8\xff":
        return True
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if image_bytes[0:8] == b"\x89PNG\r\n\x1a\n":
        return True
    return False


def resize_if_oversized(image_bytes: bytes, max_bytes: int = 4_500_000, max_side: int = 4000) -> bytes:
    """Re-encode to fit Rekognition's 5 MB inline limit AND force JPEG output.

    Rekognition rejects WebP/HEIC/AVIF/etc. Always pass through Pillow when the
    input isn't already JPEG/PNG so we hand Rekognition a clean JPEG.
    """
    needs_reencode = len(image_bytes) > max_bytes or not _is_jpeg_or_png(image_bytes)
    if not needs_reencode:
        return image_bytes
    img = _open_rgb(image_bytes)
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        scale = max_side / longest
        img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    data = out.getvalue()
    # If still too big, keep stepping quality down
    for q in (78, 70, 60):
        if len(data) <= max_bytes:
            break
        out = io.BytesIO()
        img.save(out, "JPEG", quality=q)
        data = out.getvalue()
    return data


def crop_face(image_bytes: bytes, bbox_norm: list[float], pad_ratio: float = 0.15) -> tuple[bytes | None, str | None]:
    """Crop a face out of a JPEG using normalised bbox.

    Returns (crop_bytes, error). error is "too_small" if the final crop is
    under 80 px on either side (Rekognition's min is 40 px; we use 80 for margin).
    """
    img = _open_rgb(image_bytes)
    w, h = img.size
    x = _clamp01(bbox_norm[0]) * w
    y = _clamp01(bbox_norm[1]) * h
    bw = _clamp01(bbox_norm[2]) * w
    bh = _clamp01(bbox_norm[3]) * h

    pad_x = pad_ratio * bw
    pad_y = pad_ratio * bh
    left = max(0, round(x - pad_x))
    top = max(0, round(y - pad_y))
    right = min(w, round(x + bw + pad_x))
    bottom = min(h, round(y + bh + pad_y))

    if (right - left) < 80 or (bottom - top) < 80:
        return None, "too_small"

    crop = img.crop((left, top, right, bottom))
    out = io.BytesIO()
    crop.save(out, "JPEG", quality=85)
    return out.getvalue(), None


class AwsFaceEngine:
    """Thin Rekognition wrapper. Sync methods; wrap with ``asyncio.to_thread``."""

    def __init__(self, client: Any, collection_id: str) -> None:
        self._client = client
        self._collection_id = collection_id

    # ---------- collection lifecycle ----------

    def ensure_collection(self) -> dict[str, Any]:
        """Create the collection if missing; return {face_count, status}."""
        try:
            resp = self._client.describe_collection(CollectionId=self._collection_id)
            face_count = int(resp.get("FaceCount", 0) or 0)
            log.info("rekognition collection=%s exists face_count=%d", self._collection_id, face_count)
            return {"face_count": face_count, "status": "exists"}
        except self._client.exceptions.ResourceNotFoundException:
            self._client.create_collection(CollectionId=self._collection_id)
            log.info("rekognition collection=%s created", self._collection_id)
            return {"face_count": 0, "status": "created"}

    def describe_collection(self) -> dict[str, Any]:
        resp = self._client.describe_collection(CollectionId=self._collection_id)
        return {"face_count": int(resp.get("FaceCount", 0) or 0)}

    # ---------- selfie enrolment ----------

    def index_selfie(self, image_bytes: bytes, external_id: str) -> str:
        """Index exactly one face. Returns FaceId. Raises ValueError on rejection."""
        image_bytes = resize_if_oversized(image_bytes)
        # 1. Gate: DetectFaces first to enforce single-face selfies.
        det = self._client.detect_faces(Image={"Bytes": image_bytes}, Attributes=["DEFAULT"])
        det_faces = det.get("FaceDetails", []) or []
        if len(det_faces) == 0:
            raise ValueError("No face detected in selfie")
        if len(det_faces) > 1:
            raise ValueError(f"Multiple faces detected in selfie ({len(det_faces)}) — please upload a solo photo")

        # 2. Index — MaxFaces=1, quality filter on.
        s = get_settings()
        t0 = time.monotonic()
        resp = self._client.index_faces(
            CollectionId=self._collection_id,
            Image={"Bytes": image_bytes},
            ExternalImageId=external_id,
            MaxFaces=1,
            QualityFilter=s.REKOGNITION_QUALITY_FILTER,
            DetectionAttributes=["DEFAULT"],
        )
        face_records = resp.get("FaceRecords", []) or []
        if not face_records:
            unindexed = resp.get("UnindexedFaces", []) or []
            reasons = unindexed[0].get("Reasons", []) if unindexed else ["no_face_indexed"]
            raise ValueError(f"Selfie rejected by quality filter: {reasons}")

        face_id = face_records[0]["Face"]["FaceId"]
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        request_id = resp.get("ResponseMetadata", {}).get("RequestId")
        log.info(
            "index_selfie user_id=%s face_id=%s unindexed=%d request_id=%s ms=%d",
            external_id, face_id, len(resp.get("UnindexedFaces") or []), request_id, elapsed_ms,
        )
        return face_id

    # ---------- photo processing ----------

    def detect_and_match(self, image_bytes: bytes) -> DetectResult:
        """Detect faces in a photo and try to match each against the collection."""
        s = get_settings()
        result = DetectResult()
        try:
            image_bytes = resize_if_oversized(image_bytes)
            t0 = time.monotonic()
            det = self._client.detect_faces(Image={"Bytes": image_bytes}, Attributes=["DEFAULT"])
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            result.photo_error = f"DetectFaces failed: {code}"
            log.exception("detect_faces failed: %s", code)
            return result

        det_faces = det.get("FaceDetails", []) or []
        det_faces.sort(
            key=lambda f: f.get("BoundingBox", {}).get("Width", 0) * f.get("BoundingBox", {}).get("Height", 0),
            reverse=True,
        )
        det_faces = det_faces[:20]  # MaxFaces guard

        for idx, face in enumerate(det_faces):
            bbox = face.get("BoundingBox") or {}
            bbox_norm = _bbox_to_xywh_normalised(bbox)
            det_conf = float(face.get("Confidence", 0))

            item = FaceItem(bbox=bbox_norm, detection_confidence=det_conf)

            # Crop client-side
            crop_bytes, crop_err = crop_face(image_bytes, bbox_norm)
            if crop_bytes is None:
                item.error = crop_err
                result.faces.append(item)
                continue

            # Search against the collection
            try:
                search = self._client.search_faces_by_image(
                    CollectionId=self._collection_id,
                    Image={"Bytes": crop_bytes},
                    MaxFaces=1,
                    FaceMatchThreshold=s.REKOGNITION_FACE_MATCH_THRESHOLD,
                    QualityFilter=s.REKOGNITION_QUALITY_FILTER,
                )
            except self._client.exceptions.InvalidParameterException:
                # Face too small / no face found inside the crop → unmatched, no error
                result.faces.append(item)
                continue
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "Unknown")
                item.error = "throttled" if code in ("ThrottlingException", "ProvisionedThroughputExceededException") else code
                result.faces.append(item)
                continue

            matches = search.get("FaceMatches", []) or []
            if matches:
                m = matches[0]
                item.matched_face_id = m["Face"]["FaceId"]
                item.matched_external_id = m["Face"].get("ExternalImageId")
                item.match_similarity = float(m.get("Similarity", 0))
            result.faces.append(item)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        request_id = det.get("ResponseMetadata", {}).get("RequestId")
        log.info(
            "detect_and_match detected=%d matched=%d unmatched=%d errors=%d request_id=%s ms=%d",
            len(det_faces),
            sum(1 for f in result.faces if f.matched_external_id),
            sum(1 for f in result.faces if f.matched_external_id is None and not f.error),
            sum(1 for f in result.faces if f.error),
            request_id, elapsed_ms,
        )
        return result

    # ---------- unmatched-face index for cross-photo rematch ----------

    def index_manual_face(self, crop_bytes: bytes, user_id: str) -> str:
        """Index an admin-tagged face crop under a real user's ExternalImageId.

        Returns the new FaceId. Raises ValueError if the crop has no detectable
        face or multiple faces.

        QualityFilter is hardcoded to 'NONE' here — admin asserts ground truth,
        the DetectFaces gate already guaranteed exactly one face, and quality
        rejection on a tight crop is more confusing than useful.
        """
        # Gate: DetectFaces first to ensure exactly one face in the crop.
        det = self._client.detect_faces(Image={"Bytes": crop_bytes}, Attributes=["DEFAULT"])
        det_faces = det.get("FaceDetails", []) or []
        if len(det_faces) == 0:
            raise ValueError("No face detected in the selected region")
        if len(det_faces) > 1:
            raise ValueError(f"Selected region contains {len(det_faces)} faces — tighten the box")

        resp = self._client.index_faces(
            CollectionId=self._collection_id,
            Image={"Bytes": crop_bytes},
            ExternalImageId=user_id,
            MaxFaces=1,
            QualityFilter="NONE",
            DetectionAttributes=["DEFAULT"],
        )
        face_records = resp.get("FaceRecords", []) or []
        if not face_records:
            unindexed = resp.get("UnindexedFaces", []) or []
            reasons = unindexed[0].get("Reasons", []) if unindexed else ["no_face_indexed"]
            raise ValueError(f"Crop rejected by quality filter: {reasons}")

        face_id = face_records[0]["Face"]["FaceId"]
        request_id = resp.get("ResponseMetadata", {}).get("RequestId")
        log.info(
            "index_manual_face user_id=%s face_id=%s request_id=%s",
            user_id, face_id, request_id,
        )
        return face_id

    def list_user_face_ids(self, user_id: str) -> list[str]:
        """All FaceIds in the collection whose ExternalImageId == user_id."""
        out: list[str] = []
        token = None
        while True:
            kwargs: dict[str, Any] = {"CollectionId": self._collection_id, "MaxResults": 4096}
            if token:
                kwargs["NextToken"] = token
            resp = self._client.list_faces(**kwargs)
            for f in resp.get("Faces", []) or []:
                if f.get("ExternalImageId") == user_id:
                    out.append(f["FaceId"])
            token = resp.get("NextToken")
            if not token:
                break
        return out

    def index_unmatched(self, crop_bytes: bytes, photoface_id: str) -> str | None:
        """Index an unmatched face crop so future enrolments can link it.

        ExternalImageId = ``unmatched:<photoface_id>``. Returns None if Rekognition's
        quality filter rejects the crop.
        """
        s = get_settings()
        try:
            resp = self._client.index_faces(
                CollectionId=self._collection_id,
                Image={"Bytes": crop_bytes},
                ExternalImageId=f"unmatched:{photoface_id}",
                MaxFaces=1,
                QualityFilter=s.REKOGNITION_QUALITY_FILTER,
                DetectionAttributes=["DEFAULT"],
            )
        except ClientError as e:
            log.warning("index_unmatched failed photoface_id=%s err=%s", photoface_id, e)
            return None
        face_records = resp.get("FaceRecords", []) or []
        if not face_records:
            return None
        return face_records[0]["Face"]["FaceId"]

    def search_unmatched_for_user(
        self, user_face_id: str, caller_user_id: str | None = None
    ) -> list[tuple[str, str, float]]:
        """Search the collection for unmatched faces that match a user's face.

        Returns ``[(face_id, external_image_id, similarity), ...]`` filtered to
        entries whose ExternalImageId starts with ``unmatched:``.

        If ``caller_user_id`` is given, log a WARNING when any match has
        ``ExternalImageId`` set to a DIFFERENT real user UUID (cross-user
        collision / look-alike signal).
        """
        s = get_settings()
        try:
            resp = self._client.search_faces(
                CollectionId=self._collection_id,
                FaceId=user_face_id,
                MaxFaces=4096,
                FaceMatchThreshold=s.REKOGNITION_MANUAL_PROPAGATION_THRESHOLD,
            )
        except ClientError as e:
            log.exception("search_unmatched_for_user failed: %s", e)
            return []
        out: list[tuple[str, str, float]] = []
        cross_user_match_count = 0
        for m in resp.get("FaceMatches", []) or []:
            face = m.get("Face", {})
            eid = face.get("ExternalImageId") or ""
            sim = float(m.get("Similarity", 0))
            if eid.startswith("unmatched:"):
                out.append((face["FaceId"], eid, sim))
            elif caller_user_id and eid and eid != caller_user_id:
                cross_user_match_count += 1
                log.warning(
                    "cross-user face collision: caller=%s matched_eid=%s similarity=%.1f face_id=%s",
                    caller_user_id, eid, sim, face.get("FaceId"),
                )
        log.info(
            "search_unmatched_for_user user_face_id=%s total=%d unmatched=%d cross_user=%d",
            user_face_id, len(resp.get("FaceMatches") or []), len(out), cross_user_match_count,
        )
        return out

    # ---------- deletion ----------

    def delete_face(self, face_id: str) -> None:
        try:
            self._client.delete_faces(CollectionId=self._collection_id, FaceIds=[face_id])
            log.info("delete_face face_id=%s status=ok", face_id)
        except self._client.exceptions.ResourceNotFoundException:
            log.info("delete_face face_id=%s status=not_found", face_id)
        except ClientError as e:
            log.exception("delete_face face_id=%s err=%s", face_id, e)
            raise

    def bulk_delete_faces(self, face_ids: list[str]) -> None:
        if not face_ids:
            return
        # AWS allows up to 4096 per call. Chunk if more.
        for i in range(0, len(face_ids), 4096):
            chunk = face_ids[i : i + 4096]
            try:
                self._client.delete_faces(CollectionId=self._collection_id, FaceIds=chunk)
            except ClientError as e:
                log.warning("bulk_delete_faces partial fail: %s", e)
        log.info("bulk_delete_faces count=%d status=ok", len(face_ids))

    # ---------- migration / admin ----------

    def list_all_faces(self) -> dict[str, str]:
        """Page through ListFaces; return {external_image_id: face_id} for entries that have an EID."""
        out: dict[str, str] = {}
        token = None
        while True:
            kwargs: dict[str, Any] = {"CollectionId": self._collection_id, "MaxResults": 4096}
            if token:
                kwargs["NextToken"] = token
            resp = self._client.list_faces(**kwargs)
            for f in resp.get("Faces", []) or []:
                eid = f.get("ExternalImageId")
                if eid:
                    out[eid] = f["FaceId"]
            token = resp.get("NextToken")
            if not token:
                break
        return out


@lru_cache(maxsize=1)
def get_engine() -> AwsFaceEngine:
    s = get_settings()
    if not (s.AWS_ACCESS_KEY_ID and s.AWS_SECRET_ACCESS_KEY):
        raise RuntimeError(
            "AWS credentials missing — set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY in .env"
        )
    cfg = Config(
        region_name=s.AWS_REGION,
        retries={"mode": "adaptive", "max_attempts": 5},
    )
    client = boto3.client(
        "rekognition",
        aws_access_key_id=s.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=s.AWS_SECRET_ACCESS_KEY,
        config=cfg,
    )
    # Account-identity sanity check (only if AWS_ACCOUNT_ID is configured).
    if s.AWS_ACCOUNT_ID:
        sts = boto3.client(
            "sts",
            aws_access_key_id=s.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=s.AWS_SECRET_ACCESS_KEY,
            region_name=s.AWS_REGION,
        )
        actual = sts.get_caller_identity().get("Account")
        if actual != s.AWS_ACCOUNT_ID:
            raise RuntimeError(
                f"AWS account mismatch: expected {s.AWS_ACCOUNT_ID}, got {actual}"
            )
    return AwsFaceEngine(client, s.REKOGNITION_COLLECTION_ID)
