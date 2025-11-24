SoftSkills Bot v2.2 (FastAPI Backend)

Backend API for evaluating and scoring soft skills (open-ended and multiple-choice responses) using LLM + GLMP (Guided Linguistic Model Processing).

⸻

1. 🧩 Overview

This backend is part of the SoftSkills evaluation platform, designed to automatically rate open-ended answers using AI models, compute GLMP-based linguistic metrics, and manage teacher/human ratings for calibration and comparison.

⸻

2. ⚙️ Setup & Installation

Requirements
	•	Python 3.11+
	•	pip
	•	(Optional) virtualenv / venv

Installation Steps

cd softskills-bot-v2-2

# Create virtual environment
python -m venv .venv

# Activate environment
# Windows (PowerShell): .\.venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env  # (Windows: copy .env.example .env)

Environment Variables (.env)

Edit .env and set your variables:

API_KEY=supersecret123
DATABASE_URL=sqlite:///data.db
FASTAPI_ROOT_PATH=/prod
OPENAI_API_KEY=sk-xxxxxx


⸻

3. 🚀 Run Server

Start FastAPI with Uvicorn:

uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

Access:

http://127.0.0.1:8001


⸻

4. 🩺 Health & Docs

Health Check

GET /health

Example:

GET http://127.0.0.1:8001/health

API Documentation
	•	Swagger UI → http://127.0.0.1:8001/docs￼
	•	OpenAPI JSON → http://127.0.0.1:8001/openapi.json￼

⸻

5. 🔑 Authentication

Most routes require an API Key header:

x-api-key: <API_KEY>

Public Endpoints (no API key required):
	•	/health
	•	/docs
	•	/openapi.json

⸻

6. 🧠 Core Endpoints

6.1. Evaluate Open Answer (Legacy)

POST /score-open?save=true
Content-Type: application/json
x-api-key: <API_KEY>

Body:

{
  "category": "Communication",
  "question_id": "comm_q2",
  "text": "Το κείμενό σου εδώ",
  "user_id": "user123"
}

Returns: Auto-evaluation from LLM and optional feedback.

⸻

6.2. GLMP Evaluation (Current System)

POST /glmp/evaluate-and-save
Content-Type: application/json
x-api-key: <API_KEY>

Body:

{
  "meta": {
    "userId": "user123",
    "answerId": "lead_q1",
    "category": "Leadership",
    "modalities": ["text"]
  },
  "text": {
    "clarity": 8.3,
    "coherence": 8.1,
    "topic_relevance": 7.9,
    "vocabulary_range": 8.0,
    "raw": "Η απάντησή σου εδώ..."
  }
}

Response: Final GLMP score, sub-metrics, and suggestions.

⸻

6.3. Multiple Choice Evaluation

POST /score-mc?save=true&force_llm=true
Content-Type: application/json
x-api-key: <API_KEY>

Body:

{
  "user_id": "user123",
  "category": "Teamwork",
  "question_id": "mc_q1",
  "question_text": "Which behavior best supports collaboration?",
  "options": [
    { "id": "0", "text": "Ignoring teammates" },
    { "id": "1", "text": "Actively listening and supporting" }
  ],
  "selected_id": "1",
  "correct_id": "1"
}

Returns: MCQ accuracy and feedback.

⸻

7. 🧾 Rater Workflow (Human Evaluation)

7.1. Fetch Open Answers for Manual Rating

GET /rater/items?rater_id=r1&category=Communication&qtype=open&limit=5

7.2. Submit Human Ratings

POST /rater/submit
Content-Type: application/json
x-api-key: <API_KEY>

Body:

{
  "rater_id": "r1",
  "ratings": [
    { "answer_id": "abcd1234", "score": 4.5, "notes": "Καλή οργάνωση σκέψης." }
  ]
}


⸻

8. 📤 Data Export / Import

8.1. Export All to CSV

GET /export/all-csv?category=Communication&qtype=open&fmt=long

8.2. Export to Excel Template

GET /export/human-xlsx?category=Communication&qtype=open

8.3. Import from Excel (manual ratings)

POST /import/human-xlsx
Content-Type: multipart/form-data

Form fields:

file=@ratings.xlsx
rater_id=r1


⸻

9. 📊 Reliability Metrics

Compute inter-rater reliability statistics:

GET /metrics/reliability?category=Leadership&qtype=open


⸻

10. 📂 Project Structure

softskills-bot-v2-2/
│
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── routers/             # Route definitions (score, glmp, etc.)
│   ├── core/                # Fuzzy / GLMP logic
│   ├── config/              # GLMP weight rules
│   └── schemas/             # Pydantic models
│
├── data.db                 # Local SQLite database
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── Dockerfile              # Container configuration
├── README.md               # This documentation
└── scripts/                # Helper SQL / DB tools


⸻

11. 🧪 Development Quick Commands

# Reset local DB
python reset_db.py

# Run server (dev mode)
uvicorn app.main:app --reload

# Check health endpoint
curl http://127.0.0.1:8001/health

# Export results
curl -H "x-api-key: supersecret123" http://127.0.0.1:8001/export/all-csv


⸻

12. 📘 Notes
	•	Default API Key: supersecret123 (edit in .env)
	•	Default port: 8001
	•	Database defaults to data.db (SQLite)
	•	Compatible with rater-ui-new-2 and softskills-user-quiz-2 frontends

⸻

Author

SoftSkills Research Project (v2.2)
Developed for automated soft skill evaluation using NLP and hybrid scoring models (LLM + Fuzzy GLMP).

⸻
