from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from typing import Optional, List
from io import BytesIO
from openpyxl import Workbook

from app.core.db import get_session
from app.models.db_models import Interaction

router = APIRouter(prefix="/export", tags=["export"])

@router.get("/human-xlsx")
def export_human_xlsx(
    category: Optional[str] = Query(None),
    qtype: Optional[str] = Query(None),
    session: Session = Depends(get_session)
):
    wb = Workbook()
    ws = wb.active
    ws.title = "ratings"

    ws.append(["answer_id","category","qtype","question_id","user_id","text_raw","rater_id","score","notes"])

    stmt = select(Interaction)
    if category:
        stmt = stmt.where(Interaction.category == category)
    if qtype:
        stmt = stmt.where(Interaction.qtype == qtype)
    stmt = stmt.order_by(Interaction.created_at.asc())
    rows: List[Interaction] = session.exec(stmt).all()

    for it in rows:
        ws.append([it.answer_id, it.category, it.qtype, it.question_id, it.user_id or "", it.text_raw or "", "", "", ""])

    if not rows:
        # add an example line to clarify format
        ws.append(["ans_example","Communication","open","comm_open1","user123","Παράδειγμα κειμένου","r1","4.0","προαιρετικές σημειώσεις"])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=human_ratings_template.xlsx"})
