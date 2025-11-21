# app/routers/glmp_save.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from app.core.db import get_session
from app.schemas.glmp import GLMPMeasures
from app.core.fuzzy import evaluate_glmp
from app.models.evaluation import Evaluation
from pathlib import Path
import json
from datetime import datetime


def _apply_glmp_overlay(result: dict) -> dict:
    try:
        # Αν υπάρχει _compute_glmp_dyn, το χρησιμοποιούμε· αλλιώς απλώς επιστρέφουμε το result.
        # Αν το όνομα δεν έχει οριστεί, το NameError θα πιαστεί στο except και θα κάνουμε return result.
        if _compute_glmp_dyn is None:  # type: ignore[name-defined]
            return result
        # Extract per-skill scores (0..10) and normalize to 0..1
        nodes = result.get("skill_nodes") or {}
        dims01 = {str(k).lower(): float(v.get("score", 0.0)) / 10.0 for k, v in nodes.items()}
        glmp_res = _compute_glmp_dyn(dims01)  # type: ignore[name-defined]
        # Attach overlay scores
        result = dict(result)
        result["glmp_overlay"] = {
            "weights": glmp_res.get("weights"),
            "contributions": glmp_res.get("contributions"),
            "final_score_0_1": glmp_res.get("final_score", 0.0),
            "final_score_0_10": float(glmp_res.get("final_score", 0.0)) * 10.0
        }
        return result
    except Exception:
        return result

router = APIRouter(prefix="/glmp", tags=["glmp-save"])

RULES_PATH = Path("app/rules/rules_v2.json")

def load_rules():
    if not RULES_PATH.exists():
        raise HTTPException(status_code=500, detail="Missing rules file")
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))

@router.post("/evaluate-and-save")
def evaluate_and_save(payload: GLMPMeasures, session: Session = Depends(get_session)):
    rules = load_rules()
    measures = payload.model_dump()
    result = evaluate_glmp(measures, rules)

    # ✅ FIX: Το παρακάτω block ήταν εκτός function (λάθος indent). Τώρα είναι σωστά μέσα στο def.
    meta = measures.get("meta") or {}
    category = (meta.get("category") or "communication").lower()
    modalities = ",".join(meta.get("modalities") or [])

    ev = Evaluation(
        user_id = meta.get("userId"),
        question_id = meta.get("answerId") or meta.get("questionId"),
        category = category,
        modalities = modalities,
        measures = measures,
        result = result
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)

    # επιλέγουμε primary skill από το meta.category αν υπάρχει
    skill_nodes = result.get("skill_nodes") or {}
    primary = category if category in skill_nodes else (list(skill_nodes.keys())[0] if skill_nodes else "CompositeSkill")
    response = {
        "id": ev.id,
        "skill": primary if primary!="CompositeSkill" else "composite",
        **(skill_nodes.get(primary) if primary in skill_nodes else {}),
        "dimensions": result.get("dimensions", {}),
        "attributes": result.get("attributes", {}),
        "all_categories": skill_nodes
    }
    return response
