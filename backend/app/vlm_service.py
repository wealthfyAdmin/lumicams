"""
Vision-language verification for alerts.

Supports OpenAI-compatible vision APIs and local Ollama (OpenAI-compatible
`/v1/chat/completions` on `OLLAMA_BASE_URL`, e.g. llava).

Runs in a background thread after an alert is persisted. Updates Alert row with
vlm_status / vlm_explanation / vlm_checked_at.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from app.database import SessionLocal
from app.models import Alert, VlmVerificationStatus

logger = logging.getLogger(__name__)

VLM_ENABLED = os.getenv("VLM_ENABLED", "true").strip().lower() in ("1", "true", "yes")


def _min_confidence_threshold() -> float:
    """0–1 scale; env may use 0–100 (e.g. VLM_MIN_CONFIDENCE=70 → 0.7). 0 = disabled."""
    raw = os.getenv("VLM_MIN_CONFIDENCE", "0").strip()
    if not raw:
        return 0.0
    try:
        v = float(raw)
        if v > 1.0:
            return max(0.0, min(1.0, v / 100.0))
        return max(0.0, min(1.0, v))
    except ValueError:
        return 0.0


def _vlm_endpoint_config() -> Tuple[str, str, str, str]:
    """
    Returns (api_url, model, authorization_bearer_or_empty, backend_label).
    Ollama: set OLLAMA_BASE_URL → uses .../v1/chat/completions; API key optional (dummy ok).
    Cloud OpenAI: leave OLLAMA_BASE_URL unset; set OPENAI_API_KEY + OPENAI_API_URL / VLM_MODEL.
    """
    ollama_base = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
    if ollama_base:
        model = (
            os.getenv("OLLAMA_VLM_MODEL", "").strip()
            or os.getenv("VLM_MODEL", "").strip()
            or "llava"
        )
        url = f"{ollama_base}/v1/chat/completions"
        key = os.getenv("OLLAMA_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip() or "ollama"
        return url, model, key, "ollama"
    url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions").strip()
    model = os.getenv("VLM_MODEL", "gpt-4o-mini").strip()
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return url, model, key, "openai"


def _snapshot_abs_path(snapshot_path: Optional[str]) -> Optional[Path]:
    if not snapshot_path:
        return None
    p = Path(snapshot_path.replace("\\", "/"))
    if p.is_file():
        return p
    root = Path(os.getenv("SNAPSHOT_DIR", "snapshots"))
    rel = p
    if p.parts and p.parts[0] == root.name:
        rel = Path(*p.parts[1:]) if len(p.parts) > 1 else Path(p.name)
    # e.g. reid/cam1_t1.jpg → snapshots/reid/cam1_t1.jpg
    cand = root / rel
    if cand.is_file():
        return cand
    cand = root / p.name
    if cand.is_file():
        return cand
    return None


def _build_prompt(alert_type: str) -> str:
    t = (alert_type or "").lower()
    if "fire" in t or "smoke" in t:
        return (
            "You are a safety vision assistant. Look at this surveillance image carefully. "
            "Is there REAL fire, smoke, or open flame in the physical scene in front of the camera? "
            "Reject if the flame is only on a phone/laptop/TV screen, a poster, LED display, or reflection. "
            "Reject if it is only warm-colored clothing or sunlight. "
            'Reply with JSON only: {"verdict":"confirmed"|"rejected"|"uncertain",'
            '"confidence":0.0-1.0,"reason":"one short sentence"}'
        )
    if "ppe" in t:
        return (
            "Workplace safety: Is there at least one clearly visible PERSON (whole or partial body) in the image? "
            "If there is no real person, verdict must be rejected. "
            "If there is a person, does the image support a real PPE violation (missing helmet/vest/etc.) "
            "and not a mannequin, poster, or distant blur? "
            'Reply with JSON only: {"verdict":"confirmed"|"rejected"|"uncertain",'
            '"confidence":0.0-1.0,"reason":"one short sentence"}'
        )
    if "fall" in t:
        return (
            "Does this image show a person who has likely FALLEN or collapsed (lying on ground, not supporting weight), "
            "as opposed to crouching, kneeling to tie shoes, bending, yoga, or sitting on a chair? "
            'Reply with JSON only: {"verdict":"confirmed"|"rejected"|"uncertain",'
            '"confidence":0.0-1.0,"reason":"one short sentence"}'
        )
    if "crowd" in t:
        return (
            "Crowd/occupancy: In this image, are the figures that drive the alert mostly REAL HUMANS "
            "(not chairs, bags, mannequins, posters, or statues)? "
            "If the scene is ambiguous or mostly non-person objects, prefer rejected or uncertain. "
            'Reply with JSON only: {"verdict":"confirmed"|"rejected"|"uncertain",'
            '"confidence":0.0-1.0,"reason":"one short sentence"}'
        )
    if "weapon" in t:
        return (
            "Security: Does this image show what appears to be a REAL weapon (firearm, knife, machete, etc.) "
            "in a real environment? Reject toys, tools clearly not weapons (e.g. wrench), "
            "or objects too blurry/small to tell. Police/safety context. "
            'Reply with JSON only: {"verdict":"confirmed"|"rejected"|"uncertain",'
            '"confidence":0.0-1.0,"reason":"one short sentence"}'
        )
    return (
        "Does this surveillance image justify a security/safety alert of the type implied? "
        'Reply with JSON only: {"verdict":"confirmed"|"rejected"|"uncertain",'
        '"confidence":0.0-1.0,"reason":"one short sentence"}'
    )


def _call_openai_vision(image_path: Path, prompt: str) -> tuple[str, str]:
    import base64

    api_url, model, api_key, _backend = _vlm_endpoint_config()
    raw = image_path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 300,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        api_url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    text = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    return text, ""


def _parse_verdict(raw: str) -> tuple[VlmVerificationStatus, str, Optional[float]]:
    """Returns (status, explanation, confidence 0–1 or None)."""
    raw = raw.strip()
    conf: Optional[float] = None
    try:
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
        obj = json.loads(raw)
        v = str(obj.get("verdict", "")).lower()
        reason = str(obj.get("reason", raw))[:2000]
        c = obj.get("confidence")
        if c is not None:
            try:
                conf = float(c)
                if conf > 1.0:
                    conf = min(1.0, conf / 100.0)
            except (TypeError, ValueError):
                conf = None
        if v == "confirmed":
            return VlmVerificationStatus.confirmed, reason, conf
        if v == "rejected":
            return VlmVerificationStatus.rejected, reason, conf
        if v == "uncertain":
            return VlmVerificationStatus.rejected, f"[uncertain] {reason}", conf
        return VlmVerificationStatus.rejected, f"[unparseable verdict] {reason}", conf
    except Exception:
        low = raw.lower()
        if "reject" in low or "false" in low:
            return VlmVerificationStatus.rejected, raw[:2000], None
        return VlmVerificationStatus.confirmed, raw[:2000], None


def _apply_confidence_gate(
    status: VlmVerificationStatus,
    explanation: str,
    confidence: Optional[float],
) -> tuple[VlmVerificationStatus, str]:
    """When VLM_MIN_CONFIDENCE>0, only keep *confirmed* if model confidence meets the floor."""
    floor = _min_confidence_threshold()
    if floor <= 0 or status != VlmVerificationStatus.confirmed:
        return status, explanation
    if confidence is None:
        return (
            VlmVerificationStatus.rejected,
            f"{explanation} [VLM: need confidence ≥ {floor:.0%}; no score in JSON]".strip()[:2000],
        )
    if confidence < floor:
        return (
            VlmVerificationStatus.rejected,
            f"{explanation} [VLM: {confidence:.0%} < required {floor:.0%}]".strip()[:2000],
        )
    return status, explanation


def verify_alert_async(alert_id: int, alert_type: str, snapshot_path: Optional[str]) -> None:
    def _run() -> None:
        if not VLM_ENABLED:
            _set_vlm(alert_id, VlmVerificationStatus.skipped, None)
            return
        _url, _model, _key, backend = _vlm_endpoint_config()
        if backend == "openai" and not os.getenv("OPENAI_API_KEY", "").strip():
            _set_vlm(alert_id, VlmVerificationStatus.skipped, "VLM skipped: OPENAI_API_KEY not set")
            return
        img = _snapshot_abs_path(snapshot_path)
        if not img or not img.is_file():
            _set_vlm(alert_id, VlmVerificationStatus.error, "Snapshot file not found for VLM")
            return
        try:
            prompt = _build_prompt(alert_type)
            raw, _ = _call_openai_vision(img, prompt)
            status, expl, conf = _parse_verdict(raw)
            status, expl = _apply_confidence_gate(status, expl, conf)
            _set_vlm(alert_id, status, expl)
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")[:500]
            logger.warning("VLM HTTP error: %s", err)
            _set_vlm(alert_id, VlmVerificationStatus.error, err)
        except Exception as exc:
            logger.warning("VLM failed: %s", exc)
            _set_vlm(alert_id, VlmVerificationStatus.error, str(exc)[:500])

    threading.Thread(target=_run, daemon=True).start()


def _set_vlm(alert_id: int, status: VlmVerificationStatus, explanation: Optional[str]) -> None:
    db = SessionLocal()
    try:
        row = db.query(Alert).filter(Alert.id == alert_id).first()
        if row:
            row.vlm_status = status
            row.vlm_explanation = explanation
            row.vlm_checked_at = datetime.utcnow()
            db.commit()
    except Exception as exc:
        logger.debug("VLM persist failed: %s", exc)
        db.rollback()
    finally:
        db.close()
