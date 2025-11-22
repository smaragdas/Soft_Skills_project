# app/routers/score.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException, Request, Header
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any, List, Tuple
from app.core.llm import llm_coach_mc
from sqlmodel import Session
from sqlalchemy import text
from uuid import uuid4
from datetime import datetime
import json
import uuid
import traceback

from app.core.db import get_session
from app.core.settings import settings
from app.core.study_token import parse_token

# === Rubric weights & calibration (minimal add) ===
_WEIGHTS_BY_CATEGORY = {
    "Communication":   {"relevance": 2, "clarity": 2, "empathy": 3, "actionability": 2, "specificity": 1},
    "Teamwork":        {"relevance": 2, "clarity": 1, "empathy": 3, "actionability": 2, "specificity": 2},
    "Leadership":      {"relevance": 2, "clarity": 2, "empathy": 2, "actionability": 3, "specificity": 1},
    "Problem Solving": {"relevance": 2, "clarity": 1, "empathy": 1, "actionability": 3, "specificity": 3},
}
_GAMMA_BY_CATEGORY = {
    "Communication": 1.10,
    "Teamwork": 1.15,
    "Leadership": 1.15,
    "Problem Solving": 1.20,
}


def _get_participant_and_attempt(
    user_id_in: str | None,
    token_q: str | None,
    token_h: str | None,
    attempt_in: int | None,
):
    pid = None
    # 1) token (query/header) υπερισχύει
    for tok in (token_q, token_h):
        if tok:
            u = parse_token(tok)
            if u:
                pid = str(u)
                break
    # 2) αλλιώς ό,τι μας έστειλε το UI
    if not pid and user_id_in:
        pid = user_id_in
    # attempt
    att = attempt_in if isinstance(attempt_in, int) and attempt_in in (1, 2) else 1
    return pid, att


def _norm_cat(cat: str) -> str:
    c = (cat or "").strip()
    if c.lower().replace("-", " ").replace("_", " ") == "problem solving":
        return "Problem Solving"
    return c or "Leadership"


def _calibrate_category_score(score_0_10: float, category: str) -> float:
    try:
        s = max(0.0, min(10.0, float(score_0_10)))
    except Exception:
        s = 0.0
    gamma = _GAMMA_BY_CATEGORY.get(_norm_cat(category), 1.15)
    return round(((s / 10.0) ** gamma) * 10.0, 2)


def _weighted_from_criteria(criteria: list, category: str) -> float | None:
    """Compute weighted score 0..10 from criteria list like [{'name': 'Clarity','score': 7},...]"""
    if not isinstance(criteria, list) or not criteria:
        return None
    weights = _WEIGHTS_BY_CATEGORY.get(_norm_cat(category), _WEIGHTS_BY_CATEGORY["Leadership"])
    acc = 0.0
    den = 0.0
    for c in criteria:
        try:
            name = str(c.get("name", "")).strip().lower()
            score = float(c.get("score", 0))
        except Exception:
            continue
        key = None
        if "clarity" in name:
            key = "clarity"
        elif "relevance" in name or "σχετικ" in name:
            key = "relevance"
        elif "empathy" in name or "ενσυνα" in name:
            key = "empathy"
        elif "action" in name or "πρακτικ" in name:
            key = "actionability"
        elif "specific" in name or "παράδειγ" in name or "τεκμηρ" in name:
            key = "specificity"
        if key and key in weights:
            w = float(weights[key])
            acc += max(0.0, min(10.0, score)) * w
            den += w
    if den <= 0:
        return None
    return acc / den


# ---------------------------------------------------------------------------
# Optional LLM helpers (won't break if missing)
# ---------------------------------------------------------------------------
_HAVE_LLM = False
try:
    from app.core.llm import llm_coach_open, llm_coach_mc  # type: ignore
    _HAVE_LLM = True
except Exception:
    _HAVE_LLM = False

# Κύριος router (το main.py προσθέτει και prefix για το νέο API)
router = APIRouter(prefix="", tags=["score"])

# ============================== Pydantic Models ==============================
class BaseModelConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class MCPayload(BaseModelConfig):
    category: str
    question_id: str
    user_id: Optional[str] = None
    question_text: str
    selected_id: str
    correct_id: Optional[str] = None
    options: List[Dict[str, Any]]  # [{id, text}, ...]


class ScoreOpenRequest(BaseModelConfig):
    category: str
    question_id: str
    text: str
    user_id: Optional[str] = None


class ScoreOpenResponse(BaseModelConfig):
    text: str
    category: str
    question_id: str
    score: float
    feedback: Dict[str, Any]
    model: str = "heuristic"
    answer_id: Optional[str] = None
    interaction_id: Optional[str] = None
    criteria: Optional[List[Dict[str, Any]]] = None


class ScoreMCResponse(BaseModelConfig):
    answer_id: Optional[str] = None
    interaction_id: Optional[str] = None
    source: str
    model_name: str
    llm_used: bool
    correct: Optional[bool] = None
    auto_score: float
    confidence: float
    feedback: Any  # μπορεί να είναι str ή dict
    coaching: Dict[str, Any]
    criteria: Optional[List[Dict[str, Any]]] = None

class ScoreOpenFromGlmpRequest(BaseModel):
    user_id: str
    category: str
    question_id: str
    text: str
    score: float    


# ============================== Heuristics ==============================
def _rubric_open_heuristic_0_10(text: str, category: str) -> Tuple[float, List[Dict[str, Any]]]:
    t = (text or "").lower()
    crits: List[Dict[str, Any]] = []

    def has_any(keys: List[str]) -> bool:
        return any(k in t for k in keys)

    # Clarity
    clarity = 6
    if len(text) < 40:
        clarity -= 2
    if len(text) > 300:
        clarity -= 1
    crits.append({"name": "Clarity", "score": max(0, min(10, clarity)), "comment": ""})

    # Relevance (με category-based keywords)
    rel_keys = {
        "Communication": ["ακρο", "παράδειγ", "σύνοψ", "αναλογία", "ερώτ"],
        "Leadership": ["ομάδ", "πρωτοβουλ", "ευθύ", "συνεργ", "κίνητρο"],
        "Teamwork": ["ομάδ", "ρόλ", "συνεργ", "feedback", "συντον"],
        "Problem Solving": ["λύση", "πρόβ", "βήμα", "αιτία", "δοκίμ"],
    }
    relevance = 5 + (2 if has_any(rel_keys.get(category, [])) else 0)
    crits.append({"name": "Relevance", "score": max(0, min(10, relevance)), "comment": ""})

    # Structure
    structure = 5
    if any(k in t for k in ["πρώτα", "στη συνέχεια", "τέλος", "βήμα"]):
        structure += 2
    crits.append({"name": "Structure", "score": max(0, min(10, structure)), "comment": ""})

    # Examples
    examples = 4 + (3 if has_any(["παράδειγ", "αναλογία", "όπως", "π.χ"]) else 0)
    crits.append({"name": "Examples", "score": max(0, min(10, examples)), "comment": ""})

    total = round(sum(c["score"] for c in crits) / 4)
    return total, crits


def heuristic_open_feedback(text: str, category: str) -> Dict[str, str]:
    t = (text or "").lower()
    strengths, gaps = [], []

    if any(x in t for x in ["ερώτ", "ρωτ", "ask", "κατανό"]):
        strengths.append("ενεργητική κατανόηση κοινού")
    else:
        gaps.append("ξεκίνα με 1 ερώτηση κατανόησης")

    if any(x in t for x in ["παράδειγ", "example", "αναλογία"]):
        strengths.append("χρήση παραδείγματος/αναλογίας")
    else:
        gaps.append("δώσε 1 σχετικό παράδειγμα")

    if any(x in t for x in ["σύνοψ", "κλείσ", "επόμενο βήμα"]):
        strengths.append("σαφές κλείσιμο με επόμενο βήμα")
    else:
        gaps.append("κλείσε με ξεκάθαρο επόμενο βήμα")

    return {
        "keep": " — ".join(strengths) if strengths else "Διατήρησε ό,τι λειτούργησε.",
        "change": gaps[0] if gaps else "Ακρίβεια στον στόχο του ακροατηρίου.",
        "action": "Ρώτα 1 ερώτηση κατανόησης και πρόσθεσε 1 παράδειγμα στο επόμενο μήνυμα.",
        "drill": "Mini-brief 45'': στόχος–γιατί–εμπόδιο–επόμενο βήμα.",
    }


def heuristic_mc_score_and_feedback(
    selected_id: str,
    correct_id: Optional[str],
    question_text: str,
    options_map: Dict[str, str],
    category: Optional[str] = None,
) -> Tuple[Optional[bool], float, str, Dict[str, str]]:
    selected_txt = (options_map.get(selected_id, "") or "")
    st = selected_txt.lower()
    correct_txt = (options_map.get(correct_id or "", "") or "").strip()
    correct: Optional[bool] = None

    cat = (category or "").strip().lower()
    base_pos = {
        "structure": ["δομή", "κριτήρι", "κριτήριο", "σαφή", "ρόλ", "milestone", "κανόν", "ορισ"],
        "inclusion": ["συμμετοχ", "facilit", "facilitation", "συντον", "συνεργ", "ακούμε", "συζήτ"],
        "feedback": ["feedback", "ανατροφοδ", "1:1", "retrospective", "ρετρό", "συχνό"],
    }
    base_neg = {
        "speed": ["γρήγο", "ταχύ", "άμεσα", "αστραπ", "speed"],
        "majority": ["ψηφοφορ", "πλειοψηφ", "majority vote"],
        "authority": ["manager decides", "manager", "αποφασίζ", "αυθεντ", "διευθυντής"],
        "random": ["τυχα", "κλήρο", "random"],
    }
    category_signals = {
        "leadership": {
            "pos": ["όραμα", "vision", "ευθυγράμμ", "delegat", "ανάθεση", "ενδυν", "empower"],
            "neg": ["μικροδιαχείρ", "micromanag", "αυθεντ", "μονομερ", "μονολογ"],
        },
        "teamwork": {
            "pos": ["pair", "ζευγάρωμα", "συνεργ", "κανόνες ομάδας", "retrospective", "facilit", "1:1"],
            "neg": ["σιλό", "silo", "φταίει", "blame", "ανταγωνισμ", "μόνος μου"],
        },
        "communication": {
            "pos": ["σύνοψ", "clarify", "δομή μηνύματος", "παράδειγ", "αναλογία", "ερώτηση κατανόησης"],
            "neg": ["jargon", "ασάφεια", "πολυλογία", "αόριστο"],
        },
        "problem solving": {
            "pos": ["ρίζα αιτίας", "root cause", "5 why", "υπόθεση", "hypothesis", "πειραματισ", "A/B", "κριτήρια επιτυχίας"],
            "neg": ["μπαλώματα", "quick fix", "διόρθωση επιφάνειας", "χωρίς δεδομένα"],
        },
    }

    def has_any(text: str, keys: list[str]) -> bool:
        return any(k in text for k in keys)

    pos_count = 0.0
    pos_detail: list[str] = []
    neg_count = 0.0
    neg_detail: list[str] = []

    if has_any(st, base_pos["structure"]):
        pos_count += 1.2
        pos_detail.append("δομή/κριτήρια")
    if has_any(st, base_pos["inclusion"]):
        pos_count += 0.9
        pos_detail.append("συμπερίληψη/συντονισμός")
    if has_any(st, base_pos["feedback"]):
        pos_count += 0.5
        pos_detail.append("ανατροφοδότηση")

    if has_any(st, base_neg["speed"]):
        neg_count += 0.8
        neg_detail.append("ταχύτητα πάνω από ποιότητα")
    if has_any(st, base_neg["majority"]):
        neg_count += 1.0
        neg_detail.append("πλειοψηφία αντί κριτηρίων")
    if has_any(st, base_neg["authority"]):
        neg_count += 1.0
        neg_detail.append("αυθεντία αντί δομής")
    if has_any(st, base_neg["random"]):
        neg_count += 1.2
        neg_detail.append("τυχαία επιλογή")

    cat_key = "problem solving" if cat in ("problem solving", "problem-solving", "problem_solving") else cat
    if cat_key in category_signals:
        sig = category_signals[cat_key]
        if has_any(st, sig["pos"]):
            pos_count += 0.9
            pos_detail.append(cat_key + ": θετικά")
        if has_any(st, sig["neg"]):
            neg_count += 0.9
            neg_detail.append(cat_key + ": αρνητικά")

    base = 3.0 + (pos_count * 0.85) - (neg_count * 0.9)
    base = max(1.0, min(5.0, base))

    if correct_id:
        correct = (selected_id == correct_id)
        if correct:
            base = max(base, 4.5)
            if pos_count >= 1.6:
                base = max(base, 4.8)
            if pos_count >= 2.2:
                base = 5.0
        else:
            base = min(base, 2.0)
            if pos_count >= 1.6:
                base = 2.5

    score = round(base * 2.0) / 2.0

    def bullet(lst: list[str]) -> str:
        return " — ".join(lst)

    cat_note = f" ({category})" if category else ""

    if correct is True:
        feedback = f"Σωστό{cat_note} — ευθυγραμμισμένο με σαφή κριτήρια και λειτουργικό συντονισμό."
        coaching = {
            "keep": "Συνέχισε με σαφή κριτήρια/ρόλους και μία ερώτηση κατανόησης πριν το κλείσιμο.",
            "change": "Συνόψισε το 'γιατί' σε 1 πρόταση για να είναι κρυστάλλινο.",
            "action": "Ολοκλήρωσε με ουδέτερη σύνοψη και επιβεβαίωση επόμενου βήματος.",
            "drill": "Mini-brief 45'': στόχος–κριτήρια–ρόλοι–επόμενο βήμα.",
        }
        if pos_detail:
            coaching["keep"] += f" (δυνατά σημεία: {bullet(pos_detail)})."
    elif correct is False:
        reasons = []
        if has_any(st, base_neg["majority"]):
            reasons.append("πλειοψηφία αντί κριτηρίων")
        if has_any(st, base_neg["authority"]):
            reasons.append("αυθεντία αντί ορισμένων κριτηρίων")
        if has_any(st, base_neg["speed"]):
            reasons.append("ταχύτητα > ποιότητα απόφασης")
        if has_any(st, base_neg["random"]):
            reasons.append("τυχαία/μη τεκμηριωμένη")
        if cat_key in category_signals and has_any(st, category_signals[cat_key]["neg"]):
            reasons.append("ασυμβατό με τις αρχές της κατηγορίας")

        why = bullet(reasons) if reasons else "λείπει δομή και σαφή κριτήρια"
        core_correct = f" Η σωστή επιλογή τονίζει: {correct_txt}." if correct_txt else ""
        feedback = f"Λάθος{cat_note} — {why}.{core_correct}"

        keep_hint = "Κράτα την πρόθεση για απόφαση"
        if pos_detail:
            keep_hint += f" και τα στοιχεία {bullet(pos_detail)}"
        coaching = {
            "keep": keep_hint + ".",
            "change": "Πρόσθεσε 1–2 σαφή κριτήρια και μοίρασε ρόλους πριν την τελική επιλογή.",
            "action": "Ζήτα από 1 μέλος που δεν μίλησε να δώσει οπτική· μετά κάνε ουδέτερη σύνοψη.",
            "drill": "Άσκηση 60'': γράψε κριτήρια επιτυχίας και μοίρασε ρόλους για το επόμενο βήμα.",
        }
    else:
        if pos_count >= 1.2:
            feedback = f"Καλή κατεύθυνση{cat_note} — αναδεικνύεις στοιχεία δομής/συμπερίληψης."
            coaching = {
                "keep": "Διατήρησε τα σαφή κριτήρια και τον συντονισμό.",
                "change": "Τεκμηρίωσε με 1 πρόταση το 'γιατί' της επιλογής.",
                "action": "Κλείσε με ουδέτερη σύνοψη και επιβεβαίωση επομένου βήματος.",
                "drill": "Άσκηση: γράψε 2 επιλογές, βάλε κριτήρια και αιτιολόγησε την τελική.",
            }
        else:
            feedback = f"Προσοχή{cat_note} — χρειάζεται περισσότερη δομή (κριτήρια/ρόλοι) ή ενεργή συμπερίληψη."
            coaching = {
                "keep": "Κράτα τη διάθεση για απόφαση.",
                "change": "Πρόσθεσε 1–2 κριτήρια και ορισμό ρόλων πριν την επιλογή.",
                "action": "Ζήτησε 1 νέα οπτική και κάνε ουδέτερη σύνοψη πριν το κλείσιμο.",
                "drill": "Mini-brief 45'': στόχος–κριτήρια–ρόλοι–επόμενο βήμα.",
            }

    return correct, float(score), feedback, coaching


# ============================== DB helpers (PRAGMA-based -> PG-safe) ====================
def _utc_now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _new_answer_id() -> str:
    return f"ans_{uuid4().hex[:12]}"


def _new_interaction_id() -> str:
    return f"int_{uuid4().hex[:12]}"


def _table_info(session: Session, table: str):
    sql = """
    SELECT
      column_name   AS name,
      data_type,
      is_nullable,
      column_default
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name=:t
    ORDER BY ordinal_position;
    """
    rows = session.execute(text(sql), {"t": table}).mappings().all()
    return rows


def _table_cols(session: Session, table: str):
    return {row["name"]: row for row in _table_info(session, table)}


def _to_pg_value(v):
    # Αν είναι dict/list -> JSON string
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


# --- dynamic insert που παίζει σωστά με JSONB ---
def _dynamic_insert(session: Session, table: str, data: dict):
    """
    Γενικό INSERT με RETURNING *.
    - Για τον πίνακα 'autorating' κάνουμε CAST σε JSONB για τα πεδία feedback/coaching
      και περνάμε JSON-serialized string (ώστε psycopg2 να το προσαρμόσει σωστά).
    """
    cols_info = _table_cols(session, table)
    if not cols_info:
        raise RuntimeError(f"Table '{table}' not found in public schema")

    allowed = {k: v for k, v in data.items() if k in cols_info}
    if not allowed:
        raise RuntimeError(f"No valid columns for table '{table}' in payload keys={list(data.keys())}")

    # χτίζουμε λίστες για ονόματα στηλών και placeholders
    col_names = []
    placeholders = []
    params = {}

    for k, v in allowed.items():
        col_names.append(k)
        param_name = f"p_{k}"

        # autorating.feedback / autorating.coaching => jsonb
        if table == "autorating" and k in ("feedback", "coaching"):
            # serialize to JSON string (χωρίς BOM, unicode ok)
            if not isinstance(v, str):
                v = json.dumps(v, ensure_ascii=False)
            placeholders.append(f"CAST(:{param_name} AS JSONB)")
            params[param_name] = v
        else:
            placeholders.append(f":{param_name}")
            params[param_name] = v

    cols_sql = ", ".join(col_names)
    vals_sql = ", ".join(placeholders)

    sql = text(f"INSERT INTO {table} ({cols_sql}) VALUES ({vals_sql}) RETURNING *;")
    row = session.execute(sql, params).mappings().first()
    session.commit()
    return dict(row) if row else None


# --- ΝΕΟ: upsert σε answers + llm_scores (uuid v4) ---
def _upsert_answers_and_llm(
    session: Session,
    *,
    answer_id: str,
    user_id: str,
    question_id: str,
    category: str,
    qtype: str,  # "open" | "mc"
    prompt: Optional[str],
    answer: Optional[str],
    llm_score_0_1: Optional[float],  # 0..1
) -> None:
    session.execute(
        text(
            """
        INSERT INTO answers(answer_id, user_id, question_id, category, qtype, prompt, text)
        VALUES (:aid, :user_id, :qid, :cat, :qtype, :prompt, :answer)
        ON CONFLICT (answer_id) DO UPDATE
          SET user_id     = EXCLUDED.user_id,
              question_id = EXCLUDED.question_id,
              category    = EXCLUDED.category,
              qtype       = EXCLUDED.qtype,
              prompt      = EXCLUDED.prompt,
              text        = EXCLUDED.text
        """
        ),
        {
            "aid": answer_id,
            "user_id": user_id,
            "qid": question_id,
            "cat": category or "",
            "qtype": qtype,
            "prompt": (prompt or ""),
            "answer": (answer or ""),
        },
    )

    if llm_score_0_1 is not None:
        session.execute(
            text(
                """
            INSERT INTO llm_scores(answer_id, llm_score)
            VALUES (:aid, :llm)
            ON CONFLICT (answer_id) DO UPDATE
              SET llm_score = EXCLUDED.llm_score,
                  scored_at = now()
            """
            ),
            {"aid": answer_id, "llm": float(llm_score_0_1)},
        )


# ============================== Endpoints ==============================
@router.post("/score-open", response_model=ScoreOpenResponse)
async def score_open(
    request: ScoreOpenRequest,
    session: Session = Depends(get_session),
    save: bool = Query(True),
    force_llm: bool = Query(False),
    attempt: int | None = Query(None),
    token: str | None = Query(None),
    x_study_token: str | None = Header(None, alias="X-Study-Token"),
) -> ScoreOpenResponse:
    try:
        # Heuristic baseline
        h_score, h_criteria = _rubric_open_heuristic_0_10(request.text, request.category)
        h_feedback = heuristic_open_feedback(request.text, request.category)

        # ✅ Resolve participant & attempt
        participant_id, attempt_no = _get_participant_and_attempt(
            request.user_id, token, x_study_token, attempt
        )

        # LLM (αν υπάρχει)
        use_llm = _HAVE_LLM and getattr(settings, "OPENAI_API_KEY", None) and (
            force_llm or not getattr(settings, "HEURISTIC_ONLY", False)
        )
        if use_llm:
            try:
                out = llm_coach_open(request.category, request.question_id, request.text) or {}
            except Exception as e:
                out = {
                    "score": h_score,
                    "keep": "Σφάλμα.",
                    "change": str(e),
                    "action": "Δοκίμασε ξανά.",
                    "drill": "Έλεγξε API key/μοντέλο.",
                    "model_name": getattr(settings, "OPENAI_MODEL", None) or "llm",
                    "criteria": h_criteria,
                }

            llm_score = float(out.get("score", h_score))
            llm_feedback = {
                "keep": out.get("keep") or h_feedback.get("keep"),
                "change": out.get("change") or h_feedback.get("change"),
                "action": out.get("action") or h_feedback.get("action"),
                "drill": out.get("drill") or h_feedback.get("drill"),
            }
            llm_criteria = out.get("criteria") or h_criteria

            blended = round(0.7 * llm_score + 0.3 * h_score)
            weighted_or_blended = _weighted_from_criteria(llm_criteria, request.category) or blended
            final_score = _calibrate_category_score(weighted_or_blended, request.category)

            interaction_id = answer_id = None
            if save:
                created_at = _utc_now_str()
                answer_id = str(uuid.uuid4())

                _dynamic_insert(
                    session,
                    "interaction",
                    {
                        "answer_id": answer_id,
                        "category": request.category,
                        "qtype": "open",
                        "question_id": request.question_id,
                        "text": request.text,
                        "text_raw": request.text,
                        "answer_text": request.text,
                        "user_id": participant_id,
                        "participant_id": participant_id,
                        "attempt_no": attempt_no,
                        "created_at": created_at,
                    },
                )

                _dynamic_insert(
                    session,
                    "autorating",
                    {
                        "answer_id": answer_id,
                        "score": float(final_score),
                        "confidence": 0.75,
                        "model_name": out.get("model_name", getattr(settings, "OPENAI_MODEL", None) or "llm"),
                        "feedback": {"kind": "coaching", **llm_feedback},
                        "coaching": llm_feedback,
                        "attempt_no": attempt_no,
                        "created_at": created_at,
                    },
                )

                _upsert_answers_and_llm(
                    session,
                    answer_id=answer_id,
                    user_id=participant_id or "",
                    question_id=request.question_id,
                    category=request.category,
                    qtype="open",
                    prompt=None,
                    answer=request.text,
                    llm_score_0_1=(float(final_score) / 10.0),
                )
                session.execute(
                    text(
                        """
                 UPDATE answers
                    SET participant_id = :pid,
                        attempt = :att
                  WHERE answer_id = :aid
                """
                    ),
                    {"pid": participant_id, "att": attempt_no, "aid": answer_id},
                )
                session.commit()

                interaction_id = None

            return ScoreOpenResponse(
                text=request.text,
                category=request.category,
                question_id=request.question_id,
                score=float(final_score),
                feedback=llm_feedback,
                model=out.get("model_name", "llm"),
                answer_id=answer_id,
                interaction_id=interaction_id,
                criteria=llm_criteria,
            )

        # Fallback: heuristic only
        interaction_id = answer_id = None
        if save:
            created_at = _utc_now_str()
            answer_id = str(uuid.uuid4())

            _dynamic_insert(
                session,
                "interaction",
                {
                    "answer_id": answer_id,
                    "category": request.category,
                    "qtype": "open",
                    "question_id": request.question_id,
                    "text": request.text,
                    "text_raw": request.text,
                    "answer_text": request.text,
                    "user_id": participant_id,
                    "attempt_no": attempt_no,
                    "created_at": created_at,
                },
            )

            h_final = _calibrate_category_score(
                _weighted_from_criteria(h_criteria, request.category) or float(h_score),
                request.category,
            )
            _dynamic_insert(
                session,
                "autorating",
                {
                    "answer_id": answer_id,
                    "score": float(h_final),
                    "confidence": 0.6,
                    "model_name": "heuristic",
                    "feedback": {"kind": "coaching", **h_feedback},
                    "coaching": h_feedback,
                    "attempt_no": attempt_no,
                    "created_at": created_at,
                },
            )

            _upsert_answers_and_llm(
                session,
                answer_id=answer_id,
                user_id=participant_id or "",
                question_id=request.question_id,
                category=request.category,
                qtype="open",
                prompt=None,
                answer=request.text,
                llm_score_0_1=(float(h_final) / 10.0),
            )
            session.execute(
                text(
                    """
                 UPDATE answers
                    SET participant_id = :pid,
                        attempt = :att
                  WHERE answer_id = :aid
            """
                ),
                {"pid": participant_id, "att": attempt_no, "aid": answer_id},
            )
            session.commit()

        return ScoreOpenResponse(
            text=request.text,
            category=request.category,
            question_id=request.question_id,
            score=_calibrate_category_score(
                _weighted_from_criteria(h_criteria, request.category) or float(h_score),
                request.category,
            ),
            feedback=h_feedback,
            model="heuristic",
            answer_id=answer_id,
            interaction_id=interaction_id,
            criteria=h_criteria,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"score-open error: {e}\n{traceback.format_exc()}")

@router.post("/score-open-from-glmp", response_model=ScoreOpenResponse)
async def score_open_from_glmp(
    payload: ScoreOpenFromGlmpRequest,
    session: Session = Depends(get_session),
    save: bool = Query(True),
    attempt: int | None = Query(None),
    token: str | None = Query(None),
    x_study_token: str | None = Header(None, alias="X-Study-Token"),
) -> ScoreOpenResponse:
    """
    ΔΕΝ ξανακάνει LLM, ΔΕΝ κάνει calibration.
    Απλώς παίρνει το score από το GLMP (0–10) και το γράφει στα interaction/autorating/answers.
    """
    try:
        # ✅ resolve participant/attempt όπως και στο score_open
        participant_id, attempt_no = _get_participant_and_attempt(
            payload.user_id, token, x_study_token, attempt
        )

        final_score = float(payload.score)
        if final_score < 0.0:
            final_score = 0.0
        if final_score > 10.0:
            final_score = 10.0

        interaction_id = None
        answer_id = None

        if save:
            created_at = _utc_now_str()
            answer_id = str(uuid.uuid4())

            # interaction
            _dynamic_insert(
                session,
                "interaction",
                {
                    "answer_id": answer_id,
                    "category": payload.category,
                    "qtype": "open",
                    "question_id": payload.question_id,
                    "text": payload.text,
                    "text_raw": payload.text,
                    "answer_text": payload.text,
                    "user_id": participant_id,
                    "participant_id": participant_id,
                    "attempt_no": attempt_no,
                    "created_at": created_at,
                },
            )

            # απλό feedback/coaching placeholder (δεν είναι τόσο κρίσιμο, το βασικό είναι το score)
            coaching = {
                "keep": "Συνέχισε με τον ίδιο τρόπο απάντησης.",
                "change": "Δώσε λίγη παραπάνω σαφήνεια και παραδείγματα όπου γίνεται.",
                "action": "Εφάρμοσε την ανατροφοδότηση του πλάνου μελέτης στις επόμενες απαντήσεις.",
                "drill": "Δοκίμασε να γράψεις ξανά την απάντηση με λίγο πιο δομημένο τρόπο.",
            }

            _dynamic_insert(
                session,
                "autorating",
                {
                    "answer_id": answer_id,
                    "score": final_score,
                    "confidence": 0.8,
                    "model_name": "glmp-open",
                    "feedback": {"kind": "glmp", "summary": "Βαθμολογία από GLMP quiz."},
                    "coaching": coaching,
                    "attempt_no": attempt_no,
                    "created_at": created_at,
                },
            )

            # answers + llm_scores (0..10 -> 0..1)
            _upsert_answers_and_llm(
                session,
                answer_id=answer_id,
                user_id=participant_id or "",
                question_id=payload.question_id,
                category=payload.category,
                qtype="open",
                prompt=None,
                answer=payload.text,
                llm_score_0_1=(final_score / 10.0),
            )

            session.execute(
                text(
                    """
                 UPDATE answers
                    SET participant_id = :pid,
                        attempt = :att
                  WHERE answer_id = :aid
                """
                ),
                {"pid": participant_id, "att": attempt_no, "aid": answer_id},
            )
            session.commit()

        return ScoreOpenResponse(
            text=payload.text,
            category=payload.category,
            question_id=payload.question_id,
            score=final_score,
            feedback={"summary": "Σκορ καταχωρήθηκε από GLMP.", "kind": "glmp"},
            model="glmp-open",
            answer_id=answer_id,
            interaction_id=interaction_id,
            criteria=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"score-open-from-glmp error: {e}\n{traceback.format_exc()}",
        )



@router.post("/score-mc", response_model=ScoreMCResponse)
def score_mc(
    payload: MCPayload,
    save: bool = Query(True, description="Αποθήκευση interaction + autorating"),
    force_llm: bool = Query(False, description="Χρησιμοποίησε LLM coaching αν είναι διαθέσιμο"),
    session: Session = Depends(get_session),
):
    try:
        # ---------------- OPTIONS MAP ----------------
        options_map = {
            o["id"]: o["text"]
            for o in (payload.options or [])
            if "id" in o and "text" in o
        }

        # ---------------- correct_id RESOLUTION ----------------
        correct_id = (payload.correct_id or "").strip()
        if not correct_id:
            truthy = {"true", "1", "yes", "y"}
            for o in (payload.options or []):
                cval = o.get("correct", None)
                if cval is True or (isinstance(cval, str) and cval.strip().lower() in truthy):
                    cid = str(o.get("id") or "").strip()
                    if cid:
                        correct_id = cid
                        break

        # ---------------- HEURISTIC ----------------
        correct, h_score, h_feedback, h_coaching = heuristic_mc_score_and_feedback(
            payload.selected_id,
            correct_id,
            payload.question_text,
            options_map,
            payload.category,
        )

        # default values (heuristic)
        source = "heuristic"
        model_name = "heuristic-v2"
        feedback_final: Any = h_feedback
        coaching_final: Dict[str, Any] = h_coaching
        criteria_out: Optional[List[Dict[str, Any]]] = None
        llm_used = False

        # τελικό score που θα γράψουμε / επιστρέψουμε (0..10)
        final_score: float = float(h_score)

        # ---------------- LLM CALL (OPTIONAL) ----------------
        if force_llm and _HAVE_LLM and getattr(settings, "OPENAI_API_KEY", None):
            try:
                out = llm_coach_mc(
                    category=payload.category,
                    question_id=payload.question_id,
                    question_text=payload.question_text,
                    options=options_map,
                    selected_id=payload.selected_id,
                    correct_id=correct_id,
                ) or {}

                if isinstance(out, dict) and "error" not in out:
                    # LLM δίνει score σε κλίμακα 0..10 → αυτό θέλουμε
                    llm_score = out.get("score", final_score)
                    try:
                        final_score = float(llm_score)
                    except Exception:
                        final_score = float(h_score)

                    # συνένωση coaching (LLM + heuristic fallback)
                    coaching_final = {
                        "keep":   out.get("keep")   or (coaching_final or {}).get("keep"),
                        "change": out.get("change") or (coaching_final or {}).get("change"),
                        "action": out.get("action") or (coaching_final or {}).get("action"),
                        "drill":  out.get("drill")  or (coaching_final or {}).get("drill"),
                    }

                    criteria_out = out.get("criteria") or criteria_out
                    model_name = out.get(
                        "model_name",
                        getattr(settings, "OPENAI_MODEL", None) or "llm-coach",
                    )
                    source = "llm"
                    llm_used = True
                else:
                    # LLM επέστρεψε error → fallback σε heuristic
                    feedback_final = f"{h_feedback} (LLM fallback: {out.get('error')})"
            except Exception as e:
                feedback_final = f"{h_feedback} (LLM fallback: {e})"

        # ---------------- FALLBACK RULE (ΑΝ ΔΕΝ ΕΧΕΙ LLM) ----------------
        if not llm_used:
            # Θέλουμε απλή κλίμακα: σωστό → 10, λάθος → 0 (όπως glmp)
            if correct is True:
                final_score = 10.0
                if isinstance(feedback_final, str):
                    feedback_final = {"summary": "Σωστή επιλογή."}
                else:
                    feedback_final = feedback_final or {"summary": "Σωστή επιλογή."}

                coaching_final = coaching_final or {
                    "keep": "Συνέχισε να ελέγχεις τα κριτήρια πριν απαντήσεις.",
                    "change": "Πρόσθεσε 1 πρόταση ‘γιατί’ για πληρότητα.",
                    "action": "Εφάρμοσε τον ίδιο έλεγχο κριτηρίων σε επόμενες ερωτήσεις.",
                    "drill": "Άσκηση: γράψε 2 κριτήρια για παρόμοιο σενάριο.",
                }
            elif correct is False:
                final_score = 0.0
                if isinstance(feedback_final, str):
                    feedback_final = {"summary": "Λανθασμένη επιλογή."}
                else:
                    feedback_final = feedback_final or {"summary": "Λανθασμένη επιλογή."}

                coaching_final = coaching_final or {
                    "keep": "Κράτα την προσπάθεια για γρήγορη απόφαση.",
                    "change": "Έλεγξε τα βασικά κριτήρια πριν επιλέξεις.",
                    "action": "Σύγκρινε την απάντησή σου με τη σωστή και σημείωσε τη διαφορά.",
                    "drill": "Άσκηση: εντόπισε 2 κριτήρια που οδηγούν στη σωστή επιλογή.",
                }

        # τελικό auto_score που γράφουμε/επιστρέφουμε
        score_cal = float(final_score)

        # ---------------- RESOLVE PARTICIPANT / ATTEMPT ----------------
        participant_id, attempt_no = _get_participant_and_attempt(
            payload.user_id, None, None, None
        )

        interaction_id = None
        answer_id = None

        # ---------------- SAVE TO DB ----------------
        if save:
            created_at = _utc_now_str()
            answer_id = str(uuid.uuid4())

            selected_text = options_map.get(payload.selected_id)

            _dynamic_insert(
                session,
                "interaction",
                {
                    "answer_id": answer_id,
                    "category": payload.category,
                    "qtype": "mc",
                    "question_id": payload.question_id,
                    "text": payload.question_text,
                    "text_raw": payload.question_text,
                    "user_id": participant_id,
                    "participant_id": participant_id,
                    "selected_option_id": payload.selected_id,
                    "selected_text": selected_text,
                    "attempt_no": attempt_no,
                    "created_at": created_at,
                },
            )

            # JSONB πεδία: βεβαιώσου ότι είναι dict
            if isinstance(feedback_final, str):
                feedback_final = {"summary": feedback_final}
            if isinstance(coaching_final, str):
                coaching_final = {"summary": coaching_final}

            _dynamic_insert(
                session,
                "autorating",
                {
                    "answer_id": answer_id,
                    "score": score_cal,
                    "confidence": 0.7,
                    "model_name": model_name,
                    "feedback": feedback_final,
                    "coaching": coaching_final,
                    "attempt_no": attempt_no,
                    "created_at": created_at,
                },
            )

            _upsert_answers_and_llm(
                session,
                answer_id=answer_id,
                user_id=participant_id or "",
                question_id=payload.question_id,
                category=payload.category,
                qtype="mc",
                prompt=payload.question_text,
                answer=selected_text or payload.selected_id,
                # 0..10 → 0..1
                llm_score_0_1=(float(score_cal) / 10.0),
            )

            session.execute(
                text(
                    """
                    UPDATE answers
                       SET participant_id = :pid,
                           attempt = :att
                     WHERE answer_id = :aid
                    """
                ),
                {"pid": participant_id, "att": attempt_no, "aid": answer_id},
            )

            session.commit()

        return ScoreMCResponse(
            answer_id=answer_id,
            interaction_id=interaction_id,
            source=source,
            model_name=model_name,
            llm_used=llm_used,
            correct=correct,
            auto_score=score_cal,
            confidence=0.7,
            feedback=feedback_final,
            coaching=coaching_final,
            criteria=criteria_out,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"score-mc error: {e}\n{traceback.format_exc()}",
        )

# ============================== LEGACY ALIASES ==============================
legacy_router = APIRouter(tags=["score-legacy"])


def _camel_to_snake_open(d: dict) -> dict:
    return {
        "category": d.get("category", d.get("Category")),
        "question_id": d.get("question_id", d.get("questionId")),
        "text": d.get("text", d.get("answer", d.get("userText"))),
        "user_id": d.get("user_id", d.get("userId")),
    }


@legacy_router.post("/score-open")
async def legacy_score_open(request: Request, session: Session = Depends(get_session)):
    body = await request.json()
    mapped = _camel_to_snake_open(body)
    req = ScoreOpenRequest(**mapped)
    return await score_open(req, session)  # type: ignore


@legacy_router.post("/score-mc")
async def legacy_score_mc(request: Request, session: Session = Depends(get_session)):
    body = await request.json()
    payload = MCPayload(
        category=body.get("category", body.get("Category")),
        question_id=body.get("question_id", body.get("questionId")),
        user_id=body.get("user_id", body.get("userId")),
        question_text=body.get("question_text", body.get("questionText")),
        selected_id=body.get("selected_id", body.get("selectedId")),
        correct_id=body.get("correct_id", body.get("correctId")),
        options=body.get("options", body.get("choices", [])),
    )
    return score_mc(payload, session=session)  # type: ignore


@router.get("/final-score")
def final_score(
    answer_id: str,
    human_weight: float = 0.5,
    normalize_mc_to_10: bool = True,
    session: Session = Depends(get_session),
):
    """
    Επιστρέφει συνδυαστική τελική βαθμολογία για ένα answer_id:
    - auto (autorating)
    - humans (avg από humanrating)
    - final = auto*(1-human_weight) + human_avg*human_weight
    """
    human_weight = max(0.0, min(1.0, float(human_weight)))
    auto_weight = 1.0 - human_weight

    stmt_inter = text(
        """
        SELECT category, qtype FROM interaction WHERE answer_id = :a LIMIT 1
    """
    ).bindparams(a=answer_id)
    inter = session.exec(stmt_inter).mappings().first()
    if not inter:
        raise HTTPException(status_code=404, detail=f"answer_id '{answer_id}' not found in interaction")

    category = inter.get("category")
    qtype = inter.get("qtype")

    stmt_auto = text(
        """
        SELECT score, model_name, confidence, created_at
        FROM autorating
        WHERE answer_id = :a
        ORDER BY created_at DESC
        LIMIT 1
    """
    ).bindparams(a=answer_id)
    auto = session.exec(stmt_auto).mappings().first()

    auto_score = None
    model_name = None
    confidence = None
    if auto:
        auto_score = float(auto.get("score") or 0.0)
        model_name = auto.get("model_name")
        confidence = float(auto.get("confidence") or 0.0)

    stmt_hum = text(
        """
        SELECT COUNT(*) AS cnt, AVG(score) AS avg_score
        FROM humanrating
        WHERE answer_id = :a
    """
    ).bindparams(a=answer_id)
    hum = session.exec(stmt_hum).mappings().first()
    human_count = int(hum.get("cnt") or 0)
    human_avg = float(hum.get("avg_score") or 0.0) if human_count > 0 else None

    if qtype == "mc" and normalize_mc_to_10 and auto_score is not None and auto_score <= 5.0:
        auto_score = auto_score * 2.0

    if auto_score is None and human_avg is None:
        raise HTTPException(status_code=404, detail="no scores found for given answer_id")

    auto_for_mix = auto_score if auto_score is not None else 0.0
    human_for_mix = human_avg if human_avg is not None else 0.0
    final = auto_for_mix * auto_weight + human_for_mix * human_weight

    return {
        "answer_id": answer_id,
        "category": category,
        "qtype": qtype,
        "auto": {
            "score": auto_score,
            "model": model_name,
            "confidence": confidence,
        },
        "humans": {
            "count": human_count,
            "avg": human_avg,
        },
        "weights": {
            "human_weight": human_weight,
            "auto_weight": auto_weight,
            "normalized_mc_to_10": bool(normalize_mc_to_10),
        },
        "final_score": round(final, 2),
    }
