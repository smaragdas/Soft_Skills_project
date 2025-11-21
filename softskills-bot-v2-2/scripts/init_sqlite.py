# scripts/init_sqlite.py
from sqlmodel import create_engine
from sqlalchemy import text
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///softskills.db")

DDL = """
CREATE TABLE IF NOT EXISTS interaction (
  id TEXT PRIMARY KEY,
  answer_id TEXT NOT NULL,
  category TEXT,
  qtype TEXT,
  question_id TEXT,
  text TEXT,
  text_raw TEXT,
  user_id TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS autorating (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  answer_id TEXT NOT NULL,
  score REAL,
  confidence REAL,
  model_name TEXT,
  feedback TEXT,
  coaching TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS humanrating (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  answer_id TEXT NOT NULL,
  rater_id TEXT NOT NULL,
  score REAL NOT NULL,
  notes TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_humanrating_answer_rater ON humanrating(answer_id, rater_id);
CREATE INDEX IF NOT EXISTS idx_interaction_created ON interaction(created_at);
"""

engine = create_engine(DATABASE_URL, echo=True)
with engine.begin() as conn:
    for stmt in filter(None, DDL.split(";\n")):
        conn.execute(text(stmt))
print("✅ Schema ensured.")
