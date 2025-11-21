-- core tables
CREATE TABLE IF NOT EXISTS answers(
  answer_id  UUID PRIMARY KEY,
  user_id    TEXT NOT NULL,
  question_id TEXT NOT NULL,
  category   TEXT,
  qtype      TEXT,
  prompt     TEXT,
  answer     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm_scores(
  answer_id  UUID PRIMARY KEY REFERENCES answers(answer_id) ON DELETE CASCADE,
  llm_score  NUMERIC(4,3) NOT NULL,
  scored_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS human_ratings(
  answer_id  UUID NOT NULL REFERENCES answers(answer_id) ON DELETE CASCADE,
  rater_id   TEXT NOT NULL CHECK (rater_id IN ('teacher01','teacher02')),
  score      NUMERIC(4,3) NOT NULL,
  rated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (answer_id, rater_id)
);

CREATE TABLE IF NOT EXISTS final_scores(
  answer_id   UUID PRIMARY KEY REFERENCES answers(answer_id) ON DELETE CASCADE,
  user_id     TEXT NOT NULL,
  question_id TEXT NOT NULL,
  category    TEXT,
  qtype       TEXT,
  llm_score   NUMERIC(4,3),
  teacher01   NUMERIC(4,3),
  teacher02   NUMERIC(4,3),
  human_avg   NUMERIC(4,3),
  final_score NUMERIC(4,3),
  completed_at TIMESTAMPTZ
);
