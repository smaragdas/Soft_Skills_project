# app/core/db.py
from __future__ import annotations
from typing import Generator
from sqlmodel import SQLModel, Session, create_engine
from app.core.settings import settings

# 🔹 Import όλων των μοντέλων ώστε να “γραφτούν” στο metadata
from app import models  # noqa: F401
from app.models.answer import Answer  # noqa: F401

# 🔹 Κοινό engine για όλο το app (singleton)
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        # Παίρνουμε URL από .env ή πέφτουμε σε local SQLite για dev
        db_url = getattr(settings, "DATABASE_URL", "sqlite:///./softskills.db")

        # Για PostgreSQL (Neon), αποφεύγουμε broken connections
        connect_args = {}
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,  # αποφεύγει broken connections
            connect_args=connect_args,
        )

    return _engine


def init_db() -> None:
    """
    Δημιουργεί όλους τους πίνακες αν δεν υπάρχουν.
    Τρέχει στην εκκίνηση (π.χ. μέσα στο on_startup).
    """
    engine = get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency για injection μέσω Depends(get_session)
    """
    with Session(get_engine()) as session:
        yield session
