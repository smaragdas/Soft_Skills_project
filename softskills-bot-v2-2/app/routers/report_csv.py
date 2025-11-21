from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from sqlalchemy import text
from typing import Dict, List, Optional, Tuple, Set
from statistics import mean
import io, csv

from app.core.db import get_session
from app.models.db_models import Interaction, AutoRating, HumanRating

router = APIRouter(prefix="/report", tags=["report-csv"])

def _safe_mean(values: List[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(mean(vals), 3) if vals else None

def _aggregate_user(session: Session, user_id: str):
    # Interactions by user
    inters = session.exec(
        select(Interaction.answer_id, Interaction.category).where(Interaction.user_id == user_id)
    ).all()
    if not inters:
        raise HTTPException(status_code=404, detail=f"No interactions found for user_id={user_id}")

    cat_by_answer = {aid: cat for (aid, cat) in inters}
    answer_ids = list(cat_by_answer.keys())

    autos = session.exec(
        select(AutoRating.answer_id, AutoRating.score).where(AutoRating.answer_id.in_(answer_ids))
    ).all()
    auto_by_answer: Dict[str, List[float]] = {}
    for aid, sc in autos:
        auto_by_answer.setdefault(aid, []).append(float(sc))

    humans = session.exec(
        select(HumanRating.answer_id, HumanRating.rater_id, HumanRating.score)
        .where(HumanRating.answer_id.in_(answer_ids))
    ).all()
    human_by_answer: Dict[str, List[Tuple[str, float]]] = {}
    rater_ids: Set[str] = set()
    for aid, rid, sc in humans:
        rater_ids.add(rid)
        human_by_answer.setdefault(aid, []).append((rid, float(sc)))

    per_category: Dict[str, Dict] = {}
    for aid, cat in cat_by_answer.items():
        per_category.setdefault(cat, {
            "n_answers": 0,
            "auto_scores": [],
            "human_scores": [],
            "by_rater": {},   # rater_id -> list[score]
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

    # finalize
    result: Dict[str, Dict] = {}
    by_rater_means_by_cat: Dict[str, Dict[str, Optional[float]]] = {}
    for cat, agg in per_category.items():
        auto_mean = _safe_mean(agg["auto_scores"])
        human_mean = _safe_mean(agg["human_scores"])
        by_rater_mean = {rid: _safe_mean(scores) for rid, scores in agg["by_rater"].items()}
        agree_rate = None
        if agg["n_answers"] > 0:
            agree_rate = round(agg["within_0_5"] / agg["n_answers"], 3)

        result[cat] = {
            "n_answers": agg["n_answers"],
            "auto_mean": auto_mean,
            "human_mean": human_mean,
            "delta_human_minus_auto": round(human_mean - auto_mean, 3) if (auto_mean is not None and human_mean is not None) else None,
            "agreement_within_0_5": agree_rate,
        }
        by_rater_means_by_cat[cat] = by_rater_mean

    return result, sorted(rater_ids), by_rater_means_by_cat

@router.get("/user-csv")
def report_user_csv(user_id: str = Query(...), session: Session = Depends(get_session)):
    data, rater_ids, by_rater_means_by_cat = _aggregate_user(session, user_id)

    # Dynamic columns for raters
    base_cols = ["user_id", "category", "n_answers", "auto_mean", "human_mean", "delta_human_minus_auto", "agreement_within_0_5"]
    rater_cols = [f"rater_{rid}_mean" for rid in rater_ids]
    cols = base_cols + rater_cols

    # Prepare CSV in-memory with UTF-8 BOM for Excel
    output = io.StringIO()
    output.write("\ufeff")  # BOM
    writer = csv.DictWriter(output, fieldnames=cols)
    writer.writeheader()

    for cat, vals in data.items():
        row = {
            "user_id": user_id,
            "category": cat,
            "n_answers": vals.get("n_answers"),
            "auto_mean": vals.get("auto_mean"),
            "human_mean": vals.get("human_mean"),
            "delta_human_minus_auto": vals.get("delta_human_minus_auto"),
            "agreement_within_0_5": vals.get("agreement_within_0_5"),
        }
        by_rater = by_rater_means_by_cat.get(cat, {})
        for rid in rater_ids:
            row[f"rater_{rid}_mean"] = by_rater.get(rid)
        writer.writerow(row)

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"user_report_{user_id}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/overview-csv")
def report_overview_csv(session: Session = Depends(get_session)):
    # users observed
    users = session.exec(select(Interaction.user_id).where(Interaction.user_id.is_not(None))).all()
    user_ids = sorted({u for u in users if u})

    # counts
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.DictWriter(output, fieldnames=["user_id", "n_interactions", "n_human_ratings", "n_auto_ratings"])
    writer.writeheader()

    for uid in user_ids:
        inters = session.exec(select(Interaction.answer_id).where(Interaction.user_id == uid)).all()
        ans_ids = {aid for aid in inters}
        n_inter = len(ans_ids)

        n_human = session.exec(select(HumanRating).where(HumanRating.answer_id.in_(ans_ids))).all()
        n_auto = session.exec(select(AutoRating).where(AutoRating.answer_id.in_(ans_ids))).all()

        writer.writerow({
            "user_id": uid,
            "n_interactions": n_inter,
            "n_human_ratings": len(n_human),
            "n_auto_ratings": len(n_auto),
        })

    csv_bytes = output.getvalue().encode("utf-8")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=overview_users.csv"}
    )
