from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import text
from typing import Dict, List, Optional, Tuple, Any
from statistics import mean
from datetime import datetime, timedelta

from app.core.db import get_session
from app.models.db_models import Interaction, AutoRating, HumanRating

router = APIRouter(prefix="/report", tags=["report"])

# ---------- Helper ----------
def _safe_mean(values: List[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(mean(vals), 3) if vals else None


# ==============================================================
# 🔹 PART A — Existing Reports (Interactions / Ratings)
# ==============================================================

@router.get("/user")
def report_user(
    user_id: str = Query(..., description="User (participant) id"),
    session: Session = Depends(get_session)
):
    # Interactions by user
    inters = session.exec(
        select(Interaction.answer_id, Interaction.category).where(Interaction.user_id == user_id)
    ).all()
    if not inters:
        raise HTTPException(status_code=404, detail=f"No interactions found for user_id={user_id}")

    # Map: answer_id -> category
    cat_by_answer = {aid: cat for (aid, cat) in inters}

    # Pull ALL auto ratings for these answers
    answer_ids = list(cat_by_answer.keys())
    autos = session.exec(
        select(AutoRating.answer_id, AutoRating.score).where(AutoRating.answer_id.in_(answer_ids))
    ).all()
    auto_by_answer: Dict[str, List[float]] = {}
    for aid, sc in autos:
        auto_by_answer.setdefault(aid, []).append(float(sc))

    # Pull ALL human ratings for these answers
    humans = session.exec(
        select(HumanRating.answer_id, HumanRating.rater_id, HumanRating.score)
        .where(HumanRating.answer_id.in_(answer_ids))
    ).all()
    human_by_answer: Dict[str, List[Tuple[str, float]]] = {}
    for aid, rid, sc in humans:
        human_by_answer.setdefault(aid, []).append((rid, float(sc)))

    # Aggregate per category
    per_category: Dict[str, Dict] = {}
    for aid, cat in cat_by_answer.items():
        per_category.setdefault(cat, {
            "n_answers": 0,
            "auto_scores": [],
            "human_scores": [],
            "by_rater": {},
            "within_0_5": 0,
        })
        agg = per_category[cat]
        agg["n_answers"] += 1

        a_mean = _safe_mean(auto_by_answer.get(aid, []))
        h_vals = [sc for (_rid, sc) in human_by_answer.get(aid, [])]
        h_mean = _safe_mean(h_vals)

        if a_mean is not None:
            agg["auto_scores"].append(a_mean)
        if h_mean is not None:
            agg["human_scores"].append(h_mean)

        for rid, sc in human_by_answer.get(aid, []):
            agg["by_rater"].setdefault(rid, []).append(sc)

        if a_mean is not None and h_mean is not None and abs(h_mean - a_mean) <= 0.5:
            agg["within_0_5"] += 1

    # finalize stats
    out = {"user_id": user_id, "categories": {}}
    for cat, agg in per_category.items():
        auto_mean = _safe_mean(agg["auto_scores"])
        human_mean = _safe_mean(agg["human_scores"])
        by_rater_mean = {rid: _safe_mean(scores) for rid, scores in agg["by_rater"].items()}
        agree_rate = round(agg["within_0_5"] / agg["n_answers"], 3) if agg["n_answers"] > 0 else None

        out["categories"][cat] = {
            "n_answers": agg["n_answers"],
            "auto_mean": auto_mean,
            "human_mean": human_mean,
            "delta_human_minus_auto": round(human_mean - auto_mean, 3)
            if (auto_mean is not None and human_mean is not None) else None,
            "by_rater_mean": by_rater_mean,
            "agreement_within_0_5": agree_rate
        }

    return out


@router.get("/overview")
def report_overview(session: Session = Depends(get_session)):
    users = session.exec(select(Interaction.user_id).where(Interaction.user_id.is_not(None))).all()
    user_ids = sorted({u for u in users if u})

    overview = []
    for uid in user_ids:
        cnt = session.exec(select(Interaction).where(Interaction.user_id == uid)).all()
        overview.append({"user_id": uid, "n_interactions": len(cnt)})
    return {"users": overview}


# ==============================================================
# 🔹 PART B — New Reports (Evaluation Table Analytics)
# ==============================================================

def _days_ago(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=max(0, days))


@router.get("/evaluation-overview")
def evaluation_overview(
    days: int = Query(7, ge=1, le=365),
    session: Session = Depends(get_session),
):
    since = _days_ago(days)

    total = session.exec("""
        SELECT COUNT(*)::int
        FROM evaluation
        WHERE created_at >= :since
    """, params={"since": since}).one()[0]

    per_category = session.exec("""
        SELECT category, COUNT(*)::int
        FROM evaluation
        WHERE created_at >= :since
        GROUP BY category
        ORDER BY COUNT(*) DESC
    """, params={"since": since}).all()
    per_category = [{"category": r[0], "count": r[1]} for r in per_category]

    per_label = session.exec("""
        SELECT COALESCE(result->>'label','') AS label, COUNT(*)::int
        FROM evaluation
        WHERE created_at >= :since
        GROUP BY label
        ORDER BY COUNT(*) DESC
    """, params={"since": since}).all()
    per_label = [{"label": r[0], "count": r[1]} for r in per_label]

    return {
        "since": since.isoformat() + "Z",
        "days": days,
        "total": total,
        "by_category": per_category,
        "by_label": per_label,
    }


@router.get("/evaluation-user/{user_id}/summary")
def evaluation_user_summary(
    user_id: str,
    days: int = Query(90, ge=1, le=365),
    session: Session = Depends(get_session),
):
    since = _days_ago(days)

    total = session.exec("""
        SELECT COUNT(*)::int
        FROM evaluation
        WHERE user_id = :uid AND created_at >= :since
    """, params={"uid": user_id, "since": since}).one()[0]

    if total == 0:
        return {
            "user_id": user_id,
            "since": since.isoformat() + "Z",
            "days": days,
            "total": 0,
            "avg_score": None,
            "avg_dimensions": None,
            "last": None,
        }

    avg_score = session.exec("""
        SELECT AVG( (result->>'score')::float )
        FROM evaluation
        WHERE user_id = :uid AND created_at >= :since
    """, params={"uid": user_id, "since": since}).one()[0]

    dims = session.exec("""
        SELECT
          AVG( (result->'dimensions'->'Knowledge_Decision'->>'score')::float ),
          AVG( (result->'dimensions'->'Content_Structure'->>'score')::float ),
          AVG( (result->'dimensions'->'Delivery_Presence'->>'score')::float )
        FROM evaluation
        WHERE user_id = :uid AND created_at >= :since
    """, params={"uid": user_id, "since": since}).one()

    avg_dims = {
        "Knowledge_Decision": round(dims[0], 2) if dims[0] is not None else None,
        "Content_Structure":  round(dims[1], 2) if dims[1] is not None else None,
        "Delivery_Presence":  round(dims[2], 2) if dims[2] is not None else None,
    }

    last_row = session.exec("""
        SELECT id, result->>'label', category, created_at
        FROM evaluation
        WHERE user_id = :uid AND created_at >= :since
        ORDER BY created_at DESC
        LIMIT 1
    """, params={"uid": user_id, "since": since}).one()

    last = {
        "id": last_row[0],
        "label": last_row[1],
        "category": last_row[2],
        "created_at": last_row[3].isoformat() + "Z",
    }

    return {
        "user_id": user_id,
        "since": since.isoformat() + "Z",
        "days": days,
        "total": total,
        "avg_score": round(avg_score, 2) if avg_score is not None else None,
        "avg_dimensions": avg_dims,
        "last": last,
    }


@router.get("/evaluation-user/{user_id}/timeline")
def evaluation_user_timeline(
    user_id: str,
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
):
    rows = session.exec("""
        SELECT id,
               created_at,
               (result->>'score')::float AS score,
               result->>'label' AS label,
               category
        FROM evaluation
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT :lim
    """, params={"uid": user_id, "lim": limit}).all()

    data = [{
        "id": r[0],
        "created_at": r[1].isoformat() + "Z",
        "score": r[2],
        "label": r[3],
        "category": r[4],
    } for r in rows]

    return {"user_id": user_id, "limit": limit, "items": data}
