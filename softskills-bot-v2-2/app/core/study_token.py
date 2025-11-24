# app/core/study_token.py
from __future__ import annotations
import hmac, hashlib, base64, uuid
from typing import Optional
from app.core.settings import settings

_SECRET = (getattr(settings, "STUDY_SECRET", "") or "").encode()

def _require_secret():
    if not _SECRET:
        raise RuntimeError("STUDY_SECRET not configured")

def make_token(participant_id: uuid.UUID) -> str:
    _require_secret()
    pid = participant_id.bytes  # 16 bytes
    sig = hmac.new(_SECRET, pid, hashlib.sha256).digest()[:6]  # 6 bytes
    raw = pid + sig  # 22 bytes
    b32 = base64.b32encode(raw).decode().rstrip("=")  # A-Z2-7
    
    return "-".join(b32[i:i+4] for i in range(0, len(b32), 4))

def parse_token(token: str) -> Optional[uuid.UUID]:
    if not token:
        return None
    _require_secret()
    try:
        b32 = token.replace("-", "").upper()
        pad = "=" * ((8 - (len(b32) % 8)) % 8)
        raw = base64.b32decode(b32 + pad)
        pid, sig = raw[:16], raw[16:]
        check = hmac.new(_SECRET, pid, hashlib.sha256).digest()[:len(sig)]
        if hmac.compare_digest(sig, check):
            return uuid.UUID(bytes=pid)
    except Exception:
        return None
    return None
