// src/components/AnswerCard.tsx
import React, { useMemo, useState } from "react";
import type { RaterItem } from "../types";
import { to10, bandColor } from "../lib/score";

type Props = {
  item: RaterItem;
  raterId: "teacher01" | "teacher02";
  /** τρέχουσα τιμή slider (0..10) για αυτό το answerId, αν έρχεται από parent */
  value?: number;
  /** callback όταν αλλάζει το slider */
  onChange?: (answerId: string, value10: number) => void;
  /** callback όταν πατιέται το Queue */
  onQueue?: (answerId: string, value10: number) => void;
};

function deltaColor(d: number) {
  const abs = Math.abs(d);
  // ήπια χρωματική κλίμακα για bias:
  if (abs < 0.4) return "#34d399"; // ~πράσινο (σχεδόν ταύτιση)
  if (d > 0) return "#60a5fa";     // μπλε για teacher > LLM
  return "#f59e0b";                // πορτοκαλί για teacher < LLM
}

const AnswerCard: React.FC<Props> = ({
  item,
  raterId,
  value,
  onChange,
  onQueue,
}) => {
  // Badges (σε κλίμακα 0..10)
  const llm10 = useMemo(() => to10(item.initialScore ?? null), [item.initialScore]);
  const t110  = useMemo(() => to10(item.teacher01 ?? null), [item.teacher01]);
  const t210  = useMemo(() => to10(item.teacher02 ?? null), [item.teacher02]);

  // Delta για τον τρέχοντα rater (χρησιμοποιείται ΜΟΝΟ για το δικό του score, δεν εμφανίζουμε του άλλου)
  const rater10 = raterId === "teacher01" ? t110 : t210;
  const delta = llm10 != null && rater10 != null ? +(rater10 - llm10).toFixed(1) : null;

  // local slider state αν δεν παρέχεται value από parent
  const [localValue, setLocalValue] = useState<number>(value ?? 0);
  const score10 = value ?? localValue;

  const handleSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value);
    if (onChange) onChange(item.answerId, v);
    setLocalValue(v);
  };

  const handleQueue = () => {
    if (onQueue) onQueue(item.answerId, score10);
  };

  return (
    <div className="answer-card">
      {/* Header: user + question id + badges */}
      <div className="answer-card__header">
        <div className="answer-card__title">
          <strong style={{ color: "#fff" }}>User: {item.userId || "—"}</strong>
          <span className="pill pill--qid">Q: {item.questionId}</span>
          <span className="pill pill--meta">
            Cat: {item.category} &nbsp; Type: {item.qtype}
          </span>
        </div>

        <div className="answer-card__badges">
          {/* 🔹 ΜΟΝΟ LLM score φαίνεται σταθερά */}
          <span
            className="badge"
            style={{ background: bandColor(llm10), color: "#0b1220" }}
            title="LLM initial score"
          >
            LLM: {llm10 ?? "—"}/10
          </span>

          {/* ❌ Δεν δείχνουμε πια Teacher 1 / Teacher 2 badges για να μην επηρεάζονται */}
          {/* 
          <span className="badge">T1: ...</span>
          <span className="badge">T2: ...</span>
          */}

          {/* Προαιρετικά: Δ = (current teacher − LLM), ΔΕΝ αποκαλύπτει τον άλλο teacher */}
          {delta != null && (
            <span
              className="badge"
              style={{ background: deltaColor(delta), color: "#0b1220" }}
              title={`Δ vs LLM (${raterId})`}
            >
              Δ: {delta > 0 ? `+${delta}` : delta}
            </span>
          )}
        </div>
      </div>

      {/* Question (άσπρο κείμενο) */}
      <div className="answer-card__block">
        <div className="answer-card__label" style={{ color: "#9fb0c9" }}>
          Question:
        </div>
        <div
          className="answer-card__text"
          style={{ color: "#ffffff", background: "#101827" }}
        >
          {item.prompt || "[no question text]"}
        </div>
      </div>

      {/* User Answer (άσπρο κείμενο) */}
      <div className="answer-card__block">
        <div className="answer-card__label" style={{ color: "#9fb0c9" }}>
          User Answer:
        </div>
        <div
          className="answer-card__text"
          style={{ color: "#ffffff", background: "#101827" }}
        >
          {item.answer || "—"}
        </div>
      </div>

      {/* Slider + Queue */}
      <div className="answer-card__footer">
        <div className="scorebar">
          <span>0</span>
          <input
            type="range"
            min={0}
            max={10}
            step={0.1}
            value={score10}
            onChange={handleSlider}
            className="scorebar__slider"
          />
          
          <span className="scorebar__value">{score10.toFixed(1)}/10</span>
        </div>

        <button className="btn btn--queue" onClick={handleQueue}>
          Queue
        </button>
      </div>
    </div>
  );
};

export default AnswerCard;