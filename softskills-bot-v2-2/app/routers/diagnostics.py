# app/routers/diagnostics.py
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from sqlalchemy import text, inspect
from uuid import uuid4
from datetime import datetime
import platform, sys, traceback
from app.core.llm import llm_coach_open
from app.core.settings import settings
from app.core.db import get_session, init_db
from app.core.config import settings
from app.models.db_models import Interaction, AutoRating

router = APIRouter(prefix="/_diag", tags=["_diag"])


@router.get("/ping")
def ping():
    return {"ok": True}


@router.get("/env")
def env_info():
    import sqlalchemy, sqlmodel, numpy
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "sqlalchemy": sqlalchemy.__version__,
        "sqlmodel": sqlmodel.__version__,
        "numpy": numpy.__version__,
    }


@router.get("/config")
def config_info():
    key = (settings.OPENAI_API_KEY or "")
    masked = ("*" * max(0, len(key) - 8)) + key[-8:] if key else ""
    return {
        "PROJECT_NAME": getattr(settings, "PROJECT_NAME", "softskills-bot"),
        "DATABASE_URL": settings.DATABASE_URL,
        "API_KEY_len": len(settings.API_KEY or ""),
        "OPENAI_MODEL": settings.OPENAI_MODEL,
        "OPENAI_TEMPERATURE": settings.OPENAI_TEMPERATURE,
        "OPENAI_BASE_URL": settings.OPENAI_BASE_URL,
        "OPENAI_API_KEY_masked": masked,
        "LLM_configured": bool(settings.OPENAI_API_KEY),
    }


@router.post("/init-db")
def force_init_db():
    try:
        init_db()
        return {"ok": True, "message": "init_db() called"}
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": traceback.format_exc().splitlines()[-5:]}


@router.get("/tables")
def list_tables(session: Session = Depends(get_session)):
    bind = session.get_bind()
    insp = inspect(bind)
    dialect = bind.dialect.name  # 'postgresql' | 'sqlite' | ...

    result = {"ok": True, "dialect": dialect, "schemas": {}, "views": {}}

    if dialect == "postgresql":
        # αγνοούμε system schemas
        for sch in insp.get_schema_names():
            if sch in ("pg_catalog", "information_schema"):
                continue
            result["schemas"][sch] = insp.get_table_names(schema=sch)
            try:
                result["views"][sch] = insp.get_view_names(schema=sch)
            except Exception:
                result["views"][sch] = []
    else:
        # sqlite / άλλα
        result["schemas"]["default"] = insp.get_table_names()
        try:
            result["views"]["default"] = insp.get_view_names()
        except Exception:
            result["views"]["default"] = []

    return result


@router.get("/autorating-schema")
def autorating_schema(session: Session = Depends(get_session)):
    """
    Δείχνει το schema του autorating (PRAGMA table_info).
    """
    try:
        rows = session.exec(text("PRAGMA table_info('autorating');")).all()
        # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
        out = [
            {
                "cid": r[0],
                "name": r[1],
                "type": r[2],
                "notnull": r[3],
                "default": r[4],
                "pk": r[5],
            }
            for r in rows
        ]
        return {"ok": True, "columns": out}
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": traceback.format_exc().splitlines()[-5:]}


@router.post("/migrate/autorating-columns")
def migrate_autorating_columns(session: Session = Depends(get_session)):
    """
    Ενοποιημένο migration για autorating:
    - confidence  REAL
    - model_name  VARCHAR(255)
    - feedback    TEXT
    - coaching    TEXT
    - created_at  TIMESTAMP  (γεμίζει για τα παλιά rows με CURRENT_TIMESTAMP)

    Ασφαλές να τρέχει πολλές φορές (idempotent).
    """
    try:
        cols = session.exec(text("PRAGMA table_info('autorating');")).all()
        colnames = {c[1] for c in cols}

        def add_col(name: str, ddl_type: str):
            session.exec(text(f"ALTER TABLE autorating ADD COLUMN {name} {ddl_type};"))

        changed = False

        if "confidence" not in colnames:
            add_col("confidence", "REAL")
            changed = True

        if "model_name" not in colnames:
            add_col("model_name", "VARCHAR(255)")
            changed = True

        if "feedback" not in colnames:
            add_col("feedback", "TEXT")
            changed = True

        if "coaching" not in colnames:
            add_col("coaching", "TEXT")
            changed = True

        if "created_at" not in colnames:
            # Δεν μπορούμε εύκολα να ορίσουμε NOT NULL + DEFAULT σε ALTER στο SQLite.
            # Προσθέτουμε τη στήλη και γεμίζουμε τα NULL.
            add_col("created_at", "TIMESTAMP")
            session.exec(text("UPDATE autorating SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;"))
            changed = True

        session.commit()

        # Επιστρέφουμε το τελικό schema
        final_cols = session.exec(text("PRAGMA table_info('autorating');")).all()
        out = [
            {
                "cid": r[0],
                "name": r[1],
                "type": r[2],
                "notnull": r[3],
                "default": r[4],
                "pk": r[5],
            }
            for r in final_cols
        ]
        return {"ok": True, "changed": changed, "columns": out}
    except Exception as e:
        session.rollback()
        return {"ok": False, "error": str(e), "trace": traceback.format_exc().splitlines()[-5:]}


@router.post("/db-roundtrip")
def db_roundtrip(session: Session = Depends(get_session)):
    """
    Γρήγορο insert -> select γύρισμα, για να βεβαιώσουμε ότι
    οι πίνακες είναι ΟΚ και ότι το autorating δέχεται created_at.
    """
    try:
        ans_id = f"diag_{uuid4().hex[:8]}"
        inter = Interaction(
            answer_id=ans_id,
            category="Diag",
            qtype="open",
            question_id="diag",
            text_raw="test",
        )
        auto = AutoRating(
            answer_id=ans_id,
            score=3.0,
            model_name="diag",
            confidence=0.7,
            feedback=None,
            coaching=None,
            created_at=datetime.utcnow(),  # 👈 γεμίζουμε ρητά τη NOT NULL στήλη
        )
        session.add(inter)
        session.add(auto)
        session.commit()

        found = session.exec(select(Interaction).where(Interaction.answer_id == ans_id)).all()
        return {"ok": True, "inserted_answer_id": ans_id, "found": len(found)}
    except Exception as e:
        session.rollback()
        return {"ok": False, "error": str(e), "trace": traceback.format_exc().splitlines()[-5:]}
@router.get("/llm-health")
def llm_health():
    if not settings.OPENAI_API_KEY:
        return {"ok": False, "error": "No OPENAI_API_KEY configured"}
    try:
        out = llm_coach_open("Communication", "diag", "Θα δώσω ένα μικρό παράδειγμα για να ελέγξω το LLM.")
        return {"ok": True, "model": out.get("model_name"), "feedback": out.get("feedback"), "coaching": out.get("coaching")}
    except Exception as e:
        return {"ok": False, "error": str(e)}