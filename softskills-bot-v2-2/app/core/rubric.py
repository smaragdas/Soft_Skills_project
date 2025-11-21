# app/core/rubric.py
from textwrap import dedent

RUBRICS = {
    "Communication": {
        "dimensions": [
            ("Clarity", "Πόσο καθαρά εκφράζεται; Αποφεύγει jargon;"),
            ("Structure", "Έχει αρχή-μέση-τέλος, βήματα, σύνοψη;"),
            ("Audience_Awareness", "Προσαρμόζει επίπεδο και τόνο στο κοινό;"),
            ("Use_of_Examples", "Δίνει παραδείγματα/αναλογίες;"),
        ],
        "anchors": {
            1: "Ασαφής/ασύνδετος λόγος, πολύ jargon, χωρίς παραδείγματα.",
            3: "Μέτρια σαφήνεια/δομή, κάποια παραδείγματα, μικρές αστοχίες.",
            5: "Πολύ καθαρός, δομημένος, προσαρμοσμένος στο κοινό, καλά παραδείγματα."
        },
    },
    "Teamwork": {
        "dimensions": [
            ("Collaboration", "Συνεργασία/ακρόαση/στήριξη;"),
            ("Conflict_Resolution", "Χειρισμός διαφωνιών/feedback;"),
            ("Responsibility", "Ανάληψη ρόλων/υποχρεώσεων;"),
            ("Communication", "Διαφανής, τακτική επικοινωνία;"),
        ],
        "anchors": {
            1: "Χαμηλή συνεργασία, αποφυγή ευθυνών, κακή επικοινωνία.",
            3: "Βασική συνεργασία, μέτριος χειρισμός συγκρούσεων.",
            5: "Υψηλή συνεργασία, υπευθυνότητα, άριστη επικοινωνία."
        },
    },
    "Leadership": {
        "dimensions": [
            ("Vision", "Καθαρή κατεύθυνση/στόχοι;"),
            ("Decision_Making", "Τεκμηριωμένες αποφάσεις;"),
            ("Delegation", "Ανάθεση/ενδυνάμωση;"),
            ("Ethics_Trust", "Δεοντολογία και εμπιστοσύνη;"),
        ],
        "anchors": {
            1: "Ασαφές όραμα, παρορμητικές αποφάσεις, μηδενική ανάθεση.",
            3: "Κάποια κατεύθυνση, επαρκείς αποφάσεις/ανάθεση.",
            5: "Καθαρό όραμα, τεκμηρίωση, καλή ανάθεση, εμπιστοσύνη."
        },
    },
    "Problem Solving": {
        "dimensions": [
            ("Problem_Definition", "Ορισμός/κατανόηση προβλήματος;"),
            ("Approach", "Συστηματική ανάλυση/βήματα;"),
            ("Alternatives", "Εξετάζει επιλογές/ρίσκα;"),
            ("Evaluation", "Κριτήρια αξιολόγησης/μέτρηση;"),
        ],
        "anchors": {
            1: "Ασαφής ορισμός, άναρχη προσέγγιση, χωρίς κριτήρια.",
            3: "Επαρκής ορισμός, βασικά βήματα, λίγες εναλλακτικές.",
            5: "Άριστος ορισμός, δομημένη προσέγγιση, τεκμηρίωση/μέτρηση."
        },
    },
}

def build_prompt(category: str, question_id: str, user_answer: str) -> str:
    if category not in RUBRICS:
        raise ValueError(f"Unknown category '{category}'.")
    r = RUBRICS[category]
    dims = "\n".join([f"- {name}: {desc}" for (name, desc) in r["dimensions"]])
    anchors = "\n".join([f"{k}: {v}" for k, v in sorted(r["anchors"].items())])

    return dedent(f"""
    You are an expert rater of soft skills. Rate the user's answer STRICTLY using this rubric.

    CATEGORY: {category}
    QUESTION_ID: {question_id}

    DIMENSIONS:
    {dims}

    ANCHORS (overall score guidance):
    {anchors}

    RULES:
    - Return ONLY strict JSON, no preamble or code fences.
    - "score" MUST be a number in [1, 5] with step 0.5 (e.g., 1, 1.5, 2, ..., 5).
    - "confidence" MUST be in [0, 1].
    - "feedback_el" MUST be GREEK text, friendly tone, 1–2 sentences,
      with 1 SPECIFIC improvement suggestion linked to the dimensions above.
      Avoid jargon; speak in second person ("…θα βοηθούσε να…").
    - Keep it concise (≤ 60 words).
    - Consider all dimensions holistically; produce a single overall score.

    JSON SCHEMA:
    {{
      "score": number,      // 1..5 step 0.5
      "confidence": number, // 0..1
      "feedback_el": string
    }}

    USER_ANSWER:
    \"\"\"{user_answer.strip()[:4000]}\"\"\"
    """).strip()
