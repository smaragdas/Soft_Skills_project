# app/core/fuzzy.py
# Minimal GLMP-style fuzzy aggregator (0–10) for MCQ + Text only
# Works without external deps, produces interpretable fields.

from __future__ import annotations
from typing import Any, Dict, Optional
import uuid

# ------------------------- helpers -------------------------
def _norm_cat(cat: Optional[str]) -> str:
    if not cat:
        return "communication"
    c = str(cat).strip().lower()
    aliases = {
        "communication": "communication",
        "teamwork": "teamwork",
        "leadership": "leadership",
        "problem solving": "problem_solving",
        "problem_solving": "problem_solving",
        "problem-solving": "problem_solving",
    }
    return aliases.get(c, c.replace(" ", "_"))

def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

def _clip010(x: float) -> float:
    return max(0.0, min(10.0, float(x)))

def _label_from_score(s: float) -> str:
    if s < 4.5:
        return "Low"
    if s >= 7.5:
        return "High"
    return "Mid"

def _band(s: float) -> str:
    if s < 4.5:
        return "low"
    if s >= 7.5:
        return "high"
    return "mid"

def _mean(values) -> float:
    vals = [float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0

def _safe_num(d: Dict[str, Any], key: str, default: float = 0.0) -> float:
    v = d.get(key)
    if v is None:
        return default
    try:
        if isinstance(v, str):
            v = v.strip().replace(",", ".")
        return float(v)
    except Exception:
        return default

def _get_rule(d: Optional[Dict[str, Any]], *path, default=None):
    """Safe nested-get for rules dicts."""
    cur = d or {}
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default

# ------------------------- core scoring -------------------------
def _score_from_mcq(mcq: Optional[Dict[str, Any]]) -> float:
    """0–10 από MCQ accuracy."""
    if not isinstance(mcq, dict):
        return 0.0
    if "accuracy" in mcq:
        acc = _clip01(_safe_num(mcq, "accuracy", 0.0))
        return _clip010(10.0 * acc)
    sel = str(mcq.get("selected_id")) if mcq.get("selected_id") is not None else None
    cor = str(mcq.get("correct_id")) if mcq.get("correct_id") is not None else None
    if sel is None or cor is None:
        return 0.0
    return 10.0 if sel == cor else 0.0

def _score_from_text(text: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Υπολογίζει clarity, coherence, topic_relevance, vocabulary_range και composite."""
    if not isinstance(text, dict):
        return {k: 0.0 for k in ("clarity","coherence","topic_relevance","vocabulary_range","composite")}
    clarity = _clip010(_safe_num(text, "clarity", 0.0))
    coherence = _clip010(_safe_num(text, "coherence", 0.0))
    topic_relevance = _clip010(_safe_num(text, "topic_relevance", 0.0))
    vocabulary_range = _clip010(_safe_num(text, "vocabulary_range", 0.0))
    composite = _mean([clarity, coherence, topic_relevance, vocabulary_range])
    return {
        "clarity": clarity,
        "coherence": coherence,
        "topic_relevance": topic_relevance,
        "vocabulary_range": vocabulary_range,
        "composite": composite,
    }

def _dimensions_from_inputs(mcq_score: float, t: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    kd = _clip010(0.80 * mcq_score + 0.20 * t.get("topic_relevance", 0.0))
    cs = _clip010(0.45 * t.get("clarity", 0.0) + 0.45 * t.get("coherence", 0.0) + 0.10 * t.get("topic_relevance", 0.0))
    dp = _clip010(0.75 * t.get("vocabulary_range", 0.0) + 0.25 * t.get("clarity", 0.0))
    return {
        "Knowledge_Decision": {"score": kd, "label": _label_from_score(kd)},
        "Content_Structure": {"score": cs, "label": _label_from_score(cs)},
        "Delivery_Presence": {"score": dp, "label": _label_from_score(dp)},
    }

def _attributes_from_inputs(mcq_score: float) -> Dict[str, Dict[str, Any]]:
    dq = _clip010(mcq_score)
    return {"Decision_Quality": {"score": dq, "label": _label_from_score(dq)}}

def _overall_from_modalities_with_weights(mcq_score: float, text_comp: float, mcq_w: float, text_w: float) -> float:
    if mcq_score > 0 and text_comp > 0:
        s = max(1e-9, (mcq_w + text_w))
        mcq_w, text_w = mcq_w / s, text_w / s
        return _clip010(mcq_w * mcq_score + text_w * text_comp)
    if text_comp > 0:
        return _clip010(text_comp)
    if mcq_score > 0:
        return _clip010(mcq_score)
    return 0.0

# ------------------------- coaching text -------------------------
def _coach_from_scores(overall: float, mcq_score: float, t: Dict[str, float], dims: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    b_over = _band(overall)
    b_kd   = _band(dims["Knowledge_Decision"]["score"])
    b_cs   = _band(dims["Content_Structure"]["score"])
    b_dp   = _band(dims["Delivery_Presence"]["score"])
    keep_bits, change_bits, actions, drills = [], [], [], []
    # KD
    if b_kd == "high":
        keep_bits.append("Σωστές επιλογές και καθαρά κριτήρια στις αποφάσεις.")
    elif b_kd == "mid":
        change_bits.append("Κάνε ρητά τα κριτήρια απόφασης πριν επιλέξεις λύση.")
        actions.append("Γράψε γιατί μια επιλογή είναι καλύτερη από τις άλλες.")
    else:
        change_bits.append("Εστίασε στην οριοθέτηση κριτηρίων πριν απαντήσεις.")
        actions.append("Χρησιμοποίησε κανόνα: στόχος → 2–3 κριτήρια → επιλογή.")
    # CS
    if b_cs == "high":
        keep_bits.append("Καθαρή δομή και συνεκτικότητα στο κείμενο.")
    elif b_cs == "mid":
        change_bits.append("Κράτα σταθερό σκελετό (πλαίσιο → επιλογές → απόφαση).")
        drills.append("Γράψε απάντηση 4 προτάσεων: πλαίσιο, επιλογές, απόφαση, επόμενο.")
    else:
        change_bits.append("Δούλεψε τη βασική διάρθρωση: μια ιδέα ανά πρόταση.")
        drills.append("Ξαναγράψε απάντηση σε 4 σύντομες προτάσεις, κάθε μία με 1 ιδέα.")
    # DP
    if b_dp == "high":
        keep_bits.append("Στοχευμένο λεξιλόγιο χωρίς φλυαρία.")
    elif b_dp == "mid":
        change_bits.append("Χρησιμοποίησε πιο συγκεκριμένες λέξεις-δράσης.")
    else:
        change_bits.append("Απόφυγε αόριστες εκφράσεις· επίλεξε ρήματα που δείχνουν ενέργεια.")
    # Overall note
    if b_over == "high":
        summary_note = "Σταθερή επίδοση – συνέχισε με μικρά στοχευμένα βήματα."
    elif b_over == "mid":
        summary_note = "Καλή βάση – με λίγο πιο αυστηρή δομή και λεξιλόγιο θα ανέβεις επίπεδο."
    else:
        summary_note = "Ξεκίνα από τη δομή και τα κριτήρια απόφασης."
    return {
        "keep": " • ".join(keep_bits) or "Σταθερά στοιχεία – κράτησέ τα.",
        "change": " • ".join(change_bits[:2]) or "Περισσότερη σαφήνεια και δομή.",
        "action": actions[0] if actions else "Εφάρμοσε σκελετό 4 προτάσεων.",
        "drill": drills[0] if drills else "5′ άσκηση: γράψε απάντηση σε 4 προτάσεις.",
        "summary_note": summary_note,
    }

# ------------------------- public API -------------------------
def evaluate_glmp(
    meta: Dict[str, Any],
    mcq: Optional[Dict[str, Any]] = None,
    text: Optional[Dict[str, Any]] = None,
    rules: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    category_label = meta.get("category") or meta.get("skill") or "communication"
    skill_norm = _norm_cat(category_label)
    answer_id = str(meta.get("answerId") or meta.get("answer_id") or uuid.uuid4())

    mcq_score = _score_from_mcq(mcq)
    text_scores = _score_from_text(text)
    text_comp = text_scores["composite"]
    dimensions = _dimensions_from_inputs(mcq_score, text_scores)
    attributes = _attributes_from_inputs(mcq_score)

    # --- Fusion weights (default 40/60), allow override if rules provide them ---
    fusion_mcq_w = 0.40
    fusion_text_w = 0.60
    fuse = _get_rule(rules, "weights", "fusion", skill_norm, default=None)
    if isinstance(fuse, dict):
        try:
            fusion_mcq_w = float(fuse.get("mcq", fusion_mcq_w))
            fusion_text_w = float(fuse.get("text", fusion_text_w))
        except Exception:
            pass

    overall = _overall_from_modalities_with_weights(mcq_score, text_comp, fusion_mcq_w, fusion_text_w)
    overall_label = _label_from_score(overall)

    base_pack = {"score": overall, "label": overall_label}
    all_categories = {k: dict(base_pack) for k in ("communication","leadership","teamwork","problem_solving")}
    coaching = _coach_from_scores(overall, mcq_score, text_scores, dimensions)

    # --- Step: Feedback summary (safe & modality-aware) ---
    if mcq_score > 0 and text_comp > 0:
        base_summary = (
            f"Ο συνολικός δείκτης προκύπτει από {int(round(fusion_mcq_w*100))}% MCQ "
            f"(ακρίβεια απόφασης) και {int(round(fusion_text_w*100))}% κειμενικά μέτρα "
            f"(σαφήνεια, συνοχή, συνάφεια, λεξιλόγιο). "
        )
    elif mcq_score > 0:
        base_summary = "Ο συνολικός δείκτης βασίζεται αποκλειστικά στην επίδοση MCQ (ακρίβεια απόφασης). "
    elif text_comp > 0:
        base_summary = "Ο συνολικός δείκτης βασίζεται αποκλειστικά σε κειμενικά μέτρα (σαφήνεια, συνοχή, συνάφεια, λεξιλόγιο). "
    else:
        base_summary = "Δεν υπάρχουν μετρήσιμες εισροές (MCQ/Κείμενο) για υπολογισμό σκορ. "

    debug = {
        "has_mcq": isinstance(mcq, dict),
        "has_text": isinstance(text, dict),
        "mcq_accuracy_0_10": mcq_score,
        "meta_answer_id": answer_id,
        "rules_dimensions_keys": list(dimensions.keys()),
        "rules_categories_keys": list(all_categories.keys()),
        # τι πραγματικά χρησιμοποιήθηκε για το overall:
        "overall_mode": "fusion",
        "fusion_weights": {"mcq": fusion_mcq_w, "text": fusion_text_w},
    }

    return {
        "id": answer_id,
        "skill": skill_norm,
        "score": round(float(overall), 2),
        "label": overall_label,
        "dimensions": {k: {"score": round(v["score"], 2), "label": v["label"]} for k,v in dimensions.items()},
        "attributes": {k: {"score": round(v["score"], 2), "label": v["label"]} for k,v in attributes.items()},
        "all_categories": {k: {"score": round(v["score"], 2), "label": v["label"]} for k,v in all_categories.items()},
        "feedback": {"summary": base_summary + (coaching.get("summary_note", "") if coaching else "")},
        "coaching": {k: coaching[k] for k in ("keep","change","action","drill")},
        "debug": debug,
    }

# ------------------------- adapter for routers/glmp.py -------------------------
def evaluate_glmp_payload(payload: Dict[str, Any], rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    meta = payload.get("meta") or {}
    mcq = payload.get("mcq")
    text = payload.get("text")
    return evaluate_glmp(meta=meta, mcq=mcq, text=text, rules=rules)
