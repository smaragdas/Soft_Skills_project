from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from typing import Optional, Dict, List
from io import StringIO
import csv
from datetime import datetime

from app.core.db import get_session
from app.models.db_models import Interaction, AutoRating, HumanRating

router = APIRouter(prefix="/export", tags=["export"])

def _filter_stmt(category: Optional[str], qtype: Optional[str]):
    stmt = select(Interaction)
    if category:
        stmt = stmt.where(Interaction.category == category)
    if qtype:
        stmt = stmt.where(Interaction.qtype == qtype)
    stmt = stmt.order_by(Interaction.created_at.asc())
    return stmt

@router.get("/all-csv")
def export_all_csv(
    category: Optional[str] = Query(None),
    qtype: Optional[str] = Query(None, pattern="^(open|mc)$"),
    fmt: str = Query("long", pattern="^(long|wide)$"),
    session: Session = Depends(get_session)
):
    interactions: List[Interaction] = session.exec(_filter_stmt(category, qtype)).all()
    ans_ids = [i.answer_id for i in interactions]

    autos = session.exec(select(AutoRating).where(AutoRating.answer_id.in_(ans_ids))).all() if ans_ids else []
    auto_by_ans: Dict[str, float] = {a.answer_id: a.score for a in autos}

    humans = session.exec(select(HumanRating).where(HumanRating.answer_id.in_(ans_ids))).all() if ans_ids else []
    by_ans_humans: Dict[str, List[HumanRating]] = {}
    for h in humans:
        by_ans_humans.setdefault(h.answer_id, []).append(h)

    now = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

    if fmt == "long":
        buf = StringIO(newline="")
        writer = csv.writer(buf)
        writer.writerow(["answer_id","created_at","category","qtype","question_id","user_id","text_raw","auto_score","rater_id","human_score","human_notes"])
        if not interactions:
            writer.writerow(["","","","","","","","","","",""])
        else:
            for it in interactions:
                auto_score = auto_by_ans.get(it.answer_id, "")
                humans_list = by_ans_humans.get(it.answer_id, [])
                if not humans_list:
                    writer.writerow([it.answer_id, it.created_at, it.category, it.qtype, it.question_id, it.user_id or "", (it.text_raw or "").replace("\n"," ").strip(), auto_score, "", "", ""])
                else:
                    for hr in humans_list:
                        writer.writerow([it.answer_id, it.created_at, it.category, it.qtype, it.question_id, it.user_id or "", (it.text_raw or "").replace("\n"," ").strip(), auto_score, hr.rater_id, hr.score, (hr.notes or "" ).replace("\n"," ").strip()])
        buf.seek(0)
        filename = f"export_long_{now}.csv"
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename={filename}"})
    else:
        raters = sorted({h.rater_id for h in humans})
        headers = ["answer_id","created_at","category","qtype","question_id","user_id","text_raw","auto_score"] + [f"r_{rid}" for rid in raters]
        buf = StringIO(newline="")
        writer = csv.writer(buf)
        writer.writerow(headers)
        for it in interactions:
            row = [it.answer_id, it.created_at, it.category, it.qtype, it.question_id, it.user_id or "", (it.text_raw or "").replace("\n"," ").strip(), auto_by_ans.get(it.answer_id, "")]
            ratings_map = {h.rater_id: h.score for h in by_ans_humans.get(it.answer_id, [])}
            for rid in raters:
                row.append(ratings_map.get(rid, ""))
            writer.writerow(row)
        if not interactions:
            writer.writerow(["","","","","","","",""] + [""]*len(raters))
        buf.seek(0)
        filename = f"export_wide_{now}.csv"
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename={filename}"})
