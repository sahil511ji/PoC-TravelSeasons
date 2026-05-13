"""Face engine — AWS Rekognition (replaces facenet-pytorch)."""
from .aws import (
    AwsFaceEngine,
    DetectResult,
    FaceItem,
    crop_face,
    get_engine,
    resize_if_oversized,
)

__all__ = [
    "AwsFaceEngine",
    "DetectResult",
    "FaceItem",
    "crop_face",
    "get_engine",
    "resize_if_oversized",
]
