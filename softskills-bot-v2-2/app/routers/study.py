# app/routers/study.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import uuid
from app.core.study_token import make_token, parse_token
from app.core.settings import settings

router = APIRouter(prefix="", tags=["study"])

class MintResponse(BaseModel):
    participant_id: str
    token: str
    round2_link: str

@router.get("/study/mint", response_model=MintResponse)
def study_mint(user_id: str = Query(..., alias="userId")):
    """
    Παίρνει το user_id του Γύρου-1 (αυτό που ήδη χρησιμοποιεί το UI)
    και εκδίδει token για να ξαναχρησιμοποιηθεί στον Γύρο-2.
    """
    try:
        pid = uuid.UUID(user_id) if len(user_id) == 36 else uuid.UUID(user_id)
    except Exception:
        # αν δεν είναι UUID, “αναγκαστική” χαρτογράφηση: hash → uuid
        pid = uuid.uuid5(uuid.NAMESPACE_URL, user_id)

    tok = make_token(pid)
    # link όπου θα πατήσει ο φοιτητής για Γύρο-2 (βάλε το δικό σου URL)
    base = getattr(settings, "PUBLIC_UI_BASE", "").rstrip("/") or "https://example.com"
    link = f"{base}/?token={tok}&round=2"
    return MintResponse(participant_id=str(pid), token=tok, round2_link=link)

class ResolveResponse(BaseModel):
    ok: bool
    participant_id: str | None = None

@router.get("/study/resolve", response_model=ResolveResponse)
def study_resolve(token: str = Query(...)):
    pid = parse_token(token)
    return ResolveResponse(ok=bool(pid), participant_id=(str(pid) if pid else None))
