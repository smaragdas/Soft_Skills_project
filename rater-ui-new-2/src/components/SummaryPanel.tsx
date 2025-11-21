// src/components/SummaryPanel.tsx
import React, { useEffect, useState } from "react";
import { fetchSummary } from "../api";
import type { SummaryRow } from "../types";

type Props = {
  // προαιρετικά μπορείς να δίνεις αρχικό rater απ’ έξω
  initialRater?: "teacher01" | "teacher02";
};

const SummaryPanel: React.FC<Props> = ({ initialRater = "teacher01" }) => {
  const [rater, setRater] = useState<"teacher01" | "teacher02">(initialRater);
  const [rows, setRows] = useState<SummaryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await fetchSummary({ raterId: rater });
      setRows(data);
    } catch (e: any) {
      setErr(e?.message || "Failed to load summary");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rater]);

  return (
    <div
      style={{
        border: "1px solid #1f2937",
        borderRadius: 12,
        padding: 12,
        marginBottom: 18,
        background: "#0b1220",
        color: "#e5e7eb",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: 10,
        }}
      >
        <strong style={{ color: "#fff" }}>Summary</strong>

        <label>
          Rater:&nbsp;
          <select
            value={rater}
            onChange={(e) => setRater(e.target.value as "teacher01" | "teacher02")}
          >
            <option value="teacher01">teacher01</option>
            <option value="teacher02">teacher02</option>
          </select>
        </label>

        <button onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Reload"}
        </button>
      </div>

      {err && (
        <div
          style={{
            background: "#3b0d0d",
            color: "#ffdcdc",
            border: "1px solid #7f1d1d",
            borderRadius: 8,
            padding: "8px 10px",
            marginBottom: 10,
          }}
        >
          {err}
        </div>
      )}

      {rows.length === 0 && !loading ? (
        <div style={{ opacity: 0.8 }}>— no data —</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 14,
              color: "#e5e7eb",
            }}
          >
            <thead>
              <tr style={{ background: "#111827" }}>
                <th style={th}>User</th>
                <th style={th}>Total</th>
                <th style={th}>Pending</th>
                <th style={th}>LLM avg (0–10)</th>
                <th style={th}>Human avg (0–10)</th>
                <th style={th}>Last</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.userId} style={{ borderTop: "1px solid #1f2937" }}>
                  <td style={td}>{r.userId}</td>
                  <td style={td}>{r.total}</td>
                  <td style={td}>{r.pending}</td>
                  <td style={td}>{fmt10(r.avgLLM)}</td>
                  <td style={td}>{fmt10(r.avgHuman)}</td>
                  <td style={td}>{r.lastAt ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 10px",
  color: "#9fb0c9",
  fontWeight: 600,
};

const td: React.CSSProperties = {
  padding: "8px 10px",
};

function fmt10(v?: number | null) {
  if (v == null || !Number.isFinite(v)) return "—";
  return (Number(v) * 10).toFixed(2);
}

export default SummaryPanel;
