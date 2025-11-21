# app/routers/report_simple.py
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from typing import List, Dict, Any

from app.core.db import get_session
from app.models.evaluation import Evaluation


router = APIRouter(prefix="/report", tags=["report"])


@router.get("/evaluation-user/{user_id}/summary")
def user_summary(user_id: str, session: Session = Depends(get_session)):
    # ORM/SQLModel query (ασφαλές για SQLAlchemy 2.x)
    evs: List[Evaluation] = session.exec(
        select(Evaluation).where(Evaluation.user_id == user_id)
    ).all()

    if not evs:
        return {"ok": True, "user_id": user_id, "items": []}

    # map -> flat summary items
    items: List[Dict[str, Any]] = []
    for e in evs:
        res: Dict[str, Any] = e.result or {}
        items.append({
            "id": e.id,
            "question_id": e.question_id,
            "category": e.category or res.get("skill"),
            "score": res.get("score"),
            "label": res.get("label"),
            "created_at": getattr(e, "created_at", None),
        })

    # κράτα το πιο πρόσφατο ανά category
    latest: Dict[str, Dict[str, Any]] = {}
    for it in items:
        cat = it.get("category") or "unknown"
        prev = latest.get(cat)
        if prev is None:
            latest[cat] = it
        else:
            ca, cb = prev.get("created_at"), it.get("created_at")
            if cb and (not ca or cb > ca):
                latest[cat] = it

    return {"ok": True, "user_id": user_id, "items": list(latest.values())}
