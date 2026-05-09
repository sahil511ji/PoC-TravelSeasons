from __future__ import annotations

import json
import math
from dataclasses import dataclass

from ..config import get_settings
from ..models import User


@dataclass
class Match:
    user: User
    similarity: float


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0:
        return -1.0
    return dot / denom


def best_match(embedding: list[float], users: list[User]) -> Match | None:
    threshold = get_settings().FACE_MATCH_THRESHOLD
    best: Match | None = None
    for u in users:
        if not u.face_embedding:
            continue
        try:
            ref = json.loads(u.face_embedding)
        except json.JSONDecodeError:
            continue
        sim = cosine(embedding, ref)
        if sim < threshold:
            continue
        if best is None or sim > best.similarity:
            best = Match(user=u, similarity=sim)
    return best
