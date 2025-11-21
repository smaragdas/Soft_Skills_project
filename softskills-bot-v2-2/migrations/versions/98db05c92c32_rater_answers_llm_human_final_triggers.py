"""rater: answers, llm, human, final & triggers

Revision ID: 98db05c92c32
Revises: f17f681f4075
Create Date: 2025-10-14 09:51:02.707485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98db05c92c32'
down_revision: Union[str, Sequence[str], None] = 'f17f681f4075'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass


def upgrade():
    op.execute("""
-- 1) answers
CREATE TABLE IF NOT EXISTS answers (
  answer_id    UUID PRIMARY KEY,
  user_id      TEXT NOT NULL,
  question_id  TEXT NOT NULL,
  category     TEXT NOT NULL,
  qtype        TEXT NOT NULL,
  prompt       TEXT,
  answer       TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2) llm_scores
CREATE TABLE IF NOT EXISTS llm_scores (
  answer_id   UUID PRIMARY KEY REFERENCES answers(answer_id) ON DELETE CASCADE,
  llm_score   NUMERIC(4,3) NOT NULL,   -- 0..1
  scored_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3) human_ratings (δύο raters: teacher01, teacher02)
CREATE TABLE IF NOT EXISTS human_ratings (
  answer_id   UUID REFERENCES answers(answer_id) ON DELETE CASCADE,
  rater_id    TEXT NOT NULL CHECK (rater_id IN ('teacher01','teacher02')),
  score       NUMERIC(4,3) NOT NULL,   -- 0..1
  rated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (answer_id, rater_id)
);

-- 4) final_scores (υλικός πίνακας που κλειδώνει όταν υπάρχουν και οι δύο άνθρωποι)
CREATE TABLE IF NOT EXISTS final_scores (
  answer_id     UUID PRIMARY KEY REFERENCES answers(answer_id) ON DELETE CASCADE,
  user_id       TEXT NOT NULL,
  question_id   TEXT NOT NULL,
  category      TEXT NOT NULL,
  qtype         TEXT NOT NULL,
  llm_score     NUMERIC(4,3),          -- 0..1
  teacher01     NUMERIC(4,3),          -- 0..1
  teacher02     NUMERIC(4,3),          -- 0..1
  human_avg     NUMERIC(4,3),          -- 0..1
  final_score   NUMERIC(4,3),          -- 0..1 (με w=0.5 default)
  completed_at  TIMESTAMPTZ
);

-- function: αναυπολογίζει final όταν υπάρχουν και οι δύο άνθρωποι
CREATE OR REPLACE FUNCTION _recompute_final(aid UUID) RETURNS VOID AS $$
DECLARE
  s1 NUMERIC(4,3);
  s2 NUMERIC(4,3);
  l  NUMERIC(4,3);
  w  NUMERIC(4,3) := 0.5;  -- βάρος ανθρώπου (0..1), default 0.5
  a  answers%ROWTYPE;
  havg NUMERIC(4,3);
  fin  NUMERIC(4,3);
BEGIN
  SELECT * INTO a FROM answers WHERE answer_id = aid;
  IF NOT FOUND THEN RETURN; END IF;

  SELECT MAX(CASE WHEN rater_id='teacher01' THEN score END),
         MAX(CASE WHEN rater_id='teacher02' THEN score END)
  INTO s1, s2
  FROM human_ratings WHERE answer_id = aid;

  IF s1 IS NULL OR s2 IS NULL THEN
    RETURN;
  END IF;

  SELECT llm_score INTO l FROM llm_scores WHERE answer_id = aid;

  havg := (s1 + s2)/2.0;
  IF l IS NULL THEN
    fin := havg;
  ELSE
    fin := (1 - w)*l + w*havg;
  END IF;

  INSERT INTO final_scores AS f (
    answer_id, user_id, question_id, category, qtype,
    llm_score, teacher01, teacher02, human_avg, final_score, completed_at
  )
  VALUES (
    aid, a.user_id, a.question_id, a.category, a.qtype,
    l, s1, s2, havg, fin, now()
  )
  ON CONFLICT (answer_id) DO UPDATE SET
    user_id     = EXCLUDED.user_id,
    question_id = EXCLUDED.question_id,
    category    = EXCLUDED.category,
    qtype       = EXCLUDED.qtype,
    llm_score   = EXCLUDED.llm_score,
    teacher01   = EXCLUDED.teacher01,
    teacher02   = EXCLUDED.teacher02,
    human_avg   = EXCLUDED.human_avg,
    final_score = EXCLUDED.final_score,
    completed_at= EXCLUDED.completed_at;
END;
$$ LANGUAGE plpgsql;

-- trigger: μετά από insert/update ανθρώπινου score
CREATE OR REPLACE FUNCTION _trg_after_human_rating() RETURNS TRIGGER AS $$
BEGIN
  PERFORM _recompute_final(NEW.answer_id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_after_human_rating ON human_ratings;
CREATE TRIGGER trg_after_human_rating
AFTER INSERT OR UPDATE ON human_ratings
FOR EACH ROW EXECUTE FUNCTION _trg_after_human_rating();

-- trigger: μετά από insert/update LLM score
CREATE OR REPLACE FUNCTION _trg_after_llm_score() RETURNS TRIGGER AS $$
BEGIN
  PERFORM _recompute_final(NEW.answer_id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_after_llm_score ON llm_scores;
CREATE TRIGGER trg_after_llm_score
AFTER INSERT OR UPDATE ON llm_scores
FOR EACH ROW EXECUTE FUNCTION _trg_after_llm_score();

-- indexes
CREATE INDEX IF NOT EXISTS idx_answers_user ON answers(user_id);
CREATE INDEX IF NOT EXISTS idx_answers_category ON answers(category);
CREATE INDEX IF NOT EXISTS idx_answers_question ON answers(question_id);
    """)

def downgrade():
    op.execute("""
DROP TRIGGER IF EXISTS trg_after_llm_score ON llm_scores;
DROP TRIGGER IF EXISTS trg_after_human_rating ON human_ratings;
DROP FUNCTION IF EXISTS _trg_after_llm_score();
DROP FUNCTION IF EXISTS _trg_after_human_rating();
DROP FUNCTION IF EXISTS _recompute_final(UUID);
DROP TABLE IF EXISTS final_scores;
DROP TABLE IF EXISTS human_ratings;
DROP TABLE IF EXISTS llm_scores;
DROP TABLE IF EXISTS answers;
    """)
