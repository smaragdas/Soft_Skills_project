SoftSkills User Quiz — README

Frontend quiz interface for users to answer open-ended and multiple-choice questions for soft skills evaluation.
Built with Vite + React + TypeScript, designed to work with the SoftSkills Bot (FastAPI) backend.

⸻

1️⃣ Installation & Local Run

Requirements
	•	Node.js 18+
	•	npm or yarn

Steps

cd softskills-user-quiz-2
npm install
npm run dev

Then open your browser at:

http://localhost:5173


⸻

2️⃣ API Configuration

By default, the quiz connects to:

http://localhost:8001/api/softskills

Change the API Base URL

Option 1: Edit .env
Create or modify the .env file:

VITE_API_BASE=https://your-backend-url

Option 2: Override from Browser Console

localStorage.setItem('API_BASE', 'https://your-backend-url');

Then refresh — the app will call:

<API_BASE>/api/softskills


⸻

3️⃣ Expected Endpoints

Method	Endpoint	Description
GET	/api/softskills/quiz/questions?category=Communication	Fetches quiz questions
POST	/api/softskills/quiz/submit	Submits quiz answers (JSON body with answers)
GET	/api/softskills/quiz/results?user_id=user123	Fetches user quiz results


⸻

4️⃣ Example User Flow
	1.	User opens the quiz link.
	2.	Selects a soft skill category (e.g., Communication, Leadership, Teamwork).
	3.	Answers open-ended or multiple-choice questions.
	4.	On submission, the app calls backend /score-open or /score-mc.
	5.	Results are saved and displayed to the user.

⸻

5️⃣ Build for Production

npm run build
npm run preview

Then deploy the dist/ folder to your static hosting provider (e.g., Netlify, Vercel, DigitalOcean).

⸻

6️⃣ Project Structure

softskills-user-quiz-2/
│
├── src/                  # React source files
│   ├── api/              # API service functions
│   ├── components/       # UI components (inputs, progress bar, etc.)
│   ├── pages/            # Pages (Home, Quiz, Results)
│   ├── hooks/            # Custom React hooks
│   └── utils/            # Helper functions
│
├── public/               # Static assets
├── .env                  # API base config
├── package.json          # Dependencies & scripts
├── vite.config.ts        # Build config
└── results.csv           # Optional sample output


⸻

7️⃣ Notes
	•	Backend (softskills-bot-v2-2) must be running for quiz evaluation.
	•	To reset the API URL cache:

localStorage.removeItem('API_BASE')


	•	Each user is uniquely identified via user_id (can be set automatically or manually in frontend).

⸻

Author

SoftSkills Research Project (v2.2)
Developed to collect and evaluate user responses using AI-assisted scoring for communication, teamwork, leadership, and problem-solving skills.