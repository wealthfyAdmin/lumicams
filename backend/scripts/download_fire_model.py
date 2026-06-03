#!/usr/bin/env python3
"""
Download a fire/smoke YOLO checkpoint into backend/models/fire.pt.

Usage (from backend/):
  python scripts/download_fire_model.py

Override URL:
  FIRE_MODEL_DOWNLOAD_URL=https://... python scripts/download_fire_model.py
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
# Prefer dual fire+smoke weights when available; smoke-only model needs FIRE_CONF_THRESHOLD≈0.12.
_FALLBACK_URLS = (
    "https://huggingface.co/AKURA36/yolov8-fire-smoke-detection/resolve/main/best.pt",
    "https://huggingface.co/TommyNgx/YOLOv10-Fire-and-Smoke-Detection/resolve/main/best.pt",
    "https://huggingface.co/kittendev/YOLOv8m-smoke-detection/resolve/main/best.pt",
)
_TARGET = _BACKEND_ROOT / "models" / "fire.pt"
_MIN_BYTES = 1_000_000


def main() -> int:
    env_url = os.getenv("FIRE_MODEL_DOWNLOAD_URL", "").strip()
    urls = [env_url] if env_url else list(_FALLBACK_URLS)
    _TARGET.parent.mkdir(parents=True, exist_ok=True)
    tmp = _TARGET.with_suffix(".pt.part")
    last_err: Exception | None = None
    for url in urls:
        print(f"Trying:\n  {url}\n-> {_TARGET}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Lumicams/1.0)"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as out:
                shutil.copyfileobj(resp, out)
            last_err = None
            break
        except Exception as exc:
            last_err = exc
            print(f"  failed: {exc}")
            tmp.unlink(missing_ok=True)
    if last_err is not None:
        print(f"All download URLs failed.", file=sys.stderr)
        return 1
    size = tmp.stat().st_size
    if size < _MIN_BYTES:
        print(f"Download too small ({size} bytes); check URL.", file=sys.stderr)
        tmp.unlink(missing_ok=True)
        return 1
    tmp.replace(_TARGET)
    print(f"Saved {_TARGET} ({size // 1024} KB)")
    print("Set in .env: YOLO_FIRE_MODEL=models/fire.pt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
