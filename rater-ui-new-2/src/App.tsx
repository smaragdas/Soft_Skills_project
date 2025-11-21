// src/App.tsx
import React, { useEffect, useMemo, useState } from "react";
import "./styles.css";
import AnswerCard from "./components/AnswerCard";
import {
  fetchRaterItems,
  submitRatings,
  fetchFinalCSV,
  getAllQuestionsMap,
  adminClearAll, // 👈 ενιαίο import από ./api
} from "./api";
import type { RaterItem } from "./types";
import SummaryPanel from "./components/SummaryPanel";

type Queued = { answerId: string; score10: number };

function groupByUser(items: RaterItem[]) {
  const m = new Map<string, RaterItem[]>();
  for (const it of items) {
    const k = it.userId || "—";
    if (!m.has(k)) m.set(k, []);
    m.get(k)!.push(it);
  }
  return m;
}

/** Μικρό κουμπί admin που καλεί /_diag/clear-all */
function AdminClearButton({ onAfter }: { onAfter?: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const hasAdmin = !!localStorage.getItem("ADMIN_TOKEN"); // δείξε κουμπί μόνο αν έχει ρυθμιστεί token

  if (!hasAdmin) return null;

 const handleClick = async () => {
  if (!window.confirm("⚠️ Θα διαγραφούν ΟΛΑ τα δεδομένα (answers, ratings, scores). Συνέχεια;")) return;
  const phrase = prompt("Για επιβεβαίωση πληκτρολόγησε: DELETE");
  if (phrase !== "DELETE") return;

  try {
    setBusy(true);
    const res = await adminClearAll();

    // Συναρμολογούμε το μήνυμα δυναμικά ανάλογα με το τι επιστρέφει
    let msg = "✅ Database cleared successfully!";
    if (res.before || res.after) {
      msg += `\nBefore: ${JSON.stringify(res.before ?? {})}\nAfter: ${JSON.stringify(res.after ?? {})}`;
    } else if (res.message) {
      msg += `\n${res.message}`;
    }

    alert(msg);
    onAfter?.();
  } catch (e: any) {
    alert(e?.message || "Failed to clear");
  } finally {
    setBusy(false);
  }
};


  return (
    <button
      onClick={handleClick}
      disabled={busy}
      style={{
        padding: "8px 12px",
        borderRadius: 10,
        border: "1px solid #7f1d1d",
        background: "#7f1d1d",
        color: "#fff",
        fontWeight: 700,
      }}
      title="Clear ALL data (admin)"
    >
      {busy ? "Clearing…" : "Clear DB"}
    </button>
  );
}

export default function App() {
  const [raterId, setRaterId] = useState<"teacher01" | "teacher02">("teacher01");
  const [items, setItems] = useState<RaterItem[]>([]);
  const [queued, setQueued] = useState<Queued[]>([]);
  const [values, setValues] = useState<Record<string, number>>({}); // slider values per answer

  // filters
  const [q, setQ] = useState("");
  const [hasLLM, setHasLLM] = useState<"all" | "with" | "without">("all");
  const [onlyPending, setOnlyPending] = useState(false);
  const [category, setCategory] = useState("");
  const [qtype, setQtype] = useState<"" | "open" | "mc">("");

  // εκφωνήσεις map
  const [qmap, setQmap] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  // collapsed per user
  const [collapsedUsers, setCollapsedUsers] = useState<Record<string, boolean>>({});

  // Φέρε εκφωνήσεις μία φορά
  useEffect(() => {
    (async () => {
      try {
        setQmap(await getAllQuestionsMap());
      } catch {
        setQmap({});
      }
    })();
  }, []);

  // Μετά το qmap, φόρτωσε items
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qmap]);

  async function load() {
    setLoading(true);
    try {
      const extra: Record<string, string> = {};
      if (q) extra.q = q;
      if (hasLLM === "with") extra.has_llm = "1";
      if (hasLLM === "without") extra.has_llm = "0";
      if (category) extra.category = category;
      if (qtype) extra.qtype = qtype;

      const data = await fetchRaterItems(raterId, extra as any);
      const withPrompt = data.map((d) => ({
        ...d,
        prompt: d.prompt || qmap[d.questionId] || "",
      }));
      setItems(withPrompt);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [raterId, hasLLM, category, qtype, onlyPending, q]);

  const isPending = (it: RaterItem) => (raterId === "teacher01" ? it.teacher01 : it.teacher02) == null;

  const filtered = useMemo(() => {
    let arr = items;
    if (q) {
      const s = q.toLowerCase();
      arr = arr.filter(
        (x) =>
          (x.answer || "").toLowerCase().includes(s) ||
          (x.prompt || "").toLowerCase().includes(s) ||
          (x.userId || "").toLowerCase().includes(s)
      );
    }
    if (hasLLM === "with") arr = arr.filter((x) => x.initialScore != null);
    if (hasLLM === "without") arr = arr.filter((x) => x.initialScore == null);
    if (onlyPending) arr = arr.filter(isPending);
    if (category) arr = arr.filter((x) => (x.category || "") === category);
    if (qtype) arr = arr.filter((x) => x.qtype === qtype);
    return arr;
  }, [items, q, hasLLM, onlyPending, category, qtype, raterId]);

  const grouped = useMemo(() => groupByUser(filtered), [filtered]);

  const queueOne = (answerId: string, score10: number) => {
    setQueued((prev) => {
      const rest = prev.filter((x) => x.answerId !== answerId);
      return [...rest, { answerId, score10 }];
    });
  };

  const onSubmit = async () => {
    if (!queued.length) return;
    setLoading(true);
    try {
      const payload = queued.map((q) => ({
        answerId: q.answerId,
        score: Math.max(0, Math.min(1, q.score10 / 10)), // 0..1 backend
      }));
      await submitRatings(raterId, payload);
      setQueued([]);
      setValues({});
      await load(); // άμεσο refresh
      setTimeout(() => load(), 700); // μικρό δεύτερο refresh προαιρετικά
    } finally {
      setLoading(false);
    }
  };

  const onExportCSV = async () => {
    const { blob } = await fetchFinalCSV();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "final_results.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggleUser = (userId: string) => {
    setCollapsedUsers((prev) => ({ ...prev, [userId]: !prev[userId] }));
  };

  // Τι να γίνει αμέσως μετά το Clear DB
  const handleAfterClear = () => {
    // Άδειασμα UI και επαναφόρτωση
    setItems([]);
    setQueued([]);
    setValues({});
    setCollapsedUsers({});
    load();
  };

  return (
    <div className="app-wrap full-width">
      {/* 🔹 Summary Panel πάνω-πάνω */}
      <SummaryPanel key={raterId} initialRater={raterId} />

      {/* Header / φίλτρα */}
      <div className="header-bar">
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <strong>Rater:</strong>
          <select value={raterId} onChange={(e) => setRaterId(e.target.value as any)}>
            <option value="teacher01">teacher01</option>
            <option value="teacher02">teacher02</option>
          </select>

          <input
            placeholder="Search in prompt/answer/user…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            style={{
              padding: "6px 10px",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              minWidth: 260,
            }}
          />
          <button onClick={load} disabled={loading}>Search</button>

          <select value={hasLLM} onChange={(e) => setHasLLM(e.target.value as any)}>
            <option value="all">All</option>
            <option value="with">With LLM</option>
            <option value="without">Without LLM</option>
          </select>

          <select value={qtype} onChange={(e) => setQtype(e.target.value as any)}>
            <option value="">All types</option>
            <option value="open">Open</option>
            <option value="mc">Multiple Choice</option>
          </select>

          <input
            placeholder="Category (exact)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ padding: "6px 10px", border: "1px solid #e5e7eb", borderRadius: 8 }}
          />

          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={onlyPending}
              onChange={(e) => setOnlyPending(e.target.checked)}
            />
            Only pending
          </label>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button
            onClick={onSubmit}
            disabled={!queued.length || loading}
            style={{
              padding: "8px 12px",
              borderRadius: 10,
              border: "1px solid #10b981",
              background: queued.length ? "#10b981" : "#d1d5db",
              color: "#fff",
              fontWeight: 700,
            }}
            title={queued.length ? `Submit ${queued.length} rating(s)` : "Nothing queued"}
          >
            Submit {queued.length ? `(${queued.length})` : ""}
          </button>

          <button
            onClick={onExportCSV}
            style={{
              padding: "8px 12px",
              borderRadius: 10,
              border: "1px solid #111827",
              background: "#111827",
              color: "#fff",
              fontWeight: 600,
            }}
            title="Export CSV"
          >
            Export CSV
          </button>

          {/* 🔴 Εμφανίζεται μόνο αν έχεις ADMIN_TOKEN στο localStorage */}
          <AdminClearButton onAfter={handleAfterClear} />
        </div>
      </div>

      {/* Group ανά user */}
      {[...grouped.entries()].map(([userId, rows]) => {
        const collapsed = !!collapsedUsers[userId];
        return (
          <section key={userId} style={{ marginBottom: 18 }}>
            <div className="section-header" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <strong style={{ fontSize: 18 }}>User: {userId}</strong>
              <span style={{ color: "#6b7280" }}>({rows.length} items)</span>

              <button
                onClick={() => toggleUser(userId)}
                className="btn"
                style={{
                  marginLeft: "auto",
                  padding: "6px 10px",
                  borderRadius: 10,
                  border: "1px solid #334155",
                  background: "#0b1220",
                  color: "#fff",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
                title={collapsed ? "Show answers" : "Hide answers"}
              >
                <span
                  style={{
                    transform: collapsed ? "rotate(-90deg)" : "rotate(0deg)",
                    transition: "transform 120ms",
                  }}
                >
                  ▸
                </span>
                {collapsed ? "Show" : "Hide"}
              </button>
            </div>

            {!collapsed && (
              <div className="grid-cards">
                {rows.map((it) => (
                  <AnswerCard
                    key={it.answerId}
                    item={it}
                    raterId={raterId}
                    value={values[it.answerId] ?? 0}
                    onChange={(id, v) => setValues((prev) => ({ ...prev, [id]: v }))}
                    onQueue={(id, v) => queueOne(id, v)}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
