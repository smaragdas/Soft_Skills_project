# app/main.py
from __future__ import annotations
import os
from typing import List, Dict, Any

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

# --- Settings / DB ---
from sqlalchemy import text
from sqlmodel import Session
from app.core.settings import settings
from app.core.db import init_db, get_session

# --- Routers ---
from app.routers.questions import router as questions_router
from app.routers.score import router as score_router
from app.routers.diag import router as diag_router
from app.routers.glmp import router as glmp_router
from app.routers import (
    rater_final,
    glmp,
    coach,
    report,
    report_simple,
    rules,
    diagnostics,
    rater_calibrate,
)
from app.routers.rater_simple import router as rater_simple_router

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
API_PREFIX = "/api/softskills"
ROOT_PATH = os.getenv("FASTAPI_ROOT_PATH", "")   # π.χ. "/prod"
BUILD_TAG = os.getenv("BUILD_TAG", "dev")        # για έλεγχο σωστού image

app = FastAPI(
    title=getattr(settings, "PROJECT_NAME", "softskills-bot"),
    version=getattr(settings, "VERSION", "1.0.0"),
    root_path=ROOT_PATH,
)

# -----------------------------------------------------------------------------
# CORS
# -----------------------------------------------------------------------------
ALLOW_ALL_CORS = bool(getattr(settings, "ALLOW_ALL_CORS", False) or getattr(settings, "DEBUG", True))

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5174", "http://localhost:5174",
    "http://127.0.0.1:5177", "http://localhost:5177",
    "http://127.0.0.1:8001", "http://localhost:8001",
    "http://127.0.0.1:5500", "http://localhost:5500",
    "http://127.0.0.1:5501", "http://localhost:5501",
    "http://softskills-quiz-ihu.s3-website.eu-central-1.amazonaws.com",
    "https://softskills-quiz-ihu.s3-website.eu-central-1.amazonaws.com",
]
LOCALHOST_REGEX = r"http://(localhost|127\.0\.0\.1):\d+$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ALLOW_ALL_CORS else ALLOWED_ORIGINS,
    allow_origin_regex=LOCALHOST_REGEX if not ALLOW_ALL_CORS else ".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# -----------------------------------------------------------------------------
# JSON UTF-8 middleware
# -----------------------------------------------------------------------------
@app.middleware("http")
async def force_utf8_content_type(request: Request, call_next):
    response = await call_next(request)
    ct = response.headers.get("content-type", "")
    if "application/json" in ct.lower() and "charset=" not in ct.lower():
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# -----------------------------------------------------------------------------
# Legacy (optional)
# -----------------------------------------------------------------------------
try:
    from app.routers.score import legacy_router as score_legacy_router  # type: ignore
    _HAVE_LEGACY = True
except Exception as e:
    print("LEGACY ROUTER IMPORT WARN:", e)
    score_legacy_router = None  # type: ignore
    _HAVE_LEGACY = False

# -----------------------------------------------------------------------------
# Register routers
# -----------------------------------------------------------------------------
app.include_router(glmp.router,            prefix=API_PREFIX)
app.include_router(coach.router,           prefix=API_PREFIX)
app.include_router(rules.router,           prefix=API_PREFIX)
app.include_router(rater_calibrate.router, prefix=API_PREFIX)
app.include_router(report.router,          prefix=API_PREFIX)
app.include_router(diagnostics.router)
app.include_router(rater_final.router,     prefix=API_PREFIX)
app.include_router(questions_router,       prefix=API_PREFIX)
app.include_router(score_router,           prefix=API_PREFIX)
app.include_router(rater_simple_router,    prefix=API_PREFIX)
app.include_router(diag_router, prefix="/api/softskills")

# 👉 quiz_complete router με “θορυβώδες” import
try:
    from app.routers.quiz_complete import router as quiz_router
    app.include_router(quiz_router, prefix=API_PREFIX)
    print(f"[BOOT] quiz_complete router INCLUDED at {API_PREFIX}/quiz/*")
except Exception as e:
    print("[BOOT] quiz_complete IMPORT/INCLUDE FAILED:", repr(e))

# Optional legacy χωρίς prefix
ENABLE_LEGACY_NO_PREFIX = True
if ENABLE_LEGACY_NO_PREFIX:
    app.include_router(questions_router)
    app.include_router(score_router)
    if _HAVE_LEGACY and score_legacy_router:
        app.include_router(score_legacy_router)

# -----------------------------------------------------------------------------
# Health / Debug
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "ok": True,
        "service": "softskills-bot",
        "prefix": API_PREFIX,
        "docs": "/docs",
        "redoc": "/redoc",
        "build": BUILD_TAG,
    }

@app.get("/healthz")
def health():
    return {"ok": True}

@app.get(f"{API_PREFIX}/ping")
def ping():
    return {"ok": True, "prefix": API_PREFIX}

# Inline διαγνωστικό endpoint (σίγουρα φαίνεται αν το build είναι νέο)
@app.get(f"{API_PREFIX}/quiz/hello-inline")
def hello_inline():
    return {"ok": True, "build": BUILD_TAG}

@app.get(f"{API_PREFIX}/_routes")
def list_routes(request: Request):
    out: List[Dict[str, Any]] = []
    for r in request.app.router.routes:
        try:
            out.append({"path": r.path, "methods": sorted(list(getattr(r, "methods", [])))})
        except Exception:
            out.append({"path": str(r)})
    return out

# -----------------------------------------------------------------------------
# Quiz Aliases (όπως τα είχες)
# -----------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/quiz/bundle")
def quiz_bundle_alias(session: Session = Depends(get_session)):
    rows = session.execute(text("""
        SELECT DISTINCT ON (question_id)
               question_id AS id,
               COALESCE(NULLIF(prompt, ''), '[no question text]') AS text,
               COALESCE(category, '') AS category,
               COALESCE(qtype, '')    AS qtype
        FROM answers
        WHERE question_id IS NOT NULL
        ORDER BY question_id, created_at DESC
    """)).mappings().all()

    items = [{
        "id": r["id"],
        "text": r["text"],
        "category": r["category"],
        "qtype": r["qtype"],
        "options": [],
    } for r in rows]

    return {"items": items}

@app.get(f"{API_PREFIX}/quiz/questions")
def quiz_questions_alias(session: Session = Depends(get_session)):
    rows = session.execute(text("""
        SELECT DISTINCT ON (question_id)
               question_id AS id,
               COALESCE(NULLIF(prompt, ''), '[no question text]') AS text,
               COALESCE(category, '') AS category,
               COALESCE(qtype, '')    AS qtype
        FROM answers
        WHERE question_id IS NOT NULL
        ORDER BY question_id, created_at DESC
    """)).mappings().all()

    items = []
    qmap = {}
    for r in rows:
        obj = {
            "id": r["id"],
            "text": r["text"],
            "category": r["category"],
            "qtype": r["qtype"],
            "options": [],
        }
        items.append(obj)
        qmap[r["id"]] = {k: v for k, v in obj.items() if k != "id"}

    return {"items": items, "map": qmap}

# -----------------------------------------------------------------------------
# Global exception handler
# -----------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "internal_error", "detail": str(exc)},
    )

# -----------------------------------------------------------------------------
# Startup
# -----------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    init_db()

# -----------------------------------------------------------------------------
# Lambda handler
# -----------------------------------------------------------------------------
handler = Mangum(app)
