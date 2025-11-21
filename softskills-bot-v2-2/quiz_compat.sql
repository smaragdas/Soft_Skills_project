CREATE TABLE IF NOT EXISTS interaction (
  id          BIGSERIAL PRIMARY KEY,
  user_id     TEXT NOT NULL,
  question_id TEXT NOT NULL,
  category    TEXT,
  qtype       TEXT,          -- 'mc' / 'open'
  prompt      TEXT,
  answer      TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mc_eval (
  id             BIGSERIAL PRIMARY KEY,
  interaction_id BIGINT REFERENCES interaction(id) ON DELETE CASCADE,
  model          TEXT,
  llm_score      NUMERIC(4,3),
  raw            JSONB,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
