# app/routers/quiz_complete.py
from __future__ import annotations
import os
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.db import get_session

# Ταιριάζει με το BASE που χρησιμοποιείς: .../api/softskills
# Άρα τα endpoints θα είναι /api/softskills/quiz/...
router = APIRouter(prefix="/quiz", tags=["quiz"])

MATERIALS_BUCKET = os.getenv("MATERIALS_BUCKET", "softskills-quiz-ihu")

CATEGORIES = ["leadership", "communication", "teamwork", "problem_solving"]
LEVELS     = ["low", "mid", "high"]


@router.get("/hello")
def quiz_hello():
    return {"ok": True, "router": "quiz_complete"}


def level_from_score(s: float) -> str:
    try:
        s = float(s)
    except Exception:
        s = 0.0
    if s < 40:  return "low"
    if s < 70:  return "mid"
    return "high"


def _head_exists(s3, bucket: str, key: str) -> bool:
    if not s3 or not bucket or not key:
        return False
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except NoCredentialsError:
        # 🚫 Δεν έχουμε AWS credentials → θεωρούμε ότι δεν υπάρχει
        return False
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        # για οτιδήποτε άλλο απλά log και False
        print(f"S3 head_object error: {e}")
        return False
    

def _get_s3_client():
    try:
        # Δημιουργεί S3 client μόνο αν υπάρχουν credentials
        session = boto3.session.Session()
        creds = session.get_credentials()
        if creds is None:
            return None
        return session.client("s3")
    except Exception:
        return None


def _pick_material_key(cat: str, level: str, phase: str, attempt: int) -> str:
    s3 = _get_s3_client()
    if not s3:
        # 🚫 Δεν υπάρχει S3 client (άρα δεν υπάρχουν credentials)
        return None

    phase_norm = "post" if str(phase).strip().upper() == "POST" else "pre"
    candidates = [
        f"materials/{cat}/{phase_norm}/attempt{attempt}/{level}.pdf",
        f"materials/{cat}/{phase_norm}/{level}.pdf",
        f"materials/{cat}/{level}.pdf",
    ]
    for key in candidates:
        if _head_exists(s3, MATERIALS_BUCKET, key):
            return key
    return None


def presign_url(bucket: str, key: str, expires_sec: int = 24 * 3600) -> str:
    s3 = boto3.client("s3")  # region από το Lambda runtime
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_sec,
    )


def _extract_phase_attempt(payload: Dict[str, Any]) -> tuple[str, int]:
    """
    Δέχεται phase/attempt είτε στο root (phase, attempt) είτε σε metadata.phase/metadata.attempt.
    Επιστρέφει (phase_norm, attempt_int) με ασφαλή defaults.
    """
    meta = payload.get("metadata") or {}
    phase_val: Optional[str] = payload.get("phase") or meta.get("phase") or "PRE"
    attempt_val: Optional[int] = payload.get("attempt") or meta.get("attempt") or 1

    phase_norm = "POST" if str(phase_val).strip().upper() == "POST" else "PRE"
    try:
        attempt_int = int(attempt_val)
        attempt_int = 2 if attempt_int == 2 else 1
    except Exception:
        attempt_int = 1

    return phase_norm, attempt_int


@router.post("/complete")
def quiz_complete(payload: Dict[str, Any], session: Session = Depends(get_session)):
    """
    Υποστηριζόμενα σχήματα αιτήματος:

    1) Απλό (υπάρχον):
    {
      "userId": "<id>",
      "phase": "PRE" | "POST",
      "attempt": 1 | 2,
      "results": {
        "leadership": number,
        "communication": number,
        "teamwork": number,
        "problem_solving": number
      }
    }

    2) Εναλλακτικό (π.χ. από νεότερο client):
    {
      "userId": "<id>",
      "metadata": { "phase": "POST", "attempt": 2, ... },
      "results": { ... }
    }
    """
    user_id = (payload.get("userId") or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="missing userId")

    phase_norm, attempt_int = _extract_phase_attempt(payload)

    results = payload.get("results") or {}
    s_lead = results.get("leadership", 0)
    s_comm = results.get("communication", 0)
    s_team = results.get("teamwork", 0)
    s_prob = results.get("problem_solving", 0)

    lvl_lead = level_from_score(s_lead)
    lvl_comm = level_from_score(s_comm)
    lvl_team = level_from_score(s_team)
    lvl_prob = level_from_score(s_prob)

    # ΜΟΝΟ attempt=1 μοιράζει υλικό
    deliver_materials = (attempt_int == 1)

    materials: list[dict[str, Any]] = []
    if deliver_materials:
        for cat, lvl in [
            ("leadership",      lvl_lead),
            ("communication",   lvl_comm),
            ("teamwork",        lvl_team),
            ("problem_solving", lvl_prob),
        ]:
            key = _pick_material_key(cat, lvl, phase_norm, attempt_int)
            url = None

            if key:
                try:
                    url = presign_url(MATERIALS_BUCKET, key)
                except NoCredentialsError:
                    # 🚫 Δεν έχουμε AWS credentials → δεν δίνουμε URL
                    url = None

            if url:
                materials.append({"category": cat, "level": lvl, "url": url})

    print(
        f"[quiz_complete] user={user_id} phase={phase_norm} attempt={attempt_int} "
        f"deliver_materials={deliver_materials} materials_count={len(materials)}"
    )

    return {
        "ok": True,
        "sessionEcho": {
            "userId": user_id,
            "phase": phase_norm,
            "attempt": attempt_int,
            "materials_delivered": deliver_materials,
        },
        "scores": {
            "leadership": s_lead,
            "communication": s_comm,
            "teamwork": s_team,
            "problem_solving": s_prob,
        },
        "levels": {
            "leadership": lvl_lead,
            "communication": lvl_comm,
            "teamwork": lvl_team,
            "problem_solving": lvl_prob,
        },
        "materials": materials,  # [] όταν attempt=2
    }

