# Rater UI — Quickstart

## 1) Install & Run (local)
```bash
npm install
npm run dev
# open http://localhost:5173
```

## 2) Configure API
By default, the app calls **http://localhost:8001** and automatically appends `/api/softskills`.

Ways to change the base:
- **.env**: set `VITE_API_BASE` before building/starting.
- **Browser localStorage (takes precedence)**:
  Open DevTools Console and run:
  ```js
  localStorage.setItem('API_BASE', 'https://YOUR-API-ORIGIN'); // no trailing slash
  ```
The app will use: `<API_BASE>/api/softskills`

## 3) Endpoints expected (examples)
- `GET  /api/softskills/rater/inbox?rater_id=raterA&limit=20`
- `POST /api/softskills/rater/rate` with JSON `{ answer_id, rater_id, score_rater }`
- `GET  /api/softskills/rater/recent?rater_id=raterA`

## 4) Build for production
```bash
npm run build
npm run preview
```
