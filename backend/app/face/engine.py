"""Face detection + embedding using facenet-pytorch.

We use MTCNN for detection (returns boxes + probs) and InceptionResnetV1
pretrained on VGGFace2 for 512-dim L2-normalised embeddings.

Models are downloaded lazily on first call (~120 MB total).
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image, ImageOps

from ..config import get_settings

log = logging.getLogger(__name__)


@dataclass
class DetectedFace:
    bbox: list[float]      # [x, y, w, h] in original image pixels
    prob: float            # detection confidence (0-1)
    embedding: list[float] # 512 floats, L2-normalised


class _FaceEngine:
    def __init__(self) -> None:
        self.device = torch.device("cpu")
        self._mtcnn = None
        self._encoder = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        # Imported here so module import is cheap; first call downloads models.
        from facenet_pytorch import MTCNN, InceptionResnetV1

        log.info("Loading face models (first run downloads ~120 MB)...")
        self._mtcnn = MTCNN(
            image_size=160,
            margin=20,
            min_face_size=40,
            keep_all=True,
            post_process=True,
            device=self.device,
        )
        # Get the classification head off; we want embeddings, not class scores.
        self._encoder = (
            InceptionResnetV1(pretrained=get_settings().FACE_MODEL or "vggface2")
            .eval()
            .to(self.device)
        )
        self._loaded = True
        log.info("Face models loaded.")

    @torch.inference_mode()
    def detect_faces(self, image_bytes: bytes, det_threshold: float = 0.9) -> list[DetectedFace]:
        self._load()
        img = _open_rgb(image_bytes)
        boxes, probs = self._mtcnn.detect(img)
        if boxes is None:
            return []

        # Get aligned face crops (160x160 tensors, normalised by MTCNN).
        aligned = self._mtcnn(img)  # tensor [N, 3, 160, 160] or None
        if aligned is None:
            return []
        if aligned.dim() == 3:
            aligned = aligned.unsqueeze(0)

        embeddings = self._encoder(aligned.to(self.device))
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1).cpu().numpy()

        results: list[DetectedFace] = []
        for i, box in enumerate(boxes):
            prob = float(probs[i]) if probs[i] is not None else 0.0
            if prob < det_threshold:
                continue
            x1, y1, x2, y2 = [float(v) for v in box]
            results.append(
                DetectedFace(
                    bbox=[x1, y1, x2 - x1, y2 - y1],
                    prob=prob,
                    embedding=embeddings[i].tolist(),
                )
            )
        return results

    def embed_single_face(self, image_bytes: bytes) -> list[float]:
        """For selfies: returns the embedding of the largest detected face."""
        faces = self.detect_faces(image_bytes, det_threshold=0.85)
        if not faces:
            raise ValueError("No face detected in selfie")
        # pick the largest box
        faces.sort(key=lambda f: f.bbox[2] * f.bbox[3], reverse=True)
        return faces[0].embedding


def _open_rgb(image_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


_engine: _FaceEngine | None = None


def get_engine() -> _FaceEngine:
    global _engine
    if _engine is None:
        _engine = _FaceEngine()
        _engine._load()
    return _engine
