# app/routers/coach.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlmodel import Session

from app.core.db import get_session
from app.core.coach import aggregate_session, pick_weakest, make_heuristic_session_plan
from app.core.llm import _get_client  # θα το χρησιμοποιήσουμε για μία LLM κλήση
from app.core.settings import settings

router = APIRouter(prefix="/coach", tags=["coach"])

def _llm_session_plan_prompt(summary: Dict[str, Any]) -> str:
    """
    Ελάχιστο prompt: δίνουμε aggregates & weakest και ζητάμε 3 βήματα + micro-drill.
    """
    dims = summary.get("aggregates", {}).get("dimensions", {})
    crit = summary.get("aggregates", {}).get("criteria", {})
    wk   = summary.get("weakest_area", {})

    return (
        "Είσαι coach soft skills. Με βάση τα παρακάτω aggregates φτιάξε ένα "
        "σύντομο πλάνο 3 βημάτων + 1 micro-drill για άμεσα βελτίωση.\n\n"
        f"Dimensions(avg/10): {dims}\n"
        f"Criteria(avg/10): {crit}\n"
        f"Weakest: {wk}\n\n"
        "Επιστροφή ΜΟΝΟ JSON:\n"
        "{\n"
        "  \"overview\": \"μία πρόταση με λογική / rationale\",\n"
        "  \"steps\": [\"βήμα1\",\"βήμα2\",\"βήμα3\"],\n"
        "  \"practice\": \"μία μικρο-άσκηση (micro-drill)\",\n"
        "  \"resources\": [{\"title\":\"...\",\"url\":\"...\"}]\n"
        "}\n"
    )

@router.post("/session-plan")
async def session_plan(request: Request, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """
    Body περιμένει:
    {
      "results": [ ... 16 αντικείμενα από το front ... ],
      "category": "Leadership"   (optional)
    }
    """
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Body must be JSON object")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    results = body.get("results") or []
    if not isinstance(results, list) or len(results) == 0:
        raise HTTPException(status_code=400, detail="results must be a non-empty array")

    # 1) Aggregates
    aggr = aggregate_session(results)
    kind, name, val = pick_weakest(aggr)

    summary = {
        "aggregates": aggr,
        "weakest_area": {"type": kind, "name": name, "score": val}
    }

    # 2) LLM plan (safe; αν αποτύχει/δεν έχει API key → heuristic)
    plan = None
    try:
        client = _get_client()
        from openai import OpenAI  # type: ignore
        if isinstance(client, OpenAI):
            prompt = _llm_session_plan_prompt(summary)
            resp = client.chat.completions.create(
                model=(settings.OPENAI_MODEL or "gpt-4o-mini"),
                messages=[{"role": "system", "content": "Return ONLY valid JSON."},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=getattr(settings, "OPENAI_TEMPERATURE", 0.2) or 0.2,
            )
            text = resp.choices[0].message.content or "{}"
            import json
            plan = json.loads(text)
    except Exception:
        plan = None

    # 3) Heuristic fallback
    if not isinstance(plan, dict) or not plan.get("steps"):
        plan = make_heuristic_session_plan(kind, name, val)

    return {
        "summary": summary,
        "plan": plan
    }
