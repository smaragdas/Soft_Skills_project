# app/core/coach.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import math

# ---- μικρά utils ----
def _safe_num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _mean(xs: List[float]) -> float:
    xs = [float(x) for x in xs if x is not None]
    return sum(xs)/len(xs) if xs else 0.0

# ---- aggregation πάνω στα 16 αποτελέσματα ----
def aggregate_session(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    results: [{category, type, score, ... , (προαιρετικά) coaching.criteria, dimensions}, ...]
    Επιστρέφει μέσους όρους ανά διάσταση & criterion όπου υπάρχει υλικό.
    """
    # dimensions keys όπως τα βγάζει ο GLMP
    dim_keys = ["Knowledge_Decision", "Content_Structure", "Delivery_Presence"]
    dim_vals: Dict[str, List[float]] = {k: [] for k in dim_keys}

    # criteria από LLM coaching (αν υπάρχουν)
    crit_names = ["Clarity", "Relevance", "Structure", "Examples"]
    crit_vals: Dict[str, List[float]] = {k: [] for k in crit_names}

    # γεμίζουμε από κάθε result
    for r in results or []:
        dims = (r.get("dimensions") or r.get("result", {}).get("dimensions") or {})
        for dk in dim_keys:
            v = _safe_num((dims.get(dk) or {}).get("score", None), None)
            if v is not None:
                dim_vals[dk].append(v)

        # coaching.criteria μπορεί να είναι στο r ή στο r["result"]
        coaching = r.get("coaching") or r.get("result", {}).get("coaching") or {}
        crit_list = coaching.get("criteria")
        if isinstance(crit_list, list):
            for c in crit_list:
                name = str(c.get("name") or "").strip()
                if name in crit_vals:
                    crit_vals[name].append(_safe_num(c.get("score"), None))

    # μέσοι όροι
    dim_avg = {k: round(_mean(v), 2) if v else None for k, v in dim_vals.items()}
    crit_avg = {k: round(_mean(v), 2) if v else None for k, v in crit_vals.items()}

    return {
        "dimensions": dim_avg,
        "criteria": crit_avg,
    }

def pick_weakest(aggr: Dict[str, Any]) -> Tuple[str, str, float]:
    """
    Επιστρέφει (kind, name, value) με το χαμηλότερο συστηματικό σημείο.
    kind in {"dimension","criterion"}.
    Αν υπάρχουν και τα δύο, προτιμάμε criterion (πιο χειρουργικό coaching).
    """
    dims = aggr.get("dimensions") or {}
    crit = aggr.get("criteria") or {}

    # βρες min criterion (αν υπάρχει)
    crit_items = [(k, v) for k, v in crit.items() if isinstance(v, (int, float))]
    dim_items  = [(k, v) for k, v in dims.items() if isinstance(v, (int, float))]

    if crit_items:
        name, val = min(crit_items, key=lambda kv: kv[1])
        return ("criterion", name, float(val))
    if dim_items:
        name, val = min(dim_items, key=lambda kv: kv[1])
        return ("dimension", name, float(val))
    return ("dimension", "Content_Structure", 0.0)  # ασφαλές default

# ---- Heuristic fallback plan ----
def make_heuristic_session_plan(kind: str, name: str, value: float) -> Dict[str, Any]:
    """
    Απλό, χειρουργικό πλάνο 3 βημάτων με micro-drill & rationale, χωρίς LLM.
    """
    rationale = f"Το ασθενέστερο σημείο της συνεδρίας ήταν το '{name}' ({value:.2f}/10)."

    if kind == "criterion":
        # custom tips ανά criterion
        if name == "Clarity":
            steps = [
                "Ξαναγράψε μια απάντησή σου σε 2 προτάσεις: Πλαίσιο → Απόφαση.",
                "Αφαίρεσε 2 λέξεις-βάρος (π.χ. επιρρήματα) ανά πρόταση.",
                "Κλείσε με 1 μετρήσιμο αποτέλεσμα (νούμερο ή 'σε Χ ημέρες').",
            ]
            drill = "Micro-drill: Πάρε 1 απάντηση & κάν’ την ‘tweet-length’ (<= 280 χαρακτήρες) χωρίς να χαθεί νόημα."
            resources = [
                {"title": "Plain language quick guide", "url": "https://www.plainlanguage.gov/guidelines/"},
            ]
        elif name == "Structure":
            steps = [
                "Χρησιμοποίησε σχήμα: Κατάσταση → Επιλογές → Απόφαση → Αποτέλεσμα.",
                "Βάλε επικεφαλίδες/κουκκίδες για τα 2–3 βασικά σημεία.",
                "Κλείσε με 1 post-mortem μάθημα (τι κρατάς).",
            ]
            drill = "Micro-drill: Σπάσε μια απάντηση σε 3 bullets με 7–9 λέξεις το καθένα."
            resources = [
                {"title": "Pyramid Principle (overview)", "url": "https://www.strategyu.co/pyramid-principle/"},
            ]
        elif name == "Relevance":
            steps = [
                "Υπογράμμισε τις λέξεις-κλειδιά της ερώτησης.",
                "Απάντησε πρώτα σε αυτές ρητά με 1 πρόταση.",
                "Πρόσθεσε 1 παράδειγμα αυστηρά σχετικό με το ζητούμενο.",
            ]
            drill = "Micro-drill: Γράψε μια πρόταση που ξεκινά με: “Ζητάς Χ, η απάντηση είναι Ψ γιατί…”"
            resources = [
                {"title": "Answering to the prompt", "url": "https://writingcenter.unc.edu/tips-and-tools/understanding-assignments/"},
            ]
        elif name == "Examples":
            steps = [
                "Δώσε 1 συγκεκριμένο περιστατικό (ποιος/πότε/πού).",
                "Πες τι έκανες & ποιο αποτέλεσμα είχε (νούμερο/χρονικό).",
                "Σύνδεσέ το με την αρχή/δεξιότητα (γιατί είναι σχετικό).",
            ]
            drill = "Micro-drill: Γράψε μίνι-‘case’ 3 προτάσεων για ένα λάθος & τι έμαθες."
            resources = [
                {"title": "STAR method", "url": "https://www.themuse.com/advice/star-interview-method"},
            ]
        else:
            steps = [
                "Διάλεξε 1 απάντηση που σου φαίνεται αδύναμη.",
                "Εφάρμοσε το σχήμα: Πλαίσιο → Απόφαση → Αποτέλεσμα.",
                "Πρόσθεσε 1 νούμερο/μετρική και 1 micro-μάθημα.",
            ]
            drill = "Micro-drill: Μείωσε 10% το μήκος χωρίς απώλεια πληροφορίας."
            resources = []
    else:
        # dimension-level generic
        if name == "Content_Structure":
            steps = [
                "Γράψε πρώτα τον ‘σκελετό’ (3 bullets) πριν το κείμενο.",
                "Κάθε bullet → 1 πρόταση με ρήμα δράσης.",
                "Κλείσε με 1 ‘so what’ (τι αλλάζει/μαθαίνεις).",
            ]
            drill = "Micro-drill: Μετέτρεψε μια απάντηση σε 3 bullets & σύνοψη 1 πρότασης."
            resources = []
        elif name == "Knowledge_Decision":
            steps = [
                "Δήλωσε ρητά το κριτήριο απόφασης (κόστος/ρίσκο/ταχύτητα).",
                "Σύγκρινε 2 εναλλακτικές με 1 πρόταση η καθεμία.",
                "Κλείσε με 1 μετρικό αποτέλεσμα/δοκιμή (A/B ή μικρό πείραμα).",
            ]
            drill = "Micro-drill: Γράψε μια πρόταση: “Αποφάσισα Χ διότι κριτήριο ήταν Ψ, αποφεύγοντας Ω.”"
            resources = []
        else:  # Delivery_Presence
            steps = [
                "Κράτα προτάσεις <= 18 λέξεις.",
                "Άλλαξε 2 γενικόλογα επίθετα με συγκεκριμένους όρους.",
                "Χρησιμοποίησε ενεργητική σύνταξη σε 2 σημεία.",
            ]
            drill = "Micro-drill: Αντικατάστησε ‘καλύτερα’/‘σωστά’ με 1 μετρήσιμο όρο."
            resources = []

    return {
        "overview": rationale,
        "weakest_area": {"type": kind, "name": name, "score": round(float(value),2)},
        "steps": steps[:3],
        "practice": drill,
        "resources": resources
    }
