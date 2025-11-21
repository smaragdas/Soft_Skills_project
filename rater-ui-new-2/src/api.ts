// src/lib/api.ts
// Minimal API client for Rater UI
import type { RaterItem, SummaryRow } from "./types";

const envBase = (import.meta as any).env?.VITE_API_BASE as string | undefined;
const envKey  = (import.meta as any).env?.VITE_API_KEY as string | undefined;

function normalizeBase(base: string) {
  let b = (base || "").trim().replace(/\/+$/, "");
  // αν μας έδωσαν ήδη /api/softskills στο τέλος, βγάλ' το για να το προσθέτουμε εμείς σταθερά
  b = b.replace(/\/api\/softskills$/i, "");
  return b || "http://127.0.0.1:8001";
}

export function getAPIBase(): string {
  const local = (localStorage.getItem("API_BASE") || "").trim();
  const chosen = local || envBase || "http://127.0.0.1:8001";
  return `${normalizeBase(chosen)}/api/softskills`;
}

export function getRootBase(): string {
  const local = (localStorage.getItem("API_BASE") || "").trim();
  const chosen = local || envBase || "http://127.0.0.1:8001";
  return normalizeBase(chosen);
}

function getApiKey(): string | undefined {
  // προτεραιότητα σε localStorage για γρήγορο override
  const fromLS = (localStorage.getItem("API_KEY") || "").trim();
  if (fromLS) return fromLS;
  if (envKey && String(envKey).trim()) return String(envKey).trim();
  return undefined;
}

function getAttemptFromURL(): "1" | "2" | undefined {
  const att = new URLSearchParams(window.location.search).get("attempt");
  return att === "1" || att === "2" ? att : undefined;
}

async function doFetch<T>(input: string, init?: RequestInit): Promise<T> {
  const apiKey = getApiKey();
  const headers: Record<string, string> = {
    Accept: "application/json, text/plain, */*",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (apiKey && !headers["x-api-key"]) {
    headers["x-api-key"] = apiKey;
  }

  const res = await fetch(input, { ...init, headers });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} :: ${txt}`);
  }
  const ctype = res.headers.get("content-type") || "";
  if (ctype.includes("application/json")) return (await res.json()) as T;
  // επιτρέπουμε και text (π.χ. CSV)
  return (await res.text()) as T;
}

export async function apiGet<T>(path: string, params?: Record<string, any>) {
  const base = getAPIBase();
  const url = new URL(`${base}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined || v === null || v === "") return;
      url.searchParams.set(k, String(v));
    });
  }
  return doFetch<T>(url.toString(), { method: "GET" });
}

export async function apiPost<T>(path: string, body?: any, params?: Record<string, any>) {
  const base = getAPIBase();
  const url = new URL(`${base}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined || v === null || v === "") return;
      url.searchParams.set(k, String(v));
    });
  }
  return doFetch<T>(url.toString(), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}

function getAdminToken(): string | undefined {
  const t = (localStorage.getItem("ADMIN_TOKEN") || "").trim();
  return t || undefined;
}


export type ClearResponse = {
  ok: boolean;
  message?: string;
  before?: any;
  after?: any;
};

export async function adminClearAll(): Promise<ClearResponse> {
  const headers: Record<string,string> = {
    Accept: "application/json",
    "content-type": "application/json",
    "x-admin-token": (localStorage.getItem("ADMIN_TOKEN")||"").trim(),
  };
  const apiKey = (localStorage.getItem("API_KEY")||"").trim();
  if (apiKey) headers["x-api-key"] = apiKey;

  // Χρησιμοποιούμε το ίδιο base που πάει στα κανονικά endpoints
  const base = getAPIBase();          // π.χ. http://127.0.0.1:8000/api/softskills

  // 1) σωστό wipe
  let res = await fetch(`${base}/_diag/clear-all`, {
    method: "POST",
    headers,
    body: JSON.stringify({ confirm: "DELETE" }),
  });

  // 2) fallback στον init-db αν λείπει (παλιότερα builds)
  if (res.status === 404) {
    res = await fetch(`${base}/_diag/init-db`, {
      method: "POST",
      headers,
      body: "{}",
    });
  }

  if (!res.ok) {
    const txt = await res.text().catch(()=> "");
    throw new Error(`${res.status} ${res.statusText} :: ${txt}`);
  }
  const data = await res.json();
  return {
    ok: !!data?.ok,
    message: data?.message,
    before: data?.before,
    after: data?.after,
  };
}

// ---------- Rater endpoints ----------

export async function fetchRaterItems(
  raterId: "teacher01" | "teacher02",
  filters?: { q?: string; category?: string; qtype?: "open" | "mc" | ""; has_llm?: "1" | "0" }
): Promise<RaterItem[]> {
  // GET /api/softskills/rater/items?rater_id=teacher01&...
  const attempt = getAttemptFromURL();
  const params = { rater_id: raterId, ...(filters || {}) } as Record<string, any>;
  if (attempt) params.attempt = attempt;

  const data = await apiGet<any>("/rater/items", params);

  // Map snake_case -> camelCase
  return (data as any[]).map((row) => ({
    answerId: row.answer_id,
    questionId: row.question_id,
    userId: row.user_id,
    qtype: row.qtype,
    category: row.category,
    prompt: row.prompt ?? null,
    answer: row.answer ?? null,
    initialScore: row.initialScore ?? row.llm_score ?? null,
    createdAt: row.created_at,
    teacher01: row.teacher01 ?? null,
    teacher02: row.teacher02 ?? null,
  }));
}

export async function submitRatings(
  raterId: "teacher01" | "teacher02",
  ratings: { answerId: string; score: number }[]
) {
  // POST /api/softskills/rater/submit
  // Body: { raterId, ratings }
  return apiPost<{ ok: true }>("/rater/submit", { raterId, ratings });
}

export async function fetchFinalCSV(): Promise<{ blob: Blob }> {
  const base = getAPIBase();
  const attempt = getAttemptFromURL();
  const url = new URL(`${base}/rater/results.csv`);
  if (attempt) url.searchParams.set("attempt", attempt);

  const apiKey = getApiKey();
  const res = await fetch(url.toString(), {
    headers: apiKey ? { "x-api-key": apiKey } : undefined,
  });
  if (!res.ok) throw new Error(`CSV ${res.status}`);
  const blob = await res.blob();
  return { blob };
}

export async function deleteRatings(
  raterId: "teacher01" | "teacher02",
  answerIds: string[]
) {
  // αν στο backend έχεις /rater/delete-many
  return apiPost<{ ok: boolean; deleted: number }>("/rater/delete-many", {
    raterId,
    answerIds,
  });
}

export async function deleteRating(
  raterId: "teacher01" | "teacher02",
  answerId: string
) {
  // αν στο backend έχεις /rater/delete
  return apiPost<{ ok: boolean; deleted: number }>("/rater/delete", {
    raterId,
    answerId,
  });
}

// ---------- Questions map (εκφωνήσεις) ----------
// Δουλεύει είτε /quiz/bundle είτε /quiz/questions είτε /questions.
// ---------- Questions map (εκφωνήσεις) ----------
// ---------- Questions map (εκφωνήσεις) ----------
export async function getAllQuestionsMap(): Promise<Record<string, string>> {
  const map: Record<string, string> = {};

  // attempt από το URL ?attempt=1/2 → phase PRE/POST
  const att = getAttemptFromURL();
  const attempt = att === "2" ? "2" : "1";
  const phase = attempt === "2" ? "POST" : "PRE";

  const pushArr = (arr?: any[]) =>
    (arr || []).forEach((q) => {
      if (!q) return;
      const id = q.id || q.question_id || q.code || q.key;
      const text =
        q.prompt ||
        q.text ||
        q.title ||
        q.body ||
        q.question ||
        q.statement ||
        q.description ||
        "";
      if (id && text) {
        map[String(id)] = String(text);
      }
    });

  try {
    // 1) Φέρνουμε τις κατηγορίες από το backend
    //    GET /api/softskills/questions/categories?phase=PRE|POST
    const cats = await apiGet<any>("/questions/categories", { phase });
    const categories: string[] = Array.isArray(cats)
      ? cats
      : Array.isArray(cats?.categories)
      ? cats.categories
      : ["Communication", "Teamwork", "Leadership", "Problem Solving"];

    // 2) Για κάθε κατηγορία, ζητάμε ΠΟΛΛΕΣ ερωτήσεις (100 open + 100 mc)
    for (const cat of categories) {
      try {
        const data = await apiGet<any>("/questions/bundle", {
          category: cat,
          n_open: 100,
          n_mc: 100,
          phase,
          attempt,
          include_correct: true,
        });

        pushArr(data?.open);
        pushArr(data?.mc);
        if (Array.isArray(data?.flat)) {
          pushArr(data.flat);
        }
      } catch (err) {
        console.warn("[Rater] getAllQuestionsMap: failed for category", cat, err);
      }
    }
  } catch (err) {
    console.warn("[Rater] getAllQuestionsMap: categories failed", err);
  }

  return map;
}

// URL για CSV (με attempt αν υπάρχει)
export const getResultsCsvUrl = () => {
  const base = getAPIBase();
  const attempt = getAttemptFromURL();
  const url = new URL(`${base}/rater/results.csv`);
  if (attempt) url.searchParams.set("attempt", attempt);
  return url.toString();
};

// Σύνοψη
export async function fetchSummary(params?: { raterId?: "teacher01" | "teacher02" }) {
  const query: Record<string, string> = {};
  if (params?.raterId) query.rater_id = params.raterId;

  const attempt = getAttemptFromURL();
  if (attempt) query.attempt = attempt;

  const data = await apiGet<any>("/rater/summary", query);

  // Δέχεται διάφορα σχήματα, τα χαρτογραφούμε σε SummaryRow
  const rows: any[] = Array.isArray(data) ? data : (data?.items ?? []);
  return rows.map((r) => ({
    userId: r.user_id ?? r.userId ?? "-",
    total: Number(r.total ?? r.count ?? r.items ?? 0),
    pending: Number(r.pending ?? r.todo ?? 0),
    avgLLM: r.avg_llm ?? r.llm_avg ?? r.initial_avg ?? null,
    avgHuman: r.avg_human ?? r.human_avg ?? null,
    lastAt: r.last_at ?? r.lastAt ?? r.updated_at ?? r.created_at ?? null,
  })) as SummaryRow[];
}