# softskills-bot (FastAPI)

## Setup (Windows / PowerShell)
```powershell
cd C:\Users\kosta\softskills-bot
python -m venv .venv311
.\.venv311\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# (προαιρετικά άλλαξε API_KEY στο .env)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --log-level debug
# ή με hot reload: uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## Quick health
```
GET http://127.0.0.1:8001/health
```

## Seed open answers
```powershell
$seed = @(
  @{ category="Communication"; question_id="comm_open1"; text="Θα αποφύγω jargon, θα δώσω βήματα και σύνοψη."; user_id="kosta" },
  @{ category="Communication"; question_id="comm_open2"; text="Πρώτα ρωτάω το κοινό τι ξέρει, μετά εξηγώ με παραδείγματα και κλείνω με σύνοψη."; user_id="kosta" },
  @{ category="Communication"; question_id="comm_open3"; text="Χωρίζω σε βήματα, δίνω πρακτικά παραδείγματα και αποφεύγω τεχνικούς όρους όταν δεν χρειάζεται."; user_id="kosta" }
)
$seed | ForEach-Object {
  $json = $_ | ConvertTo-Json -Depth 5
  Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/score-open?save=true" `
    -Method POST `
    -ContentType "application/json; charset=utf-8" `
    -Headers @{ 'x-api-key'='supersecret123' } `
    -Body $json
}
```

## Rater workflow
- Fetch items:
```
GET /rater/items?rater_id=r1&category=Communication&qtype=open&limit=5
```
- Submit scores:
```
POST /rater/submit
{
  "rater_id": "r1",
  "ratings": [
    {"answer_id":"<id>", "score":4.0, "notes":"..."}
  ]
}
```

## Exports
- Excel template: `GET /export/human-xlsx?category=Communication&qtype=open`
- Import from Excel: `POST /import/human-xlsx` (multipart form: `file=@...xlsx`, `rater_id=r1`)
- **All to CSV**: `GET /export/all-csv?category=Communication&qtype=open&fmt=long` (ή `fmt=wide`)

## Reliability
```
GET /metrics/reliability?category=Communication&qtype=open
```

## Env
- API key header: `x-api-key: <API_KEY>` (skip only for `/health`, `/docs`, `/openapi.json`)
