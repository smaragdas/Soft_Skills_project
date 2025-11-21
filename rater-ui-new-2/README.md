
# Rater UI — Improved

A lean React + Vite + TS interface for teacher ratings.

## Setup
1. Copy `.env.example` to `.env` and adjust `VITE_API_BASE` if needed.
2. Install deps:
   ```bash
   npm i
   npm run dev
   ```
   It will run on http://127.0.0.1:5177

## Usage
- Set your **Rater ID** at the top. It's saved locally.
- Filters for category, type, LLM presence, and search.
- Select an item from the left list to open the rating pane.
- Use **slider** or keyboard (**1..9**, **0** for 1.0) to set score.
- **S** to queue the rating, **N** to go to the next item.
- Submit all queued ratings with **Submit Queue**.
- Click **Compare with LLM** to see final score blending (0.5 weight).
- **Export CSV** exports the current filtered list with LLM scores.
