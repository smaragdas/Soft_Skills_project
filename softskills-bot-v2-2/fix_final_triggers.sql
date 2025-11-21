-- === FUNCTION & TRIGGERS FOR FINAL SCORES (PostgreSQL) ===
CREATE OR REPLACE FUNCTION _recompute_final(aid UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $func$
DECLARE
  s1   NUMERIC(4,3);
  s2   NUMERIC(4,3);
  l    NUMERIC(4,3);
  w    NUMERIC(4,3) := 0.5;
  a    answers%ROWTYPE;
  havg NUMERIC(4,3);
  fin  NUMERIC(4,3);
BEGIN
  SELECT * INTO a FROM answers WHERE answer_id = aid;
  IF NOT FOUND THEN RETURN; END IF;

  SELECT
    MAX(CASE WHEN rater_id='teacher01' THEN score END),
    MAX(CASE WHEN rater_id='teacher02' THEN score END)
  INTO s1, s2
  FROM human_ratings
  WHERE answer_id = aid;

  IF s1 IS NULL OR s2 IS NULL THEN RETURN; END IF;

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
$func$;

CREATE OR REPLACE FUNCTION _trg_after_human_rating()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $trg$
BEGIN
  PERFORM _recompute_final(NEW.answer_id);
  RETURN NEW;
END;
$trg$;

CREATE OR REPLACE FUNCTION _trg_after_llm_score()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $trg2$
BEGIN
  PERFORM _recompute_final(NEW.answer_id);
  RETURN NEW;
END;
$trg2$;

DROP TRIGGER IF EXISTS trg_after_human_rating ON human_ratings;
CREATE TRIGGER trg_after_human_rating
AFTER INSERT OR UPDATE ON human_ratings
FOR EACH ROW EXECUTE FUNCTION _trg_after_human_rating();

DROP TRIGGER IF EXISTS trg_after_llm_score ON llm_scores;
CREATE TRIGGER trg_after_llm_score
AFTER INSERT OR UPDATE ON llm_scores
FOR EACH ROW EXECUTE FUNCTION _trg_after_llm_score();
