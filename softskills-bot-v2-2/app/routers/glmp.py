# app/routers/glmp.py
from __future__ import annotations

from typing import Any, Dict, Optional, List, Tuple
from pathlib import Path
import json
import re

from fastapi import APIRouter, HTTPException, Request, Depends
from sqlmodel import Session

# Core imports
from app.core.fuzzy import evaluate_glmp_payload
from app.core.db import get_session
from app.models.evaluation import Evaluation
from app.core.llm import llm_coach_open, llm_coach_mc
from app.core.questions import QUESTIONS as QUESTION_BANK

router = APIRouter(prefix="/glmp", tags=["glmp"])

# ---------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------
_RULES: Optional[Dict[str, Any]] = None
RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "rules_v2.json"

def get_rules() -> Dict[str, Any]:
    global _RULES
    if _RULES is None:
        try:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                _RULES = json.load(f)
        except Exception:
            _RULES = {"weights": {}}
    return _RULES

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def normalize_category(label: Optional[str]) -> str:
    if not label:
        return "communication"
    m = {
        "communication": "communication",
        "leadership": "leadership",
        "teamwork": "teamwork",
        "problem solving": "problem_solving",
        "problem_solving": "problem_solving",
    }
    key = str(label).strip().lower().replace(" ", "_")
    return m.get(key, "communication")




def _norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _text_similarity(a: str, b: str) -> float:
    """
    Πολύ απλό similarity για να πιάσουμε copy-paste:
    - 1.0 αν είναι πρακτικά ίδια
    - αν το ένα περιέχει το άλλο, ratio = len(shorter)/len(longer)
    - αλλιώς 0.0 (δεν μας νοιάζουν «έξυπνες» παραφράσεις εδώ)
    """
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        shorter = na if len(na) < len(nb) else nb
        longer  = nb if len(na) < len(nb) else na
        return len(shorter) / max(1, len(longer))
    return 0.0


def _apply_repetition_penalty_single(
    session: Session,
    user_id: str | None,
    category_norm: str,
    user_text: str,
    current_score: float,
    threshold: float = 0.85,
    penalty: float = 1.0,
) -> tuple[float, dict]:
    """
    Κοιτάζει προηγούμενες open απαντήσεις του χρήστη στην ίδια κατηγορία
    και αν βρει πολύ όμοιες, ρίχνει λίγο το score.
    Επιστρέφει (new_score, debug_info).
    ΤΩΡΑ το debug_info γυρνάει ΠΑΝΤΑ το max_similarity, για να βλέπουμε τι γίνεται.
    """
    if not user_id or not user_text.strip():
        return current_score, {
            "repetition_max_similarity": 0.0,
            "repetition_penalized": False,
        }

    from sqlmodel import select
    prev_evals = session.exec(
        select(Evaluation)
        .where(Evaluation.user_id == user_id)
        .where(Evaluation.category == category_norm)
    ).all()

    max_sim = 0.0
    for ev in prev_evals:
        measures = ev.measures or {}
        t_block = (measures.get("text") or {})
        t = t_block.get("value") or t_block.get("raw") or ""
        if not t:
            continue
        sim = _text_similarity(user_text, str(t))
        if sim > max_sim:
            max_sim = sim

    debug_info: dict = {
        "repetition_max_similarity": round(max_sim, 3),
        "repetition_threshold": threshold,
        "repetition_penalty": penalty,
        "repetition_penalized": False,
    }

    if max_sim >= threshold:
        new_score = max(0.0, float(current_score) - penalty)
        debug_info["repetition_penalized"] = True
        return new_score, debug_info

    return current_score, debug_info

def to_bank_label(label: Optional[str]) -> str:
    internal = normalize_category(label)
    m = {
        "communication": "Communication",
        "leadership": "Leadership",
        "teamwork": "Teamwork",
        "problem_solving": "Problem Solving",
    }
    return m.get(internal, "Communication")

def normalize_mcq_accuracy(payload: Dict[str, Any]) -> None:
    mc = payload.get("mcq") or payload.get("mc")
    if not isinstance(mc, dict):
        return
    if payload.get("mcq") is None:
        payload["mcq"] = mc
    if "accuracy" not in mc and "accuracy_0_10" in mc:
        try:
            val10 = float(mc["accuracy_0_10"])
            mc["accuracy"] = max(0.0, min(1.0, val10 / 10.0))
        except Exception:
            pass

def _lookup_correct_id(category_label: str, qid: str) -> Optional[str]:
    bank_cat = to_bank_label(category_label)
    bucket = (QUESTION_BANK.get(bank_cat) or {}).get("mc") or []
    for q in bucket:
        if str(q.get("id")) == str(qid):
            if q.get("correct_id") is not None:
                return str(q["correct_id"])
            if q.get("correct") is not None:
                try:
                    return str(int(q["correct"]))
                except Exception:
                    return None
    return None

def _lookup_question_and_options(category_label: str, qid: str) -> Tuple[Optional[str], Dict[str, str]]:
    bank_cat = to_bank_label(category_label)
    bucket = (QUESTION_BANK.get(bank_cat) or {}).get("mc") or []
    for q in bucket:
        if str(q.get("id")) != str(qid):
            continue
        qtext = str(q.get("text") or "")
        opts: Dict[str, str] = {}
        if isinstance(q.get("options"), list):
            for o in q["options"]:
                oid = str(o.get("id"))
                txt = str(o.get("text") or "")
                opts[oid] = txt
        elif isinstance(q.get("choices"), list):
            for i, t in enumerate(q["choices"]):
                opts[str(i)] = str(t)
        return qtext, opts
    return None, {}

def _ensure_mcq_accuracy(payload: Dict[str, Any]) -> Dict[str, Any]:
    meta = payload.get("meta") or {}
    mcq = payload.get("mcq") or payload.get("mc")
    if not isinstance(mcq, dict):
        return {}
    if "accuracy" in mcq:
        payload["mcq"] = mcq
        return mcq
    sel = mcq.get("selected_id")
    if sel is None:
        return {}
    category_in = meta.get("category") or payload.get("category") or ""
    qid = meta.get("answerId") or payload.get("question_id") or ""
    corr = mcq.get("correct_id") or _lookup_correct_id(category_in, str(qid))
    mcq["accuracy"] = 1.0 if (corr is not None and str(corr) == str(sel)) else 0.0
    mcq["correct_id_used"] = str(corr) if corr is not None else None
    payload["mcq"] = mcq
    return mcq

def _clip010(x: float) -> float:
    try:
        return max(0.0, min(10.0, float(x or 0.0)))
    except Exception:
        return 0.0

def _lbl10(s: float) -> str:
    s = float(s)
    if s < 4.5: return "Low"
    if s < 7.5: return "Mid"
    return "High"

def _get_text_value(payload: Dict[str, Any]) -> str:
    t = payload.get("text") or {}
    return str(t.get("value") or t.get("raw") or "").strip()

def _has_open_text(payload: Dict[str, Any]) -> bool:
    return bool(_get_text_value(payload))

def _compute_debug(payload: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
    dbg: Dict[str, Any] = {}
    mc = payload.get("mcq") or payload.get("mc")
    has_mc = isinstance(mc, dict) and bool(mc)
    dbg["has_mcq"] = has_mc
    dbg["has_text"] = isinstance(payload.get("text"), dict) and bool(payload.get("text"))

    m = (payload.get("mcq") or payload.get("mc") or {})
    acc10 = None
    if "accuracy" in m:
        try:
            acc = float(m["accuracy"])
            if acc <= 1.0:
                acc10 = acc * 10.0
            elif acc <= 10.0:
                acc10 = acc
            else:
                acc10 = (acc / 100.0) * 10.0
        except Exception:
            acc10 = None
    dbg["mcq_accuracy_0_10"] = acc10

    r = rules or {}
    w = r.get("weights") or {}
    dbg["rules_dimensions_keys"] = list((w.get("dimensions") or {}).keys())
    dbg["rules_categories_keys"] = list((w.get("categories") or {}).keys())
    return dbg

def _sync_all_categories(out: Dict[str, Any]) -> None:
    """Κράτα τα categories sync με το τελικό overall (απλός καθρέφτης)."""
    try:
        s = float(out.get("score", 0.0))
    except Exception:
        s = 0.0
    label = _lbl10(s)
    out["all_categories"] = {
        "communication": {"score": s, "label": label},
        "leadership": {"score": s, "label": label},
        "teamwork": {"score": s, "label": label},
        "problem_solving": {"score": s, "label": label},
    }

# ---------------------------------------------------------------------
# LLM → GLMP mapping & fusion
# ---------------------------------------------------------------------
def _apply_llm_to_glmp(payload: Dict[str, Any], llm: dict) -> Dict[str, float]:
    """
    Map LLM criteria (Clarity/Relevance/Structure/Examples) → GLMP inputs:
      Clarity   → clarity
      Structure → coherence
      Relevance → topic_relevance
      Examples  → vocabulary_range
    """
    written: Dict[str, float] = {}
    if not (isinstance(llm, dict) and isinstance(llm.get("criteria"), list)):
        return written

    lower = {}
    for c in llm["criteria"]:
        try:
            n = str(c.get("name", "")).strip().lower()
            s = float(c.get("score", 0) or 0)
            lower[n] = s
        except Exception:
            pass

    clarity   = lower.get("clarity")
    structure = lower.get("structure")
    relevance = lower.get("relevance")
    examples  = lower.get("examples")

    text_block = payload.get("text") or {}
    if clarity is not None:
        text_block["clarity"] = _clip010(clarity); written["clarity"] = text_block["clarity"]
    if structure is not None:
        text_block["coherence"] = _clip010(structure); written["coherence"] = text_block["coherence"]
    if relevance is not None:
        text_block["topic_relevance"] = _clip010(relevance); written["topic_relevance"] = text_block["topic_relevance"]
    if examples is not None:
        text_block["vocabulary_range"] = _clip010(examples); written["vocabulary_range"] = text_block["vocabulary_range"]

    payload["text"] = text_block
    return written

def _fuse_text_and_mcq(text_score_0_10: float, mcq_acc_0_10: float, has_mcq: bool) -> tuple[float, Dict[str, float]]:
    if has_mcq:
        overall = 0.40 * mcq_acc_0_10 + 0.60 * text_score_0_10
        w = {"mcq": 0.40, "text": 0.60}
    else:
        overall = text_score_0_10
        w = {"mcq": 0.0, "text": 1.0}
    return _clip010(overall), w

# ---------------------------------------------------------------------
# Build response
# ---------------------------------------------------------------------
def build_response(
    payload: Dict[str, Any],
    out: Dict[str, Any],
    debug_extra: Dict[str, Any],
    coaching: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    meta = (payload.get("meta") or {})
    cat = normalize_category(meta.get("category") or payload.get("category"))
    resp = {
        "id": out.get("id") or meta.get("answerId"),
        "skill": out.get("skill", cat),
        "score": out.get("score", 0.0),
        "label": out.get("label", "Low"),
        "dimensions": out.get("dimensions") or {},
        "attributes": out.get("attributes") or {},
        "all_categories": out.get("all_categories") or {},
        "feedback": out.get("feedback") or {},
        "debug": {**(out.get("debug") or {}), **debug_extra},
    }
    if coaching:
        resp["coaching"] = coaching
    return resp

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@router.post("/evaluate")
async def glmp_evaluate(request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    normalize_mcq_accuracy(payload)
    _ensure_mcq_accuracy(payload)
    rules = get_rules()

    # 1) Base GLMP
    out = evaluate_glmp_payload(payload, rules)
    debug_extra = _compute_debug(payload, rules)

    meta = payload.get("meta") or {}
    category = meta.get("category") or payload.get("category") or "Communication"
    qid = meta.get("answerId") or payload.get("question_id") or ""
    coaching: Optional[Dict[str, Any]] = None

    # 2) OPEN-TEXT με LLM → inject → re-evaluate → fuse
    if isinstance(payload.get("text"), dict) and _has_open_text(payload):
        user_text = _get_text_value(payload)
        llm = llm_coach_open(category, str(qid), user_text)  # μπορεί να είναι {}
        if isinstance(llm, dict) and llm.get("error"):
            debug_extra["llm_error"] = str(llm.get("error"))

        mapped = _apply_llm_to_glmp(payload, llm)
        out = evaluate_glmp_payload(payload, rules)

        text_score = float(out.get("score", 0.0))
        if text_score == 0.0 and user_text.strip():
            text_score = 6.0
            out["score"] = text_score
            out["label"] = _lbl10(text_score)
            debug_extra["baseline_applied"] = True

        mcq10 = float(debug_extra.get("mcq_accuracy_0_10") or 0.0) or 0.0
        fused, w = _fuse_text_and_mcq(text_score, mcq10, bool(debug_extra.get("has_mcq")))
        out["score"] = round(_clip010(fused), 2)
        out["label"] = _lbl10(out["score"])
        _sync_all_categories(out)

        out.setdefault("feedback", {})
        out["feedback"]["summary"] = (
            "Το LLM ανέλυσε το ανοιχτό κείμενο (Clarity/Relevance/Structure/Examples) "
            "και οι βαθμολογίες χαρτογραφήθηκαν στα GLMP measures. "
            "Ο συνολικός δείκτης συνδυάζει 40% MCQ και 60% Text."
        )
        if isinstance(llm, dict) and llm.get("criteria"):
            out["feedback"]["criteria"] = llm["criteria"]

        debug_extra["fusion_weights"] = w
        if mapped:
            debug_extra["llm_to_glmp_mapped"] = mapped

        coaching = llm or {}

    # 3) ΜΟΝΟ MCQ
    elif isinstance(payload.get("mcq"), dict) or isinstance(payload.get("mc"), dict):
        mc = payload.get("mcq") or payload.get("mc") or {}
        sel = str(mc.get("selected_id") or "")
        qtext, opts = _lookup_question_and_options(category, str(qid))
        corr = mc.get("correct_id") or _lookup_correct_id(category, str(qid))
        llm = llm_coach_mc(category, str(qid), qtext or "", opts, sel, corr)
        if isinstance(llm, dict) and llm.get("error"):
            debug_extra["llm_error"] = str(llm.get("error"))
        coaching = llm or {}

    return build_response(payload, out, debug_extra, coaching)

@router.post("/evaluate-and-save")
async def glmp_evaluate_and_save(request: Request, session: Session = Depends(get_session)) -> Dict[str, Any]:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    normalize_mcq_accuracy(payload)
    _ensure_mcq_accuracy(payload)
    rules = get_rules()

    out = evaluate_glmp_payload(payload, rules)
    debug_extra = _compute_debug(payload, rules)

    meta = payload.get("meta") or {}
    category = meta.get("category") or payload.get("category") or "Communication"
    qid = meta.get("answerId") or payload.get("question_id") or ""
    coaching: Optional[Dict[str, Any]] = None

    if isinstance(payload.get("text"), dict) and _has_open_text(payload):
        user_text = _get_text_value(payload)
        llm = llm_coach_open(category, str(qid), user_text)
        if isinstance(llm, dict) and llm.get("error"):
            debug_extra["llm_error"] = str(llm.get("error"))
        mapped = _apply_llm_to_glmp(payload, llm)
        out = evaluate_glmp_payload(payload, rules)

        text_score = float(out.get("score", 0.0))
        if text_score == 0.0 and user_text.strip():
            text_score = 6.0
            out["score"] = text_score
            out["label"] = _lbl10(text_score)
            debug_extra["baseline_applied"] = True

        mcq10 = float(debug_extra.get("mcq_accuracy_0_10") or 0.0) or 0.0
        fused, w = _fuse_text_and_mcq(text_score, mcq10, bool(debug_extra.get("has_mcq")))
        out["score"] = round(_clip010(fused), 2)
        out["label"] = _lbl10(out["score"])
        _sync_all_categories(out)

        # === Repetition penalty: αν ο χρήστης επαναλαμβάνει την ίδια απάντηση σε πολλές open ===
        user_id = (meta.get("userId") or meta.get("user_id") or payload.get("user_id"))
        category_norm = normalize_category(category)

        penalized_score, rep_debug = _apply_repetition_penalty_single(
            session=session,
            user_id=str(user_id) if user_id is not None else None,
            category_norm=category_norm,
            user_text=user_text,
            current_score=float(out["score"]),
            threshold=0.90,   # πόσο «ίδιες» πρέπει να είναι
            penalty=1.0       # πόσο κόβουμε
        )

        if penalized_score != out["score"]:
            out["score"] = round(_clip010(penalized_score), 2)
            out["label"] = _lbl10(out["score"])

        # 🆕 γράφουμε ΠΑΝΤΑ τα debug fields, ακόμα κι αν δεν μπήκε penalty
        debug_extra.update(rep_debug)

        out.setdefault("feedback", {})
        out["feedback"]["summary"] = (
            "Το LLM ανέλυσε το ανοιχτό κείμενο (Clarity/Relevance/Structure/Examples) "
            "και οι βαθμολογίες χαρτογραφήθηκαν στα GLMP measures. "
            "Ο συνολικός δείκτης συνδυάζει 40% MCQ και 60% Text."
        )
        if isinstance(llm, dict) and llm.get("criteria"):
            out["feedback"]["criteria"] = llm["criteria"]

        debug_extra["fusion_weights"] = w
        if mapped:
            debug_extra["llm_to_glmp_mapped"] = mapped

        coaching = llm or {}

    elif isinstance(payload.get("mcq"), dict) or isinstance(payload.get("mc"), dict):
        mc = payload.get("mcq") or payload.get("mc") or {}
        sel = str(mc.get("selected_id") or "")
        qtext, opts = _lookup_question_and_options(category, str(qid))
        corr = mc.get("correct_id") or _lookup_correct_id(category, str(qid))
        llm = llm_coach_mc(category, str(qid), qtext or "", opts, sel, corr)
        if isinstance(llm, dict) and llm.get("error"):
            debug_extra["llm_error"] = str(llm.get("error"))
        coaching = llm or {}

    # Save
    try:
        user_id = (meta.get("userId") or meta.get("user_id") or payload.get("user_id"))
        qid_final = (meta.get("questionId") or meta.get("question_id") or meta.get("answerId") or payload.get("answer_id"))
        if qid_final is not None:
            qid_final = str(qid_final)
        category_norm = normalize_category(category)

        modalities = []
        if isinstance(payload.get("text"), dict) and _has_open_text(payload):
            modalities.append("text")
        if isinstance(payload.get("mcq"), dict) or isinstance(payload.get("mc"), dict):
            modalities.append("mcq")
        modalities_str = ",".join(modalities) or ""

        out.setdefault("debug", {})
        out["debug"].update(debug_extra)

        result_to_store = dict(out)
        if coaching:
            result_to_store["coaching"] = coaching

        ev = Evaluation(
            user_id=user_id,
            question_id=qid_final,
            category=category_norm,
            modalities=modalities_str,
            measures=payload,
            result=result_to_store,
        )
        session.add(ev)
        session.commit()
        session.refresh(ev)

        resp = build_response(payload, result_to_store, debug_extra, coaching)
        resp["id"] = ev.id
        return resp

    except Exception as e:
        print("SAVE ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------
# NEW: /glmp/session-plan  (για να μη ρίχνει 404 στο UI)
# ---------------------------------------------------------------------
@router.post("/session-plan")
async def session_plan(request: Request) -> Dict[str, Any]:
    """
    Επιστρέφει ένα απλό, έγκυρο πλάνο με τη δομή που περιμένει το frontend.
    Δεν αφαιρεί/επηρεάζει καμία από τις υπάρχουσες ροές.
    """
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    meta = payload.get("meta") or {}
    level = str(meta.get("level") or "").upper()
    overall = float(meta.get("overall") or 0.0)
    weakest = meta.get("weakestCategory") or ""

    # Ένα απλό default πλάνο. Το UI θέλει: title, summary, steps[], resources[].
    title = "Πλάνο 2 εβδομάδων (personalized)"
    summary = "Το πλάνο εστιάζει στα αδύναμα σημεία σας για γρήγορη βελτίωση."
    steps = [
        "Επιλέξτε 1–2 μικρούς στόχους για τις επόμενες δύο εβδομάδες.",
        "Κλείστε 3 x 30' blocks στο ημερολόγιο για στοχευμένη εξάσκηση.",
        "Ζητήστε feedback από έναν συμφοιτητή/συνάδελφο πάνω στο συγκεκριμένο skill."
    ]
    resources = []

    # Αν έχουμε weakest category, προσθέτουμε μια μικρή προσαρμογή στα resources.
    if isinstance(weakest, str) and weakest:
        resources.append({
            "title": f"Γρήγορος οδηγός για {weakest}",
            "url": "https://rework.withgoogle.com/subjects/teams/" if "team" in weakest.lower() else "https://www.mindtools.com/"
        })

    return {
        "title": title,
        "summary": summary,
        "steps": steps,
        "resources": resources,
        "metaEcho": { "level": level, "overall": overall, "weakest": weakest }
    }
