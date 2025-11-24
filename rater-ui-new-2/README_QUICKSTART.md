Rater UI — Quickstart Guide

Frontend interface for human raters to review and score open-ended soft skill answers.
Built with Vite + React + TypeScript.

⸻

1️⃣ Installation & Local Run

Requirements
	•	Node.js 18+
	•	npm or yarn

Steps

cd rater-ui-new-2
npm install
npm run dev

Then open your browser at:

http://localhost:5173


⸻

2️⃣ API Configuration

By default, the Rater UI expects the backend to run at:

http://localhost:8001/api/softskills

Change the API Base URL

Option 1: Using .env
Create or edit the .env file in the project root and set:

VITE_API_BASE=https://your-backend-url

Option 2: Override via Browser Console
(Overrides .env and build defaults)

localStorage.setItem('API_BASE', 'https://your-backend-url');

Then refresh the page — the app will use:

<API_BASE>/api/softskills


⸻

3️⃣ API Endpoints (Expected by Rater UI)

Method	Endpoint	Description
GET	/api/softskills/rater/inbox?rater_id=raterA&limit=20	Fetches next batch of answers for rating
POST	/api/softskills/rater/rate	Submits a rater score (JSON body: { answer_id, rater_id, score_rater })
GET	/api/softskills/rater/recent?rater_id=raterA	Lists recently rated answers


⸻

4️⃣ Build for Production

npm run build
npm run preview

Then serve the /dist folder via any static hosting service (S3, Netlify, Vercel, etc.).

⸻

5️⃣ Project Structure

rater-ui-new-2/
│
├── src/                  # React components & logic
│   ├── api/              # API service calls
│   ├── components/       # UI components
│   ├── pages/            # Main pages (Inbox, History, etc.)
│   └── utils/            # Helpers & config
│
├── public/               # Static assets
├── .env                  # API configuration
├── package.json          # Dependencies & scripts
├── vite.config.ts        # Build config
└── results.csv           # (optional) example export file


⸻

6️⃣ Notes
	•	Make sure the backend (softskills-bot-v2-2) runs before starting the UI.
	•	You can clear cached API base by running:

localStorage.removeItem('API_BASE')


	•	Supports multiple raters — each identified by rater_id.

⸻

Author: SoftSkills Research Team (v2.2)
Purpose: Provide a lightweight UI for human raters to validate or compare LLM-generated scores.