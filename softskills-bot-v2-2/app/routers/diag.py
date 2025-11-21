# app/routers/diag.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body
from sqlmodel import Session
from sqlalchemy import text
from typing import Optional, Dict, Any

from app.core.db import get_session

router = APIRouter(prefix="/_diag", tags=["diag"])

@router.get("/ping")
def diag_ping():
    return {"ok": True, "scope": "/_diag"}

@router.post("/clear-all")
def clear_all(
    payload: Dict[str, Any] = Body(...),
    session: Session = Depends(get_session),
    x_admin_token: Optional[str] = Header(None),
):
    EXPECTED = "softskills-admin"   # ASCII μόνο
    if not x_admin_token or x_admin_token != EXPECTED:
        raise HTTPException(status_code=401, detail="unauthorized")


    confirm = payload.get("confirm")

    if confirm not in (None, "DELETE"):
        raise HTTPException(status_code=400, detail="missing confirm token")

    before = session.execute(text("""
      SELECT
        (SELECT COUNT(*) FROM human_ratings) AS human_ratings,
        (SELECT COUNT(*) FROM final_scores)  AS final_scores,
        (SELECT COUNT(*) FROM llm_scores)    AS llm_scores,
        (SELECT COUNT(*) FROM answers)       AS answers,
        (SELECT COUNT(*) FROM interaction)   AS interaction
    """)).mappings().first()
    before = dict(before or {})

    session.execute(text("TRUNCATE TABLE human_ratings RESTART IDENTITY CASCADE"))
    session.execute(text("TRUNCATE TABLE final_scores RESTART IDENTITY CASCADE"))
    session.execute(text("TRUNCATE TABLE llm_scores RESTART IDENTITY CASCADE"))
    session.execute(text("TRUNCATE TABLE answers RESTART IDENTITY CASCADE"))
    session.execute(text("TRUNCATE TABLE interaction RESTART IDENTITY CASCADE"))
    session.commit()

    after = session.execute(text("""
      SELECT
        (SELECT COUNT(*) FROM human_ratings) AS human_ratings,
        (SELECT COUNT(*) FROM final_scores)  AS final_scores,
        (SELECT COUNT(*) FROM llm_scores)    AS llm_scores,
        (SELECT COUNT(*) FROM answers)       AS answers,
        (SELECT COUNT(*) FROM interaction)   AS interaction
    """)).mappings().first()
    after = dict(after or {})

    return {"ok": True, "before": before, "after": after}
