# app/routers/rater.py
from __future__ import annotations

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query, Header, HTTPException
from sqlalchemy import text
from sqlmodel import Session
from app.core.db import get_session

router = APIRouter(prefix="/rater", tags=["rater"])

# ----------------------------- Helpers -----------------------------
def _row_to_item(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "answerId": row.get("answer_id"),
        "questionId": row.get("question_id"),
        "userId": row.get("user_id"),
        "qtype": row.get("qtype"),
        "category": row.get("category"),
        "prompt": row.get("prompt") or "",
        "answer": (row.get("answer") or "").strip(),
        "initialScore": row.get("initial_score"),
        "initialNotes": row.get("initial_notes"),
        "createdAt": row.get("created_at"),
    }

def _table_exists(session: Session, name: str) -> bool:
    res = session.exec(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n").bindparams(n=name)
    ).first()
    return bool(res)

def _columns(session: Session, table: str) -> set[str]:
    rows = session.exec(text(f"PRAGMA table_info({table})")).all()
    cols: set[str] = set()
    for r in rows:
        try:
            cols.add(r[1])
        except Exception:
            pass
    return cols

def _coalesce_cols(prefix: str, cols: List[str]) -> List[str]:
    return [f"{prefix}.{c}" for c in cols]

def _coalesce_sql(parts: List[str]) -> str:
    if not parts:
        return "''"
    return "COALESCE(" + ", ".join(parts + ["''"]) + ")"

# ----------------------------- Endpoints -----------------------------
@router.get("/items")
def get_items(
    rater_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    qtype: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
):
    where = ["1=1"]
    params: Dict[str, Any] = {"lim": limit}
    if category:
        where.append("i.category = :category")
        params["category"] = category
    if qtype:
        where.append("i.qtype = :qtype")
        params["qtype"] = qtype

    icols = _columns(session, "interaction")
    has_payload = "payload" in icols

    # ---------------- Prompt για OPEN μόνο ----------------
    # Προσπάθησε να πάρεις εκφώνηση από πίνακα ερωτήσεων αν υπάρχει· αλλιώς από i.question_text· αλλιώς κενό.
    q_table = next((t for t in ("questions", "question", "quiz_questions") if _table_exists(session, t)), None)
    has_qtext_col = "question_text" in icols
    if q_table:
        prompt_open_expr = "COALESCE(q.text, '')"
        join_q = f"LEFT JOIN {q_table} q ON q.id = i.question_id"
    else:
        prompt_open_expr = "COALESCE(i.question_text, '')" if has_qtext_col else "''"
        join_q = ""

    # ---------------- OPEN: εντοπισμός απάντησης ----------------
    open_parts: List[str] = []
    open_parts += _coalesce_cols("i", [c for c in ("answer_text", "text_raw", "user_answer", "response_text", "free_text", "answer") if c in icols])
    if has_payload:
        open_parts += [
            "json_extract(i.payload, '$.answer')",
            "json_extract(i.payload, '$.open_text')",
            "json_extract(i.payload, '$.response')",
            "json_extract(i.payload, '$.text')",
        ]
    # έσχατα fallbacks
    open_parts += _coalesce_cols("i", [c for c in ("text_raw", "text") if c in icols])
    open_expr = _coalesce_sql(open_parts)

    # ---------------- MC: δείξε ΜΟΝΟ το questionId (άρα prompt='', answer='') ----------------
    mc_answer_expr = "''"
    mc_prompt_expr = "''"

    # ---------------- Generic (αν προκύψει άλλο qtype, κράτα το απλό) ----------------
    generic_answer_expr = "''"
    generic_prompt_expr = "''"

    # ---------------- CASE expressions ----------------
    prompt_expr = f"""
CASE
  WHEN i.qtype = 'open' THEN {prompt_open_expr}
  WHEN i.qtype = 'mc'   THEN {mc_prompt_expr}
  ELSE {generic_prompt_expr}
END AS prompt
"""

    answer_expr = f"""
CASE
  WHEN i.qtype = 'open' THEN {open_expr}
  WHEN i.qtype = 'mc'   THEN {mc_answer_expr}
  ELSE {generic_answer_expr}
END AS answer
"""

    sql = f"""
SELECT
  i.answer_id,
  i.question_id,
  i.user_id,
  i.qtype,
  i.category,
  {prompt_expr},
  {answer_expr},
  a.score    AS initial_score,
  a.feedback AS initial_notes,
  i.created_at AS created_at
FROM interaction i
{join_q}
LEFT JOIN autorating a ON a.answer_id = i.answer_id
WHERE {" AND ".join(where)}
ORDER BY i.created_at DESC
LIMIT :lim
"""
    rows = session.exec(text(sql).bindparams(**params)).mappings().all()
    return [_row_to_item(dict(r)) for r in rows]

# --- Admin: reset interactions (κουμπί "Delete ALL answers") ---
@router.post("/reset-interactions")
def reset_interactions(
    session: Session = Depends(get_session),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Token")

    def count(tbl: str) -> int:
        try:
            row = session.exec(text(f"SELECT COUNT(*) FROM {tbl}")).first()
            return int(row[0]) if row is not None else 0
        except Exception:
            return 0

    before = {"autorating": count("autorating"), "interaction": count("interaction")}
    try:
        session.exec(text("DELETE FROM autorating"))
    except Exception:
        pass
    try:
        session.exec(text("DELETE FROM interaction"))
    except Exception:
        pass
    session.commit()

    return {"ok": True, "cleared": before}
