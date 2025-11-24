# app/routers/rater_simple.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.core.db import get_session

# prefix = "/rater", γιατί το UI ζητά /api/softskills/rater/...
router = APIRouter(prefix="/rater", tags=["rater"])

@router.get("/items")
def list_items(
    rater_id: str = Query(..., description="π.χ. teacher01"),
    session: Session = Depends(get_session),
):
    """
    Γυρνάει λίστα απαντήσεων για βαθμολόγηση.
    Ταιριάζει με το schema σου: answers.prompt, answers.text, llm_scores.llm_score.
    """
    sql = text("""
        SELECT
          a.answer_id,
          a.user_id,
          a.question_id,
          a.category,
          a.qtype,
          a.prompt AS prompt,      -- στο schema σου υπάρχει 'prompt'
          a.text   AS answer,      -- στο schema σου η απάντηση είναι 'text' (όχι 'answer')
          a.created_at,
          l.llm_score AS "initialScore",
          (
            SELECT rr.score_rater
            FROM rater_ratings rr
            WHERE rr.answer_id = a.answer_id
              AND rr.rater_id  = :rater_id
            LIMIT 1
          ) AS rater_score
        FROM answers a
        LEFT JOIN llm_scores l USING (answer_id)
        WHERE 1=1
        ORDER BY a.created_at DESC
        LIMIT 500
    """)
    rows = session.execute(sql, {"rater_id": rater_id}).mappings().all()
    return {"ok": True, "items": [dict(r) for r in rows]}

@router.post("/rate")
def upsert_rating(payload: dict, session: Session = Depends(get_session)):
    """
    Body:
      {
        "answer_id": "<uuid>",
        "rater_id": "teacher01",
        "score": 8.0
      }
    Κάνει UPSERT στον πίνακα rater_ratings.
    """
    try:
        answer_id = payload.get("answer_id")
        rater_id  = payload.get("rater_id")
        score     = payload.get("score")

        if not answer_id or not rater_id or score is None:
            raise HTTPException(status_code=400, detail="Missing answer_id / rater_id / score")

        sql = text("""
            INSERT INTO rater_ratings (answer_id, rater_id, score_rater)
            VALUES (:answer_id::uuid, :rater_id, :score::numeric)
            ON CONFLICT (answer_id, rater_id)
            DO UPDATE SET score_rater = EXCLUDED.score_rater,
                          updated_at  = now()
            RETURNING rating_id, answer_id, rater_id, score_rater, updated_at;
        """)
        row = session.execute(sql, {
            "answer_id": answer_id,
            "rater_id":  rater_id,
            "score":     score,
        }).mappings().first()
        session.commit()
        return {"ok": True, "rating": dict(row) if row else None}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"rater/rate error: {e}")

@router.get("/ping")
def ping():
    return {"ok": True, "router": "rater"}
