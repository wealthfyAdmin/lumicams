"""Lightweight appearance embedding from a BGR crop (HSV histogram) for cross-camera matching."""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np


def embedding_from_bgr_crop(crop_bgr: np.ndarray) -> Tuple[List[float], Optional[float]]:
    """
    Returns (normalized histogram vector, dominant hue 0–180 or None).
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return [], None
    try:
        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    except Exception:
        return [], None
    h, w = hsv.shape[:2]
    if h < 2 or w < 2:
        return [], None
    # 16 bins for H, 8 each for S,V — concat and L2-normalize
    hist_h = cv2.calcHist([hsv], [0], None, [16], [0, 180])
    hist_s = cv2.calcHist([hsv], [1], None, [8], [0, 256])
    hist_v = cv2.calcHist([hsv], [2], None, [8], [0, 256])
    vec = np.concatenate([hist_h.flatten(), hist_s.flatten(), hist_v.flatten()]).astype(np.float64)
    n = np.linalg.norm(vec)
    if n > 1e-9:
        vec = vec / n
    dom = float(np.argmax(hist_h)) * (180.0 / 16.0) if hist_h.size else None
    return vec.tolist(), dom


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))
