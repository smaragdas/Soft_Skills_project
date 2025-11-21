CREATE TABLE IF NOT EXISTS autorating (
  id             BIGSERIAL PRIMARY KEY,
  interaction_id BIGINT REFERENCES interaction(id) ON DELETE CASCADE,
  model          TEXT,
  llm_score      NUMERIC(4,3),
  raw            JSONB,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Προαιρετικό index για γρήγορα lookups
CREATE INDEX IF NOT EXISTS idx_autorating_interaction
  ON autorating (interaction_id);
