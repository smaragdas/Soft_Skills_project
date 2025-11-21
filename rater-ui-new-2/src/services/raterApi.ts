// src/services/raterApi.ts
export type Answer = {
  answer_id: string;
  user_id: string;
  participant_id: string;
  category: string;
  qtype: string;
  question_id: string;
  text: string;
  created_at: string; // ISO
  attempt?: number | null;
};

export type IRRStats = {
  mae?: number;
  fleiss_kappa?: number;
  icc?: number;
};

const BASE = import.meta.env.VITE_API_URL; // π.χ. .../prod/api/softskills

// Παίρνει ουρά απαντήσεων για rating.
// overlap=1 => δίνει και κοινά items για IRR.
// Αν περάσεις rater_id, θα φιλτράρει όσα έχεις ήδη βαθμολογήσει.
export async function fetchQueue(params: {
  category?: string;
  limit?: number;
  overlap?: boolean;
  rater_id: string;
}) {
  const url = new URL(`${BASE}/rater/queue`);
  if (params.category) url.searchParams.set("category", params.category);
  url.searchParams.set("limit", String(params.limit ?? 20));
  url.searchParams.set("overlap", params.overlap ? "1" : "0");
  url.searchParams.set("rater_id", params.rater_id);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Queue fetch failed");
  return (await res.json()) as Answer[];
}

// Αποστολή βαθμολογίας raters
export async function submitScore(payload: {
  answer_id: string;
  rater_id: string;
  category: string;
  score: number; // 0..1
  notes?: string;
}) {
  const res = await fetch(`${BASE}/rater/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Submit score failed");
}

// IRR στατιστικά (υπολογίζονται στο back ή τα επιστρέφεις έτοιμα)
export async function fetchStats(params?: { category?: string }) {
  const url = new URL(`${BASE}/rater/stats`);
  if (params?.category) url.searchParams.set("category", params.category);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Stats fetch failed");
  return (await res.json()) as IRRStats;
}
