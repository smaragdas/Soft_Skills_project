// src/services/api.js
import { getStudyToken, getAttemptNo } from './studyToken';

// --- Base settings ---
// ΠΡΟΣΟΧΗ: χρησιμοποιούμε VITE_API_BASE_URL (όχι VITE_API_BASE)
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');  // π.χ. https://.../prod/api/softskills
const API_KEY  = import.meta.env.VITE_API_KEY || '';
const CATALOG_BASE = (import.meta.env.VITE_CATALOG_BASE || BASE_URL).replace(/\/+$/, '');

// --- Study token & attempt ---
const STUDY_TOKEN = getStudyToken();
const ATTEMPT_NO  = getAttemptNo();

// --- URL helper: προσθέτει token & attempt σαν query params ---
function withStudyParams(rawUrl) {
  const u = new URL(rawUrl, window.location.origin);

  if (STUDY_TOKEN && typeof STUDY_TOKEN === 'string' && STUDY_TOKEN.trim()) {
    u.searchParams.set('token', STUDY_TOKEN.trim());
  }
  u.searchParams.set('attempt', String(ATTEMPT_NO));

  return u;
}

// Μόνο αυτά τα paths χρειάζονται X-Study-Token
function needsStudyHeader(url) {
  try {
    const u = new URL(url, window.location.origin);
    const p = u.pathname || '';
    // π.χ. .../score-mc, .../score-open, .../glmp/..., .../questions/bundle
    return /\/(score-|glmp|questions)\b/.test(p);
  } catch {
    return false;
  }
}

// --- Common fetch helper ---
async function fetchJSON(url, { method = 'GET', body, headers = {}, study = undefined } = {}) {
  const H = {
    'Content-Type': 'application/json',
    ...(API_KEY ? { 'x-api-key': API_KEY } : {}),
    ...headers,
  };

  // από προεπιλογή: βάλε X-Study-Token μόνο όπου χρειάζεται
  const attachStudy = (study === undefined) ? needsStudyHeader(url) : !!study;
  if (attachStudy && STUDY_TOKEN && typeof STUDY_TOKEN === 'string' && STUDY_TOKEN.trim()) {
    H['X-Study-Token'] = STUDY_TOKEN.trim();
  }

  const res = await fetch(url, {
    method,
    headers: H,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText} ${txt}`);
  }

  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) return {};
  return await res.json();
}

// ---------------------------------------------------------------------
// GLMP endpoints
// ---------------------------------------------------------------------
export async function evaluateGLMP({ textMeasures, audioMeasures, meta }) {
  const payload = {
    meta:  meta || {},
    text:  textMeasures || {},
    audio: audioMeasures || {},
  };
  const url = withStudyParams(`${BASE_URL}/glmp/evaluate`).toString();
  return await fetchJSON(url, { method: 'POST', body: payload }); // study header auto
}

export async function evaluateAndSaveGLMP(payload) {
  const url = withStudyParams(`${BASE_URL}/glmp/evaluate-and-save`).toString();
  return await fetchJSON(url, { method: 'POST', body: payload }); // study header auto
}

// ---------------------------------------------------------------------
// Soft-skills scoring endpoints
// ---------------------------------------------------------------------
export async function scoreOpen(payload) {
  const u = withStudyParams(`${BASE_URL}/score-open`);
  u.searchParams.set('save', 'true');   // &save=true
  const url = u.toString();
  return await fetchJSON(url, { method: 'POST', body: payload }); // study header auto
}

export async function scoreMC(payload) {
  const u = withStudyParams(`${BASE_URL}/score-mc`);
  u.searchParams.set('save', 'true');
  const url = u.toString();
  return await fetchJSON(url, { method: 'POST', body: payload }); // study header auto
}

// ---------------------------------------------------------------------
// Categories API  (ΧΩΡΙΣ study header)
// ---------------------------------------------------------------------
export async function getCategories() {
  const url = `${CATALOG_BASE}/categories`;
  return await fetchJSON(url, { method: 'GET', study: false }); // force: μην στείλεις X-Study-Token
}

// ---------------------------------------------------------------------
// Debug info (προαιρετικό για development)
// ---------------------------------------------------------------------
export function getStudyInfo() {
  return { STUDY_TOKEN, ATTEMPT_NO, BASE_URL, CATALOG_BASE, API_KEY_PRESENT: !!API_KEY };
}
