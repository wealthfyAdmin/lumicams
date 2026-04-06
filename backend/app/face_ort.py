"""
Face detection + embedding without the `insightface` Python package.
Uses OpenCV FaceDetectorYN (YuNet ONNX) + ArcFace MBF ONNX (w600k_mbf) via onnxruntime.

Needed on Python 3.13 / Windows where `pip install insightface` often fails (no wheel, MSVC build).
"""

from __future__ import annotations

import logging
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MODEL_ROOT = Path(os.getenv("FACE_ORT_MODEL_DIR", "")).resolve() if os.getenv("FACE_ORT_MODEL_DIR") else (
    Path(__file__).resolve().parent.parent / "models" / "face_ort"
)
_YUNET_URLS = [
    os.getenv("FACE_YUNET_ONNX_URL", "").strip(),
    "https://huggingface.co/opencv/opencv_zoo/resolve/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
]
_YUNET_URLS = [u for u in _YUNET_URLS if u]
_ARC_ZIP_URL = os.getenv(
    "FACE_ARC_ONNX_ZIP_URL",
    "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",
)

# ArcFace 112x112 reference landmarks (same convention as InsightFace).
_ARC_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7289, 92.2041],
    ],
    dtype=np.float32,
)

_ORT_APP: Optional["OnnxFaceAnalysis"] = None


def _download(url: str, dest: Path, timeout: int = 120, min_bytes: int = 0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    logger.info("Downloading face model: %s", url)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AegisEye/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    sz = tmp.stat().st_size
    if min_bytes and sz < min_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Download too small ({sz} B); likely not a model file.")
    tmp.replace(dest)


def _ensure_yunet(model_dir: Path) -> Path:
    target = model_dir / "face_detection_yunet_2023mar.onnx"
    if target.is_file() and target.stat().st_size > 50_000:
        return target
    last_err = None
    for url in _YUNET_URLS:
        try:
            _download(url, target, timeout=180, min_bytes=50_000)
            return target
        except Exception as exc:
            last_err = exc
            target.unlink(missing_ok=True)
            logger.warning("YuNet download failed (%s): %s", url, exc)
    raise RuntimeError(f"Could not download YuNet ONNX. Last error: {last_err}")


def _ensure_arcface(model_dir: Path) -> Path:
    env_path = os.getenv("FACE_ARC_ONNX_PATH", "").strip()
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"FACE_ARC_ONNX_PATH not found: {p}")
        return p
    target = model_dir / "w600k_mbf.onnx"
    if target.is_file():
        return target
    model_dir.mkdir(parents=True, exist_ok=True)
    zip_path = model_dir / "buffalo_s_dl.zip"
    _download(_ARC_ZIP_URL, zip_path, timeout=600)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(model_dir)
    found = list(model_dir.rglob("w600k_mbf.onnx"))
    if not found:
        raise RuntimeError("buffalo_s zip does not contain w600k_mbf.onnx")
    shutil.move(str(found[0]), str(target))
    zip_path.unlink(missing_ok=True)
    for item in list(model_dir.iterdir()):
        if item.name == target.name:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        elif item == zip_path:
            continue
        else:
            try:
                item.unlink()
            except OSError:
                pass
    return target


class _FaceObj:
    __slots__ = ("embedding", "normed_embedding")

    def __init__(self, vec: np.ndarray) -> None:
        v = np.asarray(vec, dtype=np.float32).reshape(-1)
        self.embedding = v
        n = float(np.linalg.norm(v))
        self.normed_embedding = v / (n + 1e-9) if n > 1e-9 else v


class OnnxFaceAnalysis:
    """
    Drop-in subset of insightface.app.FaceAnalysis: .prepare(), .get(bgr_image) -> list of face objects
    with .normed_embedding and .embedding.
    """

    _aegis_engine = "onnxruntime"

    def __init__(self) -> None:
        import onnxruntime as ort

        self._det_path: Optional[Path] = None
        self._rec_path: Optional[Path] = None
        self._detector: Optional[cv2.FaceDetectorYN] = None
        self._cascade: Optional[cv2.CascadeClassifier] = None
        self._rec: Any = None
        self._rec_in: Optional[str] = None
        self._providers = ["CPUExecutionProvider"]
        self._ort = ort

    def prepare(self, ctx_id: int = -1, det_size: tuple[int, int] = (640, 640)) -> None:
        del ctx_id, det_size
        root = _MODEL_ROOT
        arc = _ensure_arcface(root)
        self._rec_path = arc
        so = self._ort.SessionOptions()
        self._rec = self._ort.InferenceSession(str(arc), providers=self._providers, sess_options=so)
        ins = self._rec.get_inputs()
        if not ins:
            raise RuntimeError("ArcFace ONNX has no inputs")
        self._rec_in = ins[0].name

        try:
            yunet = _ensure_yunet(root)
            self._det_path = yunet
            self._detector = cv2.FaceDetectorYN.create(
                str(yunet),
                "",
                (320, 320),
                score_threshold=float(os.getenv("FACE_ORT_YUNET_SCORE", "0.55")),
                nms_threshold=0.3,
                top_k=5000,
            )
            logger.info("OnnxFaceAnalysis ready (YuNet + %s).", arc.name)
        except Exception as exc:
            self._detector = None
            path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            self._cascade = cv2.CascadeClassifier(path)
            if self._cascade.empty():
                raise RuntimeError("No YuNet and no Haar cascade") from exc
            logger.warning("YuNet unavailable (%s); using OpenCV Haar frontal face (lower quality).", exc)

    def get(self, img_bgr: np.ndarray) -> List[_FaceObj]:
        if self._rec is None:
            raise RuntimeError("Call prepare() first")
        if img_bgr is None or img_bgr.size == 0:
            return []
        out: List[_FaceObj] = []

        if self._detector is not None:
            h, w = img_bgr.shape[:2]
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(img_bgr)
            if faces is None or len(faces) == 0:
                return []
            for row in faces:
                if row.shape[0] < 15:
                    continue
                bw, bh = float(row[2]), float(row[3])
                if bw < 16 or bh < 16:
                    continue
                score = float(row[14])
                if score < float(os.getenv("FACE_ORT_MIN_DET_SCORE", "0.55")):
                    continue
                lm = row[4:14].reshape(5, 2).astype(np.float32)
                warped = _warp_arcface(img_bgr, lm)
                if warped is None:
                    continue
                out.append(self._embed_112(warped))
            return out

        if self._cascade is not None:
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            rects = self._cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(48, 48),
            )
            for (x, y, rw, rh) in rects:
                crop = img_bgr[int(y) : int(y + rh), int(x) : int(x + rw)]
                if crop.size == 0:
                    continue
                warped = cv2.resize(crop, (112, 112), interpolation=cv2.INTER_AREA)
                out.append(self._embed_112(warped))
            return out

        return []

    def _embed_112(self, warped112_bgr: np.ndarray) -> _FaceObj:
        inp = _arcface_input(warped112_bgr)
        raw = self._rec.run(None, {self._rec_in: inp})[0]
        emb = np.asarray(raw, dtype=np.float32).reshape(-1)
        return _FaceObj(emb)


def _warp_arcface(img_bgr: np.ndarray, landmarks: np.ndarray) -> Optional[np.ndarray]:
    tform, _ = cv2.estimateAffinePartial2D(landmarks, _ARC_DST)
    if tform is None:
        return None
    return cv2.warpAffine(img_bgr, tform[:2], (112, 112), borderValue=(0, 0, 0))


def _arcface_input(face112_bgr: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(face112_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = (rgb - 127.5) / 128.0
    return np.transpose(rgb, (2, 0, 1))[np.newaxis, ...]


def get_shared_ort_face_app() -> OnnxFaceAnalysis:
    global _ORT_APP
    if _ORT_APP is None:
        _ORT_APP = OnnxFaceAnalysis()
        _ORT_APP.prepare(ctx_id=-1, det_size=(640, 640))
    return _ORT_APP


_SHARED_FACE_APP: Optional[Any] = None


def get_shared_face_app() -> Optional[Any]:
    """
    Single process-wide face backend (InsightFace if installed, else YuNet+ArcFace ORT).
    Shared by all camera workers and the enroll API.
    """
    global _SHARED_FACE_APP
    if _SHARED_FACE_APP is not None:
        return _SHARED_FACE_APP
    if os.getenv("FACE_FORCE_ONNX", "").strip().lower() in ("1", "true", "yes"):
        try:
            _SHARED_FACE_APP = get_shared_ort_face_app()
            return _SHARED_FACE_APP
        except Exception as exc:
            logger.warning("FACE_FORCE_ONNX set but ORT face init failed: %s", exc)
            return None
    try:
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        app._aegis_engine = "insightface"  # type: ignore[attr-defined]
        _SHARED_FACE_APP = app
        return _SHARED_FACE_APP
    except Exception as exc:
        logger.info("InsightFace unavailable (%s); using ONNXRuntime face backend.", exc)
    try:
        _SHARED_FACE_APP = get_shared_ort_face_app()
        return _SHARED_FACE_APP
    except Exception as exc:
        logger.warning("ONNXRuntime face backend failed: %s", exc)
        return None
