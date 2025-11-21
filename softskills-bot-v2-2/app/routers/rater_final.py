# app/routers/rater_final.py
from __future__ import annotations

from typing import List, Optional, Literal, Tuple, Dict, Any
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, Response, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session
from sqlalchemy import text

from app.core.db import get_session

router = APIRouter(prefix="/rater", tags=["rater"])

# ---------------------------------------------------------------------
# Schema helper: προσθέτει human_weighted αν λείπει από final_scores
# ---------------------------------------------------------------------
def ensure_schema(session: Session) -> Dict[str, bool]:
    flags = {"has_human_weighted": False}

    row = session.execute(
        text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='final_scores'
          AND column_name='human_weighted'
        """)
    ).first()

    if row:
        flags["has_human_weighted"] = True
        return flags

    try:
        session.execute(text("ALTER TABLE final_scores ADD COLUMN human_weighted NUMERIC"))
        session.commit()
        flags["has_human_weighted"] = True
    except Exception:
        session.rollback()
        row2 = session.execute(
            text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='final_scores'
              AND column_name='human_weighted'
            """)
        ).first()
        flags["has_human_weighted"] = bool(row2)

    return flags

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def clamp01(x: float | Decimal | None) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
    except Exception:
        return None
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f

def safe_mean(vals: List[Optional[float]]) -> Optional[float]:
    arr = [v for v in vals if v is not None]
    if not arr:
        return None
    return sum(arr) / len(arr)

# ---------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------
@router.get("/ping")
def ping():
    return {"ok": True, "scope": "/rater"}

# ---------------------------------------------------------------------
# Rate (single)
# ---------------------------------------------------------------------
class RatePayload(BaseModel):
    answerId: UUID
    raterId: Literal["teacher01", "teacher02"]
    score: float  # 0..10 ή 0..1

@router.post("/rate")
def rate_one(p: RatePayload, session: Session = Depends(get_session)):
    s = float(p.score)
    if s > 1.0:
        s = s / 10.0
    s = max(0.0, min(1.0, s))

    session.execute(
        text("""
          INSERT INTO human_ratings (answer_id, rater_id, score)
          VALUES (:aid, :rid, :s)
          ON CONFLICT (answer_id, rater_id)
          DO UPDATE SET score=EXCLUDED.score, rated_at=now()
        """),
        {"aid": str(p.answerId), "rid": p.raterId, "s": s}
    )
    session.commit()
    return {"ok": True, "answerId": str(p.answerId), "raterId": p.raterId, "stored_score_0_1": s}

# ---------------------------------------------------------------------
# Submit (batch) + recompute μόνο για αυτά που ήρθαν
# ---------------------------------------------------------------------
class Rating(BaseModel):
    answerId: UUID
    score: float  # 0..1

class SubmitPayload(BaseModel):
    raterId: Literal["teacher01", "teacher02"]
    ratings: List[Rating]

def _recompute_for(session: Session, answer_ids: List[str], human_weight: float = 0.6) -> int:
    """
    Υπολογίζει/ενημερώνει final_scores μόνο για τα συγκεκριμένα answers.
    """
    if not answer_ids:
        return 0

    rows = session.execute(text("""
        SELECT a.answer_id,
               (SELECT llm_score FROM llm_scores WHERE answer_id=a.answer_id) AS llm,
               (SELECT score FROM human_ratings WHERE answer_id=a.answer_id AND rater_id='teacher01') AS t1,
               (SELECT score FROM human_ratings WHERE answer_id=a.answer_id AND rater_id='teacher02') AS t2
        FROM answers a
        WHERE a.answer_id::text = ANY(:ids)
    """), {"ids": answer_ids}).mappings().all()

    flags = ensure_schema(session)
    has_hw = flags.get("has_human_weighted", False)

    updated = 0
    for r in rows:
        aid = str(r["answer_id"])
        llm = clamp01(r.get("llm"))
        t1  = clamp01(r.get("t1"))
        t2  = clamp01(r.get("t2"))

        cnt = (0 if t1 is None else 1) + (0 if t2 is None else 1)
        human_avg = None if cnt == 0 else ((0.0 if t1 is None else t1) + (0.0 if t2 is None else t2)) / cnt
        human_weighted = human_avg

        auto = 0.0 if llm is None else llm
        hw   = 0.0 if human_weighted is None else human_weighted
        final = (1.0 - human_weight) * auto + human_weight * hw

        if has_hw:
            sql = text("""
                INSERT INTO final_scores (
                    answer_id, user_id, question_id, category, qtype,
                    llm_score, teacher01, teacher02, human_avg, human_weighted, final_score, completed_at
                )
                SELECT a.answer_id, a.user_id, a.question_id, a.category, a.qtype,
                       :llm, :t1, :t2, :hav, :hw, :final, now()
                FROM answers a
                WHERE a.answer_id = :aid
                ON CONFLICT (answer_id) DO UPDATE
                  SET user_id        = EXCLUDED.user_id,
                      question_id    = EXCLUDED.question_id,
                      category       = EXCLUDED.category,
                      qtype          = EXCLUDED.qtype,
                      llm_score      = EXCLUDED.llm_score,
                      teacher01      = EXCLUDED.teacher01,
                      teacher02      = EXCLUDED.teacher02,
                      human_avg      = EXCLUDED.human_avg,
                      human_weighted = EXCLUDED.human_weighted,
                      final_score    = EXCLUDED.final_score,
                      completed_at   = now()
            """)
            params_up = {
                "llm": llm, "t1": t1, "t2": t2,
                "hav": human_avg, "hw": human_weighted,
                "final": final, "aid": aid
            }
        else:
            sql = text("""
                INSERT INTO final_scores (
                    answer_id, user_id, question_id, category, qtype,
                    llm_score, teacher01, teacher02, human_avg, final_score, completed_at
                )
                SELECT a.answer_id, a.user_id, a.question_id, a.category, a.qtype,
                       :llm, :t1, :t2, :hav, :final, now()
                FROM answers a
                WHERE a.answer_id = :aid
                ON CONFLICT (answer_id) DO UPDATE
                  SET user_id       = EXCLUDED.user_id,
                      question_id   = EXCLUDED.question_id,
                      category      = EXCLUDED.category,
                      qtype         = EXCLUDED.qtype,
                      llm_score     = EXCLUDED.llm_score,
                      teacher01     = EXCLUDED.teacher01,
                      teacher02     = EXCLUDED.teacher02,
                      human_avg     = EXCLUDED.human_avg,
                      final_score   = EXCLUDED.final_score,
                      completed_at  = now()
            """)
            params_up = {
                "llm": llm, "t1": t1, "t2": t2,
                "hav": human_avg, "final": final, "aid": aid
            }

        session.execute(sql, params_up)
        updated += 1

    return updated

@router.post("/submit")
def submit_ratings(p: SubmitPayload, session: Session = Depends(get_session)):
    for r in p.ratings:
        s = max(0.0, min(1.0, float(r.score)))
        session.execute(
            text("""
              INSERT INTO human_ratings (answer_id, rater_id, score)
              VALUES (:aid, :rid, :s)
              ON CONFLICT (answer_id, rater_id)
              DO UPDATE SET score=EXCLUDED.score, rated_at=now()
            """),
            {"aid": str(r.answerId), "rid": p.raterId, "s": s}
        )

    # recompute μόνο για τα συγκεκριμένα answers
    ids = [str(r.answerId) for r in p.ratings]
    _recompute_for(session, ids, human_weight=0.6)

    session.commit()
    return {"ok": True, "count": len(p.ratings)}

# ---------------------------------------------------------------------
# Items για Rater UI
# ---------------------------------------------------------------------
@router.get("/items")
def rater_items(
    rater_id: str,
    category: Optional[str] = None,
    qtype: Optional[str] = None,
    q: Optional[str] = None,
    has_llm: Optional[str] = None,
    attempt: Optional[int] = Query(None, ge=1, le=2),
    session: Session = Depends(get_session),
):
    sql = """
      SELECT a.answer_id, a.user_id, a.question_id, a.category, a.qtype,
             a.prompt, a.text AS answer, a.created_at,
             l.llm_score AS "initialScore",
             (SELECT score FROM human_ratings WHERE answer_id=a.answer_id AND rater_id='teacher01') AS teacher01,
             (SELECT score FROM human_ratings WHERE answer_id=a.answer_id AND rater_id='teacher02') AS teacher02
      FROM answers a
      LEFT JOIN llm_scores l USING(answer_id)
      WHERE 1=1
    """
    params: Dict[str, Any] = {}

    if category:
        sql += " AND a.category = :cat"; params["cat"] = category
    if qtype:
        sql += " AND a.qtype = :qt"; params["qt"] = qtype
    if q:
        sql += " AND (a.text ILIKE :q OR a.prompt ILIKE :q)"; params["q"] = f"%{q}%"
    if has_llm == "1":
        sql += " AND l.llm_score IS NOT NULL"
    if has_llm == "0":
        sql += " AND l.llm_score IS NULL"
    if attempt in (1, 2):
        sql += " AND EXISTS (SELECT 1 FROM interaction i WHERE i.answer_id=a.answer_id AND i.attempt_no=:att)"
        params["att"] = attempt

    sql += " ORDER BY a.created_at DESC LIMIT 500"

    rows = session.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]

# ---------------------------------------------------------------------
# Final-score για ένα answer
# ---------------------------------------------------------------------
@router.get("/final-score")
def final_score(answer_id: UUID, session: Session = Depends(get_session)):
    row = session.execute(text("""
      SELECT
        f.answer_id,
        f.llm_score,
        (f.teacher01 + f.teacher02)/2.0 AS human_score,
        f.final_score
      FROM final_scores f
      WHERE f.answer_id=:aid
    """), {"aid": str(answer_id)}).mappings().first()
    if not row:
        return {"answer_id": str(answer_id), "pending": True}
    return dict(row)

# ---------------------------------------------------------------------
# Metrics (QWK “light” demo)
# ---------------------------------------------------------------------
def _bin_score(x: Optional[float], bins: int) -> Optional[int]:
    if x is None:
        return None
    x = max(0.0, min(1.0, float(x)))
    b = int(x * bins)
    if b == bins:
        b = bins - 1
    return b

@router.get("/metrics")
def metrics(bins: int = Query(5, ge=2, le=10), session: Session = Depends(get_session)):
    rows = session.execute(text("""
        SELECT
          h1.answer_id,
          (SELECT score FROM human_ratings WHERE answer_id=h1.answer_id AND rater_id='teacher01') AS t1,
          (SELECT score FROM human_ratings WHERE answer_id=h1.answer_id AND rater_id='teacher02') AS t2
        FROM human_ratings h1
        GROUP BY h1.answer_id
    """)).mappings().all()

    gold: List[Tuple[int,int]] = []
    for r in rows:
        s1 = clamp01(r.get("t1"))
        s2 = clamp01(r.get("t2"))
        if s1 is None or s2 is None:
            continue
        b1 = _bin_score(s1, bins)
        b2 = _bin_score(s2, bins)
        if b1 is None or b2 is None:
            continue
        gold.append((b1, b2))

    n_common = len(gold)
    if n_common < 2:
        return {"ok": True, "n_common": n_common, "bins": bins, "qwk": None}

    K = bins
    O = [[0]*K for _ in range(K)]
    for a,b in gold:
        O[a][b] += 1

    W = [[((i-j)**2)/((K-1)**2) for j in range(K)] for i in range(K)]
    N = float(n_common)
    row_s = [sum(O[i][j] for j in range(K)) for i in range(K)]
    col_s = [sum(O[i][j] for i in range(K)) for j in range(K)]

    Po = 1.0 - sum(W[i][j]*O[i][j] for i in range(K) for j in range(K))/N
    Pe = 1.0 - sum(W[i][j]*(row_s[i]*col_s[j]/(N*N)) for i in range(K) for j in range(K))

    kappa = None
    den = (1.0 - Pe)
    if den != 0:
        kappa = (Po - Pe)/den

    return {"ok": True, "n_common": n_common, "bins": bins, "qwk": kappa}

# ---------------------------------------------------------------------
# Recompute-final (προαιρετικά μόνο για attempt)
# ---------------------------------------------------------------------
@router.post("/recompute-final")
def recompute_final(
    human_weight: float = Query(0.6, ge=0.0, le=1.0),
    bins: int = Query(5, ge=2, le=10),
    attempt: Optional[int] = Query(None, ge=1, le=2),
    session: Session = Depends(get_session),
):
    flags = ensure_schema(session)
    has_hw = flags.get("has_human_weighted", False)

    base_sql = """
        SELECT a.answer_id,
               (SELECT llm_score FROM llm_scores WHERE answer_id=a.answer_id) AS llm,
               (SELECT score FROM human_ratings WHERE answer_id=a.answer_id AND rater_id='teacher01') AS t1,
               (SELECT score FROM human_ratings WHERE answer_id=a.answer_id AND rater_id='teacher02') AS t2
        FROM answers a
    """
    params: Dict[str, Any] = {}
    if attempt in (1, 2):
        base_sql += " WHERE a.answer_id IN (SELECT answer_id FROM interaction WHERE attempt_no=:att)"
        params["att"] = attempt

    answers = session.execute(text(base_sql), params).mappings().all()

    updated = 0
    for r in answers:
        aid_val = r.get("answer_id")
        if not aid_val:
            continue

        aid = str(aid_val)
        llm = clamp01(r.get("llm"))
        t1  = clamp01(r.get("t1"))
        t2  = clamp01(r.get("t2"))

        cnt = (0 if t1 is None else 1) + (0 if t2 is None else 1)
        human_avg = None if cnt == 0 else ((0.0 if t1 is None else t1) + (0.0 if t2 is None else t2)) / cnt
        human_weighted = human_avg

        auto = 0.0 if llm is None else llm
        hw   = 0.0 if human_weighted is None else human_weighted
        final = (1.0 - human_weight) * auto + human_weight * hw

        if has_hw:
            sql = text("""
                INSERT INTO final_scores (
                    answer_id, user_id, question_id, category, qtype,
                    llm_score, teacher01, teacher02, human_avg, human_weighted, final_score, completed_at
                )
                SELECT
                    a.answer_id, a.user_id, a.question_id, a.category, a.qtype,
                    :llm, :t1, :t2, :hav, :hw, :final, now()
                FROM answers a
                WHERE a.answer_id = :aid
                ON CONFLICT (answer_id) DO UPDATE
                  SET user_id        = EXCLUDED.user_id,
                      question_id    = EXCLUDED.question_id,
                      category       = EXCLUDED.category,
                      qtype          = EXCLUDED.qtype,
                      llm_score      = EXCLUDED.llm_score,
                      teacher01      = EXCLUDED.teacher01,
                      teacher02      = EXCLUDED.teacher02,
                      human_avg      = EXCLUDED.human_avg,
                      human_weighted = EXCLUDED.human_weighted,
                      final_score    = EXCLUDED.final_score,
                      completed_at   = now()
            """)
            params_up = {"llm": llm, "t1": t1, "t2": t2, "hav": human_avg, "hw": human_weighted, "final": final, "aid": aid}
        else:
            sql = text("""
                INSERT INTO final_scores (
                    answer_id, user_id, question_id, category, qtype,
                    llm_score, teacher01, teacher02, human_avg, final_score, completed_at
                )
                SELECT
                    a.answer_id, a.user_id, a.question_id, a.category, a.qtype,
                    :llm, :t1, :t2, :hav, :final, now()
                FROM answers a
                WHERE a.answer_id = :aid
                ON CONFLICT (answer_id) DO UPDATE
                  SET user_id       = EXCLUDED.user_id,
                      question_id   = EXCLUDED.question_id,
                      category      = EXCLUDED.category,
                      qtype         = EXCLUDED.qtype,
                      llm_score     = EXCLUDED.llm_score,
                      teacher01     = EXCLUDED.teacher01,
                      teacher02     = EXCLUDED.teacher02,
                      human_avg     = EXCLUDED.human_avg,
                      final_score   = EXCLUDED.final_score,
                      completed_at  = now()
            """)
            params_up = {"llm": llm, "t1": t1, "t2": t2, "hav": human_avg, "final": final, "aid": aid}

        session.execute(sql, params_up)
        updated += 1

    session.commit()

    m = metrics(bins=bins, session=session)  # type: ignore
    return {
        "ok": True,
        "updated": updated,
        "qwk": m.get("qwk") if isinstance(m, dict) else None,
        "bins": bins,
        "human_weight": human_weight,
    }

# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------
def _summary_for_rater(session: Session, rid: Literal["teacher01","teacher02"]) -> Dict[str, Any]:
    row = session.execute(text("""
        WITH hh AS (
          SELECT answer_id, score, rated_at
          FROM human_ratings
          WHERE rater_id = :rid
        )
        SELECT
          COUNT(a.answer_id)                                AS total,
          COUNT(a.answer_id) FILTER (WHERE hh.score IS NULL) AS pending,
          AVG(l.llm_score)                                 AS avg_llm,
          AVG(hh.score)                                    AS avg_human,
          MAX(COALESCE(hh.rated_at, a.created_at))         AS last_at
        FROM answers a
        LEFT JOIN llm_scores l USING(answer_id)
        LEFT JOIN hh ON hh.answer_id = a.answer_id
    """), {"rid": rid}).mappings().first() or {}

    return {
        "rater_id": rid,
        "total": int(row.get("total") or 0),
        "pending": int(row.get("pending") or 0),
        "avg_llm": row.get("avg_llm"),
        "avg_human": row.get("avg_human"),
        "last_at": row.get("last_at"),
    }

@router.get("/summary")
def rater_summary(
    rater_id: Optional[str] = Query(None, description="teacher01 | teacher02 (προαιρετικό)"),
    session: Session = Depends(get_session),
):
    if rater_id:
        if rater_id not in ("teacher01", "teacher02"):
            raise HTTPException(status_code=400, detail="invalid rater_id")
        return _summary_for_rater(session, rater_id)
    else:
        items = [
            _summary_for_rater(session, "teacher01"),
            _summary_for_rater(session, "teacher02"),
        ]
        return {"items": items}

# ---------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------
@router.get("/results.csv")
def export_results_csv(session: Session = Depends(get_session)):
    """
    Εξάγει CSV με ΟΛΕΣ τις απαντήσεις (open + MC), με:
    - LLM score
    - Teacher1 / Teacher2
    - Human Avg / Human Weighted
    - Final score (συνδυασμός LLM + Human όταν υπάρχουν, αλλιώς μόνο LLM)
    - Attempt, RatedAt ανά rater, Ημερομηνία
    """
    import csv, io, datetime
    from sqlalchemy import text

    # ---- helpers: τι υπάρχει στο schema;
    def table_exists(name: str) -> bool:
        row = session.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:t
        """), {"t": name}).first()
        return bool(row)

    def column_exists(table: str, col: str) -> bool:
        row = session.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
        """), {"t": table, "c": col}).first()
        return bool(row)

    has_interaction = table_exists("interaction")
    has_rated_at_hh = column_exists("human_ratings", "rated_at")

    # ---- CTEs για attempt & rated_at (αν υπάρχουν)
    ctes = []

    if has_interaction:
        ctes.append("""
            att AS (
              SELECT answer_id::text AS aid_text, MIN(attempt_no) AS attempt
              FROM interaction
              GROUP BY answer_id::text
            )
        """)

    if has_rated_at_hh:
        ctes.append("""
            last_r1 AS (
              SELECT answer_id::text AS aid_text, MAX(rated_at) AS rated_at
              FROM human_ratings
              WHERE rater_id='teacher01'
              GROUP BY answer_id::text
            ),
            last_r2 AS (
              SELECT answer_id::text AS aid_text, MAX(rated_at) AS rated_at
              FROM human_ratings
              WHERE rater_id='teacher02'
              GROUP BY answer_id::text
            )
        """)

    ctes_sql = ("WITH " + ",\n".join(ctes)) if ctes else ""

    # ---- Βασικό SELECT: παίρνουμε ΟΛΑ τα answers (MC + open)
    sql = f"""
        {ctes_sql}
        SELECT
          a.answer_id,
          a.user_id,
          a.question_id,
          a.category,
          a.qtype,
          COALESCE(f.llm_score, l.llm_score) AS llm_score,
          (SELECT score FROM human_ratings
             WHERE answer_id = a.answer_id AND rater_id = 'teacher01') AS teacher01,
          (SELECT score FROM human_ratings
             WHERE answer_id = a.answer_id AND rater_id = 'teacher02') AS teacher02,
          f.human_avg,
          f.human_weighted,
          f.final_score,
          a.created_at
          {", att.attempt" if has_interaction else ""}
          {", r1.rated_at AS rated_at_t1, r2.rated_at AS rated_at_t2" if has_rated_at_hh else ""}
        FROM answers a
        LEFT JOIN llm_scores   l USING(answer_id)
        LEFT JOIN final_scores f USING(answer_id)
        { "LEFT JOIN att   ON att.aid_text = a.answer_id::text" if has_interaction else "" }
        { "LEFT JOIN last_r1 r1 ON r1.aid_text = a.answer_id::text" if has_rated_at_hh else "" }
        { "LEFT JOIN last_r2 r2 ON r2.aid_text = a.answer_id::text" if has_rated_at_hh else "" }
        ORDER BY a.user_id, a.question_id
    """

    rows = session.execute(text(sql)).mappings().all()

    # ---- CSV
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    headers = [
        "Α/Α",
        "User",
        "Answer ID",
        "Attempt",
        "Question",
        "Category",
        "Type",
        "LLM Score (0–10)",
        "Teacher 1 (0–10)",
        "Teacher 2 (0–10)",
        "Human Avg (0–10)",
        "Human Weighted (0–10)",
        "Final Score (0–10)",
        "Διαφορά (Human–LLM, 0–10)",
    ]
    if has_rated_at_hh:
        headers += ["RatedAt T1", "RatedAt T2"]
    headers.append("Ημερομηνία")
    writer.writerow(headers)

    def f10(x):
        if x is None:
            return ""
        try:
            return f"{float(x)*10:.1f}".replace('.', ',')
        except Exception:
            return ""

    def fmt_dt(dt):
        if isinstance(dt, datetime.datetime):
            return dt.strftime("%d/%m/%Y %H:%M")
        return ""

    HUMAN_WEIGHT = 0.6  # ίδιο με _recompute_for / recompute-final

    for i, r in enumerate(rows, start=1):
        llm = r.get("llm_score")
        t1  = r.get("teacher01")
        t2  = r.get("teacher02")

        # --- clamp & mean όπως στα helpers
        llm_c = clamp01(llm)
        t1_c  = clamp01(t1)
        t2_c  = clamp01(t2)

        # human_avg = μέσος T1/T2 αν υπάρχουν
        human_vals = []
        if t1_c is not None:
            human_vals.append(t1_c)
        if t2_c is not None:
            human_vals.append(t2_c)
        human_avg = sum(human_vals)/len(human_vals) if human_vals else None

        # human_weighted = ίδιο με human_avg (προς το παρόν)
        human_weighted = human_avg

        # final_score: αν υπάρχουν ανθρώπινα → fusion, αλλιώς μόνο LLM
        if human_avg is not None and llm_c is not None:
            auto = llm_c
            hw   = human_weighted
            final = (1.0 - HUMAN_WEIGHT) * auto + HUMAN_WEIGHT * hw
        elif human_avg is not None:
            final = human_avg
        else:
            final = llm_c

        # diff (Human–LLM) σε 0–10
        diff = ""
        if human_avg is not None and llm_c is not None:
            try:
                diff = f"{(float(human_avg)-float(llm_c))*10:.3f}".replace('.', ',')
            except Exception:
                diff = ""

        row = [
            i,
            r.get("user_id"),
            r.get("answer_id"),
            r.get("attempt") if has_interaction else "",
            r.get("question_id"),
            r.get("category"),
            r.get("qtype"),
            f10(llm_c),
            f10(t1_c),
            f10(t2_c),
            f10(human_avg),
            f10(human_weighted),
            f10(final),
            diff,
        ]
        if has_rated_at_hh:
            row += [fmt_dt(r.get("rated_at_t1")), fmt_dt(r.get("rated_at_t2"))]
        row.append(fmt_dt(r.get("created_at")))
        writer.writerow(row)

    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")  # BOM για Excel/Greek
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8")