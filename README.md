SoftSkills FullStack Project 

An end-to-end AI-powered Soft Skills Assessment Platform built to evaluate, coach, and track learners’ development in communication, leadership, teamwork, and other soft skills.

This platform integrates AI-based scoring, human rater validation, and data analytics — designed for use in educational or corporate environments.

⸻

🧱 Components Overview

Component	Folder	Tech Stack	Description
Backend API	softskills-bot-v2-2/	FastAPI (Python)	Core AI scoring engine (OpenAI integration, database persistence, APIs)
Quiz UI	softskills-quiz-ui/	React + Vite	User interface where learners answer open & multiple-choice questions
Rater UI	softskills-rater-ui/	React + Vite	Instructor dashboard to review and validate AI scores
Database	PostgreSQL	SQL	Stores questions, answers, feedback, raters, and performance analytics


⸻

🧠 Key Features
	•	LLM-Powered Evaluation using GPT models for open-ended answers
	•	Automatic and Human Scoring Fusion — both AI and raters contribute to final grading
	•	Adaptive Feedback System offering personalized coaching (keep, change, action, drill)
	•	Performance Analytics and reliability metrics for instructors
	•	Modular Design — easily extendable categories, questions, and assessment types
	•	Full Dockerized Environment for consistent development & deployment

⸻

🏗️ System Architecture

┌────────────────────────────────────────────────────┐
│                    FRONTEND UIs                    │
│ ┌────────────────────────┐    ┌──────────────────┐ │
│ │  Quiz UI (Students)   │    │ Rater UI (Admin) │ │
│ └─────────────┬──────────┘    └─────────┬────────┘ │
└───────────────┼─────────────────────────┼──────────┘
                │                         │
                ▼                         ▼
         ┌─────────────────────────────────────────┐
         │     FastAPI Backend (softskills-bot)    │
         │   ├── /score-open                      │
         │   ├── /score-mc                        │
         │   ├── /rater/...                       │
         │   └── /glmp/evaluate-and-save          │
         └─────────────────────────────────────────┘
                │
                ▼
         ┌──────────────────────┐
         │  PostgreSQL Database │
         └──────────────────────┘


⸻

🐳 Docker Compose Setup (Full Stack)

Folder Structure

project-root/
├── softskills-bot-v2-2/        # FastAPI backend
├── softskills-quiz-ui/         # Quiz app
├── softskills-rater-ui/        # Rater dashboard
└── docker-compose.yml

docker-compose.yml

version: "3.9"

services:
  db:
    image: postgres:16
    container_name: softskills-db
    environment:
      POSTGRES_USER: softskills
      POSTGRES_PASSWORD: softskills
      POSTGRES_DB: softskills
    volumes:
      - db_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  api:
    build: ./softskills-bot-v2-2
    container_name: softskills-api
    env_file:
      - ./softskills-bot-v2-2/.env
    depends_on:
      - db
    ports:
      - "8001:8001"

  quiz-ui:
    build: ./softskills-quiz-ui
    container_name: softskills-quiz-ui
    environment:
      - VITE_API_BASE=http://api:8001
    depends_on:
      - api
    ports:
      - "5173:4173"

  rater-ui:
    build: ./softskills-rater-ui
    container_name: softskills-rater-ui
    environment:
      - VITE_API_BASE=http://api:8001
    depends_on:
      - api
    ports:
      - "4173:4173"

volumes:
  db_data:

Commands

# Build all services
docker compose build

# Start in detached mode
docker compose up -d

# Stop everything
docker compose down

# Reset database
docker compose down -v

Access Points

Service	URL	Description
Backend (FastAPI)	http://localhost:8001/api/softskills	Main API endpoints
Quiz UI	http://localhost:5173	Student quiz interface
Rater UI	http://localhost:4173	Instructor dashboard
PostgreSQL	localhost:5432	Database (softskills / softskills)


⸻

⚙️ Environment Variables (.env example)

API_KEY=supersecret123
DATABASE_URL=postgresql+psycopg2://softskills:softskills@db:5432/softskills
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o-mini
HEURISTIC_ONLY=false


⸻

🧩 API Overview

Core Endpoints

Endpoint	Method	Description
/score-open	POST	Evaluates open-ended user answers (AI + heuristic fusion)
/score-mc	POST	Evaluates multiple choice answers (AI or heuristic)
/glmp/evaluate-and-save	POST	Routes GLMP score data and saves results
/rater/inbox	GET	Fetches answers awaiting human review
/rater/rate	POST	Submits human rater evaluations
/export/...	GET	Exports results in CSV or Excel format
/metrics/reliability	GET	Calculates inter-rater reliability


⸻

🧍‍♀️ Quiz UI — Learner Interface

cd softskills-quiz-ui
npm install
npm run dev
# Open http://localhost:5173

Features:
	•	LLM feedback for open-ended questions (score, keep, change, action, drill)
	•	Dynamic difficulty per user level
	•	Secure tokenized access for multiple attempts

⸻

🧑‍🏫 Rater UI — Instructor Dashboard

cd softskills-rater-ui
npm install
npm run dev
# Open http://localhost:4173

Features:
	•	View AI-rated answers and manually override scores
	•	Filter by category, rater, or attempt
	•	Export all evaluations to Excel/CSV

⸻

🧠 AI Logic (Backend Internals)
	•	Hybrid Evaluation Engine: blends heuristic + GPT-based analysis
	•	Dynamic Prompts for contextualized scoring (category-based)
	•	Automatic Coaching Generation with structured JSON output
	•	Error Handling & Normalization to ensure consistent LLM output

⸻

📊 Data Model (simplified)

answers(
  answer_id UUID,
  user_id TEXT,
  category TEXT,
  question_id TEXT,
  answer TEXT,
  llm_score FLOAT,
  attempt INT,
  created_at TIMESTAMP
)

autorating(
  answer_id UUID,
  score FLOAT,
  feedback JSONB,
  coaching JSONB,
  model_name TEXT,
  created_at TIMESTAMP
)


⸻

🧰 Development Notes
	•	Built with FastAPI, SQLAlchemy, Vite + React, and PostgreSQL
	•	Integrates OpenAI API for dynamic feedback
	•	Uses Docker Compose for cross-platform deployment
	•	Frontends support .env or browser localStorage for API base override

⸻

☁️ Deployment Options

Platform	Recommended Use
Render	Free hosting for the FastAPI backend
Vercel	Fast deployment of frontends (Quiz & Rater UI)
DigitalOcean / AWS EC2	Complete containerized deployment


⸻

🔒 Security
	•	API key required for all backend routes (except health/docs)
	•	Optional JWT or study tokens for identifying users/raters
	•	CORS-enabled for frontend integrations

⸻

🧾 License & Author

Author: Konstantinos Smaragdas — Information Technology & Electronic Systems Engineering Student
Purpose: Research & educational tool exploring AI-based soft skills evaluation.

License: MIT © 2025
