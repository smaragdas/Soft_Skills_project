# app/routers/questions.py
from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlmodel import Session
import random

from app.core.db import get_session
from app.core.questions import build_bundle, get_categories

MARKER = "bundle-v2-jsonresp-POST-phase-attempt"
router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/_marker")
def marker():
    return {"marker": MARKER}


@router.get("/bundle")
def bundle(
    category: str = Query("Communication"),
    n_open: int = Query(6, ge=0),
    n_mc: int = Query(6, ge=0),
    include_correct: bool = Query(False),
    phase: str = Query("PRE"),
    attempt: int = Query(1, ge=1, le=2),
    _ts: int | None = Query(
        None,
        description="optional seed for deterministic sampling"
    ),
):
    # Κανονικοποίηση phase/attempt
    phase_norm = "POST" if str(phase).strip().upper() == "POST" else "PRE"
    attempt_norm = 2 if int(attempt or 1) == 2 else 1

    # 🔒 Προαιρετική σπορά τυχαιοποίησης ώστε ίδιο _ts ⇒ ίδιο δείγμα
    if _ts is not None:
        try:
            random.seed(f"{category}|{phase_norm}|{attempt_norm}|{_ts}")
        except Exception:
            pass

    try:
        resp = build_bundle(
            category=category,
            n_open=n_open,
            n_mc=n_mc,
            hide_correct=not include_correct,
            phase=phase_norm,
            attempt=attempt_norm,
        )
        # Σταθερά debug πεδία στο payload
        resp["used_fallback"] = False
        resp["phase"] = phase_norm
        resp["attempt"] = attempt_norm

        # 🔎 ΡΗΤΟ LOG: τι πραγματικά επιστρέφουμε
        open_count = len(resp.get("open") or [])
        mc_count = len(resp.get("mc") or [])
        flat_count = len(resp.get("flat") or [])
        print(
            f"[bundle] OK cat={category} phase={phase_norm} attempt={attempt_norm} "
            f"include_correct={include_correct} keys={list(resp.keys())} "
            f"open={open_count} mc={mc_count} flat={flat_count}"
        )
        return JSONResponse(content=resp, headers={"x-bundle-marker": MARKER})

    except TypeError:
        # Fallback για images με παλιό build_bundle signature
        resp = build_bundle(
            category=category,
            n_open=n_open,
            n_mc=n_mc,
            hide_correct=not include_correct,
        )
        resp["used_fallback"] = True
        resp["phase"] = phase_norm
        resp["attempt"] = attempt_norm

        # 🔎 ΡΗΤΟ LOG: fallback κλάδος
        open_count = len(resp.get("open") or [])
        mc_count = len(resp.get("mc") or [])
        flat_count = len(resp.get("flat") or [])
        print(
            f"[bundle] FALLBACK cat={category} phase={phase_norm} attempt={attempt_norm} "
            f"include_correct={include_correct} keys={list(resp.keys())} "
            f"open={open_count} mc={mc_count} flat={flat_count}"
        )
        return JSONResponse(content=resp, headers={"x-bundle-marker": MARKER})


@router.get("/categories")
def categories(phase: str = Query("PRE", description="PRE ή POST")):
    """Επιστρέφει τις διαθέσιμες κατηγορίες για το δοσμένο phase (PRE/POST)."""
    phase_norm = "POST" if str(phase).strip().upper() == "POST" else "PRE"
    return {"categories": get_categories(phase_norm)}


# ---------------------------------------------------------------------
# ΕΛΑΧΙΣΤΟ endpoint για το Rater UI (να μην 404-άρει):
# GET /api/softskills/questions/quiz/bundle
# Παίρνει τις πιο πρόσφατες ερωτήσεις από τον πίνακα answers και
# επιστρέφει έναν απλό χάρτη id->text/category/qtype (options κενό).
# ---------------------------------------------------------------------
@router.get("/quiz/bundle")
def quiz_bundle(session: Session = Depends(get_session)):
    rows = session.execute(text("""
        SELECT DISTINCT ON (question_id)
               question_id AS id,
               COALESCE(NULLIF(prompt, ''), '[no question text]') AS text,
               COALESCE(category, '') AS category,
               COALESCE(qtype, '')    AS qtype
        FROM answers
        WHERE question_id IS NOT NULL
        ORDER BY question_id, created_at DESC
    """)).mappings().all()

    items = [{
        "id": r["id"],
        "text": r["text"],
        "category": r["category"],
        "qtype": r["qtype"],
        "options": [],
    } for r in rows]

    return {"items": items}


@router.get("")
def questions_index(session: Session = Depends(get_session)):
    rows = session.execute(text("""
        SELECT DISTINCT ON (question_id)
               question_id AS id,
               COALESCE(NULLIF(prompt, ''), '[no question text]') AS text,
               COALESCE(category, '') AS category,
               COALESCE(qtype, '')    AS qtype
        FROM answers
        WHERE question_id IS NOT NULL
        ORDER BY question_id, created_at DESC
    """)).mappings().all()

    items = []
    qmap = {}
    for r in rows:
        obj = {
            "id": r["id"],
            "text": r["text"],
            "category": r["category"],
            "qtype": r["qtype"],
            "options": [],
        }
        items.append(obj)
        qmap[r["id"]] = {k: v for k, v in obj.items() if k != "id"}

    return {"items": items, "map": qmap}


@router.get("/quiz/questions")
def quiz_questions(session: Session = Depends(get_session)):
    rows = session.execute(text("""
        SELECT DISTINCT ON (question_id)
               question_id AS id,
               COALESCE(NULLIF(prompt, ''), '[no question text]') AS text,
               COALESCE(category, '') AS category,
               COALESCE(qtype, '')    AS qtype
        FROM answers
        WHERE question_id IS NOT NULL
        ORDER BY question_id, created_at DESC
    """)).mappings().all()

    items = []
    qmap = {}
    for r in rows:
        obj = {
            "id": r["id"],
            "text": r["text"],
            "category": r["category"],
            "qtype": r["qtype"],
            "options": [],
        }
        items.append(obj)
        qmap[r["id"]] = {k: v for k, v in obj.items() if k != "id"}

    return {"items": items, "map": qmap}
# ---------------------------------------------------------------------
