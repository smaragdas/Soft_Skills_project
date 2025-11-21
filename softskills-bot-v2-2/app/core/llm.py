# app/core/llm.py
from __future__ import annotations

import json, re, math
from typing import Any, Dict, Optional, List
import httpx
from openai import OpenAI
from app.core.settings import settings

_CLIENT: Optional[OpenAI] = None

def _get_client() -> OpenAI:
    """OpenAI v1 client με explicit timeout."""
    global _CLIENT
    if _CLIENT is None:
        http_client = httpx.Client(timeout=30)
        _CLIENT = OpenAI(api_key=settings.OPENAI_API_KEY, http_client=http_client)
    return _CLIENT

# ---------------- Prompts ----------------

SYSTEM_OPEN = (
    "Είσαι ένας έμπειρος coach ανάπτυξης Soft Skills σε περιβάλλοντα επαγγελματικής εκπαίδευσης.\n"
    "ΠΡΕΠΕΙ να επιστρέφεις ΜΟΝΟ έγκυρο JSON (χωρίς κείμενο γύρω-γύρω), με ΑΚΡΙΒΩΣ τα πεδία που ζητούνται.\n"
    "\n"
    "ΚΡΙΤΗΡΙΑ ΒΑΘΜΟΛΟΓΗΣΗΣ (score 0..10):\n"
    "- 0–2: Η απάντηση είναι πολύ φτωχή ή σχεδόν άδεια: εκτός θέματος, μονολεκτική ή δεν απαντά καθόλου στο ζητούμενο.\n"
    "- 3–4: Η απάντηση είναι πολύ γενική ή θα μπορούσε να ταιριάζει σε πολλές ερωτήσεις, με ελάχιστα συγκεκριμένα σημεία.\n"
    "- 5–7: Καλή και σχετική απάντηση. Δείχνει κατανόηση του ζητήματος, περιέχει κάποιες συγκεκριμένες ιδέες/ενέργειες, αλλά δεν είναι πλήρως ανεπτυγμένη.\n"
    "- 8–10: Πολύ καλή/εξαιρετική, στοχευμένη απάντηση, με συγκεκριμένες ενέργειες/παραδείγματα που δείχνουν βαθιά κατανόηση και εφαρμόσιμα βήματα.\n"
    "\n"
    "ΟΔΗΓΙΕΣ ΚΛΙΜΑΚΑΣ:\n"
    "- Αν η απάντηση είναι κατανοητή, σχετική με την ερώτηση και περιέχει έστω μερικά πρακτικά σημεία, συνήθως ανήκει στην περιοχή 5–7.\n"
    "- Κράτα τις βαθμολογίες 0–4 για περιπτώσεις όπου η απάντηση είναι πολύ γενική, εκτός θέματος ή σχεδόν άδεια.\n"
    "- Χρησιμοποίησε 8–10 μόνο όταν η απάντηση είναι πραγματικά στοχευμένη, με σαφή δομή και συγκεκριμένα παραδείγματα/ενέργειες.\n"
    "\n"
    "Αν η απάντηση είναι αδύναμη ή εκτός θέματος, βαθμολόγησε χαμηλά αλλά ΔΩΣΕ ΣΥΓΚΕΚΡΙΜΕΝΟ coaching στα πεδία change/action/drill."
)

USER_OPEN = """Κατηγορία: {category}
Ερώτηση/ID: {question_id}

Απάντηση χρήστη:
{user_text}

ΒΑΘΜΟΛΟΓΗΣΕ την απάντηση σε κλίμακα 0..10, με βάση τα κριτήρια που σου δόθηκαν.
Πρόσεξε ειδικά αν η απάντηση:
- είναι πολύ γενική,
- θα μπορούσε να ταιριάζει αυτούσια ή σχεδόν αυτούσια σε πολλές διαφορετικές ερωτήσεις,
- δεν δίνει συγκεκριμένα παραδείγματα ή πρακτικά βήματα.

Σε αυτές τις περιπτώσεις χρησιμοποίησε χαμηλές βαθμολογίες (0–4).
Αν όμως η απάντηση είναι κατανοητή, σχετική με την ερώτηση και περιέχει έστω μερικές συγκεκριμένες ιδέες/ενέργειες,
τότε συνήθως ανήκει στην περιοχή 5–7 ή και παραπάνω, ανάλογα με το πόσο αναλυτική και στοχευμένη είναι.

ΕΠΕΣΤΡΕΨΕ ΜΟΝΟ το ΕΞΗΣ JSON:
{{
  "score": <ακέραιος 0..10>,
  "keep": "<1-2 προτάσεις, συγκεκριμένες δυνάμεις της απάντησης>",
  "change": "<1-2 προτάσεις, συγκεκριμένες αδυναμίες/τι να αλλάξει>",
  "action": "<ένα πρακτικό και μετρήσιμο επόμενο βήμα>",
  "drill": "<μία μικρή άσκηση για εξάσκηση>",
  "criteria": [
    {{ "name":"Clarity",   "score":0..10, "comment":"..." }},
    {{ "name":"Relevance", "score":0..10, "comment":"..." }},
    {{ "name":"Structure", "score":0..10, "comment":"..." }},
    {{ "name":"Examples",  "score":0..10, "comment":"..." }}
  ]
}}
"""

SYSTEM_MC = (
    "Είσαι coach soft skills. Για ερώτηση πολλαπλής επιλογής, εξήγησε ΠΑΙΔΑΓΩΓΙΚΑ τη διαφορά ανάμεσα στην επιλεγμένη και στη σωστή επιλογή: ποια αρχή/σκεπτικό λείπει, τι παρανόηση υπάρχει, και πώς να σκέφτεται την επόμενη φορά\n"
    "ΠΡΕΠΕΙ να επιστρέψεις ΜΟΝΟ έγκυρο JSON με τα πεδία που ζητούνται."
)

USER_MC = """Κατηγορία: {category}
MC Ερώτηση: {question_id}
Κείμενο Ερώτησης:
{question_text}

Επιλογές:
{options_block}

Επέλεξα: {selected_id} → "{selected_text}"
Σωστό:   {correct_id}  → "{correct_text}"

ΕΠΕΣΤΡΕΨΕ ΜΟΝΟ το ΕΞΗΣ JSON:
{{
  "score": <ακέραιος 0..10>,
  "keep": "<τι πήγε καλά (συγκεκριμένα)>",
  "change": "<τι να προσέξει/διορθώσει (συγκεκριμένα)>",
  "action": "<ένα πρακτικό βήμα που να εφαρμόζεται άμεσα>",
  "drill": "<μία μικρή άσκηση με βήματα/checklist>",
  "criteria": [
    {{ "name":"Understanding",  "score":0..10, "comment":"..." }},
    {{ "name":"Principles fit", "score":0..10, "comment":"..." }}
  ]
}}
"""

# ---------------- Helpers ----------------

def _safe_int010(x: Any, default: int = 0) -> int:
    try:
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            v = int(round(x))
            return max(0, min(10, v))
        if isinstance(x, str):
            m = re.search(r"-?\d+", x)
            if m:
                v = int(m.group())
                return max(0, min(10, v))
    except Exception:
        pass
    return default

def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    # ψάχνουμε απευθείας αντικείμενο
    s, e = text.find("{"), text.rfind("}")
    if 0 <= s < e:
        cand = text[s : e + 1]
        try:
            return json.loads(cand)
        except Exception:
            return None
    return None

def _normalize_open_payload(d: dict) -> dict:
    out = dict(d or {})
    out["score"]  = _safe_int010(out.get("score", 0), 0)
    # υποχρεωτικά πεδία coaching
    for k in ("keep", "change", "action", "drill"):
        v = (out.get(k) or "").strip()
        out[k] = v if v else "—"
    # criteria: φτιάξε πάντα τα 4 ζητούμενα (Clarity/Relevance/Structure/Examples)
    want = ["Clarity", "Relevance", "Structure", "Examples"]
    got  = {str((c or {}).get("name", "")).strip().lower(): c for c in (out.get("criteria") or []) if isinstance(c, dict)}
    crit: List[dict] = []
    for name in want:
        c = got.get(name.lower()) or {}
        crit.append({
            "name": name,
            "score": _safe_int010(c.get("score", 0), 0),
            "comment": (c.get("comment") or "—").strip() or "—"
        })
    out["criteria"] = crit
    return out

def _normalize_mc_payload(d: dict) -> dict:
    out = dict(d or {})
    out["score"]  = _safe_int010(out.get("score", 0), 0)
    for k in ("keep", "change", "action", "drill"):
        v = (out.get(k) or "").strip()
        out[k] = v if v else "—"
    # criteria: δύο θέλουμε
    want = ["Understanding", "Principles fit"]
    got  = {str((c or {}).get("name", "")).strip().lower(): c for c in (out.get("criteria") or []) if isinstance(c, dict)}
    crit: List[dict] = []
    for name in want:
        c = got.get(name.lower()) or {}
        crit.append({
            "name": name,
            "score": _safe_int010(c.get("score", 0), 0),
            "comment": (c.get("comment") or "—").strip() or "—"
        })
    out["criteria"] = crit
    return out

def _chat_json(messages: list[dict]) -> tuple[Optional[dict], Optional[str], Optional[str]]:
    """
    Κάνει κλήση στο OpenAI και επιστρέφει (json_dict, model_name, raw_text) ή (None, model, raw_text) σε αποτυχία.
    """
    client = _get_client()
    model_name = getattr(settings, "OPENAI_MODEL", None) or "gpt-4o-mini"
    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=getattr(settings, "OPENAI_TEMPERATURE", 0.3) or 0.3,
        )
        content = resp.choices[0].message.content
        data = _extract_json(content) or {}
        return data, getattr(resp, "model", model_name), content
    except Exception as e:
        # επιστρέφουμε raw error για debug
        return {"__error__": str(e)}, model_name, None

# ---------------- Public ----------------

def llm_coach_open(category: str, question_id: str, user_text: str) -> Dict[str, Any]:
    data, model_name, raw = _chat_json([
        {"role":"system","content": SYSTEM_OPEN},
        {"role":"user","content": USER_OPEN.format(category=category, question_id=question_id, user_text=user_text)}
    ])

    # Σφάλμα client
    if isinstance(data, dict) and data.get("__error__"):
        return {"error": data["__error__"], "model_name": model_name}

    if not isinstance(data, dict) or not data:
        return {"error": "empty_llm_response", "model_name": model_name, "raw": (raw[:500] if raw else None)}

    norm = _normalize_open_payload(data)
    # Αν όλα τα coaching πεδία είναι "—" και όλα τα scores 0 → θεωρούμε κακή απόκριση
    all_zero = norm["score"] == 0 and all(c["score"] == 0 for c in norm["criteria"])
    all_dash = all((norm[k] == "—") for k in ("keep","change","action","drill"))
    if all_zero and all_dash:
        return {"error": "unusable_llm_payload", "model_name": model_name, "raw": (raw[:500] if raw else None)}

    norm["model_name"] = model_name
    norm["_source"] = "llm"
    return norm

def llm_coach_mc(
    category: str,
    question_id: str,
    question_text: str,
    options: Dict[str, str],
    selected_id: str,
    correct_id: Optional[str],
) -> Dict[str, Any]:
    opts_lines = "\n".join([f"- {oid}: {otxt}" for oid, otxt in options.items()])
    selected_text = options.get(selected_id, "—")
    correct_text  = options.get(correct_id or "", "—")

    data, model_name, raw = _chat_json([
        {"role":"system","content": SYSTEM_MC},
        {"role":"user","content": USER_MC.format(
            category=category,
            question_id=question_id,
            question_text=question_text,
            options_block=opts_lines,
            selected_id=selected_id, selected_text=selected_text,
            correct_id=(correct_id or "—"), correct_text=correct_text,
        )}
    ])

    if isinstance(data, dict) and data.get("__error__"):
        return {"error": data["__error__"], "model_name": model_name}

    if not isinstance(data, dict) or not data:
        return {"error": "empty_llm_response", "model_name": model_name, "raw": (raw[:500] if raw else None)}

    norm = _normalize_mc_payload(data)
    all_zero = norm["score"] == 0 and all(c["score"] == 0 for c in norm["criteria"])
    all_dash = all((norm[k] == "—") for k in ("keep","change","action","drill"))
    if all_zero and all_dash:
        return {"error": "unusable_llm_payload", "model_name": model_name, "raw": (raw[:500] if raw else None)}

    norm["model_name"] = model_name
    norm["_source"] = "llm"
    return norm
