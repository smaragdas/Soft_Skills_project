// src/pages/Calibration.tsx
import React, { useEffect, useState } from "react";

/** Τύπος των στατιστικών που επιστρέφει το backend */
type CalibStats = {
  mae?: number;
  fleiss_kappa?: number;
  icc?: number;
  n?: number;
  updated_at?: string;
};

// Αν έχεις ήδη helper στο services/api, μπορείς να τον χρησιμοποιήσεις.
// Εδώ το κρατάω self-contained για να φύγουν αμέσως τα TS errors.
const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");
const API_KEY = import.meta.env.VITE_API_KEY as string;

async function fetchJSON(url: string, init?: RequestInit) {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "x-api-key": API_KEY } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${txt}`);
  }
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return {};
  return res.json();
}

async function getCalibrationStats(): Promise<CalibStats> {
  const url = `${API_BASE}/rater/calibration/stats`;
  const data = await fetchJSON(url);
  return (data || {}) as CalibStats;
}

export default function Calibration() {
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [stats, setStats]     = useState<CalibStats | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const s = await getCalibrationStats();
        if (alive) setStats(s);
      } catch (e: any) {
        if (alive) setError(e?.message || "Failed to load stats");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const fmt = (v?: number) =>
    typeof v === "number" && Number.isFinite(v) ? v.toFixed(2) : "—";

  return (
    <div className="p-4 max-w-xl mx-auto">
      <h1 className="text-2xl font-semibold mb-4">Calibration</h1>

      {loading && <p>Loading…</p>}
      {error && <p className="text-red-600">Error: {error}</p>}

      {!loading && !error && (
        <ul className="list-disc pl-6 space-y-1">
          <li>MAE: {fmt(stats?.mae)}</li>
          <li>Fleiss' κ: {fmt(stats?.fleiss_kappa)}</li>
          <li>ICC: {fmt(stats?.icc)}</li>
          {typeof stats?.n === "number" && <li>N: {stats!.n}</li>}
          {stats?.updated_at && <li>Updated: {stats.updated_at}</li>}
        </ul>
      )}
    </div>
  );
}
