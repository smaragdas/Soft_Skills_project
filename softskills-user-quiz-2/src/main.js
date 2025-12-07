// src/main.js — adaptive quiz: 4 (2 MC + 2 Open) → LEVEL → +12 (3*4) = 16 total
// Finale: overall avg, per-category avg, weakest category (resources)
import './style.css';
import { ensureSignedStudyToken } from './services/studyToken';

ensureSignedStudyToken().catch(()=>{alert("Invalid or expired token.");});

/* ================== helpers ================== */
const $ = (sel) => document.querySelector(sel);
globalThis.data = globalThis.data || {};

const LS = {
  API_BASE: 'API_BASE',
  USER_ID: 'USER_ID',
  CATEGORY: 'CATEGORY',
  API_KEY: 'API_KEY',
  PROGRESS: (u, c, p) => `QUIZ_PROGRESS:${u}:${c}:${(p||'PRE').toUpperCase()}`,
};

const DEFAULTS = { secondsPerQuestion: 180, openMinLen: 20 };
const DEBUG_SHOW_CORRECT = true;

function centerSettingsPanel(){
  const panel = document.getElementById('settingsPanel') || document.querySelector('.layout > aside.panel');
  if (!panel) return;
  const r = panel.getBoundingClientRect();
  const cx = r.left + r.width/2;
  const cy = r.top + r.height/2;
  const vw = window.innerWidth, vh = window.innerHeight;
  const dx = Math.round(vw/2 - cx);
  const dy = Math.round(vh/2 - cy);
  panel.style.transform = `translate(${dx}px, ${dy}px) scale(0.98)`;
}

// --- Study token & attempt helpers ---
function getQueryParam(name) {
  const m = new RegExp(`[?&]${name}=([^&#]*)`).exec(window.location.search);
  return m ? decodeURIComponent(m[1].replace(/\+/g, ' ')) : null;
}

const STUDY_TOKEN = (() => {
  const fromUrl = getQueryParam('token');
  const fromLS  = localStorage.getItem('study_token');
  const tok = fromUrl || fromLS || '';
  if (tok) localStorage.setItem('study_token', tok);
  return tok;
})();

const ATTEMPT_NO = (() => {
  const raw = getQueryParam('attempt');
  const n = parseInt(raw || '1', 10);
  return (n === 1 || n === 2) ? n : 1;
})();

// Δημιουργία ανώνυμου χρήστη + φάση PRE/POST
;(function seedUserFromTokenAndAttempt(){
  if (typeof STUDY_TOKEN !== 'undefined' && STUDY_TOKEN && STUDY_TOKEN.trim()) {
    const anonId = `stu_${STUDY_TOKEN.trim()}`;
    localStorage.setItem(LS.USER_ID, anonId);
    localStorage.setItem('QUIZ_USER', anonId);
  }
  const phase = (ATTEMPT_NO === 1 ? 'PRE' : 'POST');
  localStorage.setItem('QUIZ_PHASE', phase);
})();

// Αρχικοποίηση του badge PRE / POST στον τίτλο
;(function initPhaseBadge(){
  const phase = (localStorage.getItem('QUIZ_PHASE') || 'PRE').trim();
  const badgeEl = document.getElementById('phaseBadge');
  if (!badgeEl) return;

  badgeEl.textContent =
    phase === 'PRE' ? 'Αρχικό τεστ (PRE)' : 'Τελικό τεστ (POST)';
})();

const toNum = (x) => {
  if (x == null) return 0;
  const s = String(x).trim().replace(',', '.');
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : 0;
};

/* ================== Adaptive state ================== */
const ALL_CATEGORIES = ['Communication', 'Teamwork', 'Leadership', 'Problem Solving'];
let START_CATEGORY = null;
let BRANCHED = false;
let LEVEL = null;
let FINISHED = false;

function bandFromAvg(avg) {
  if (avg < 4.5) return 'low';
  if (avg >= 7.5) return 'high';
  return 'mid';
}

/* ================== User & API ================== */
const apiBaseEl  = $('#apiBase');
const userIdEl   = $('#userId');
const categoryEl = $('#category');

const ENV = {
  API_BASE: (import.meta.env?.VITE_API_BASE || '').trim(),
  API_KEY: (import.meta.env?.VITE_API_KEY || '').trim(),
};

const getAPIBase = () => {
  // ΠΡΩΤΑ πάρε από localStorage (UI override)
  const ls = (localStorage.getItem(LS.API_BASE) || '').trim();
  if (ls) return ls;

  // Μετά από .env*. Αν είναι λάθος, θα το σώσεις από UI/console.
  const env = (import.meta.env?.VITE_API_BASE || '').trim();
  if (env) return env;

  // Τελευταίο fallback
  return window.location.origin;
};

if (apiBaseEl) apiBaseEl.value = getAPIBase();

function ensureUserId() {
  // αν υπάρχει ήδη LS.USER_ID, μην το πειράξεις (π.χ. το έβαλε το seed)
  const existingLS = (localStorage.getItem(LS.USER_ID) || '').trim();

  // 1) Αν υπάρχει study token → χρησιμοποίησε ΠΑΝΤΑ stu_<token>
  if (STUDY_TOKEN && STUDY_TOKEN.trim()) {
    const anonId = `stu_${STUDY_TOKEN.trim()}`;
    if (!existingLS || existingLS !== anonId) {
      localStorage.setItem(LS.USER_ID, anonId);
      localStorage.setItem('QUIZ_USER', anonId);
    }
    if (userIdEl) {
      userIdEl.value = anonId;
      userIdEl.readOnly = true;
      userIdEl.setAttribute('aria-readonly','true');
    }
    return anonId;
  }

  // 2) Αλλιώς κράτα την υπάρχουσα συμπεριφορά (UUID όταν placeholder)
  const existingRaw = ((userIdEl?.value || '') || existingLS).trim();
  const isPlaceholder = !existingRaw || existingRaw.toLowerCase() === 'kosta' || existingRaw.length < 8;
  let uid = existingRaw;

  if (isPlaceholder) {
    try { uid = crypto?.randomUUID?.() || ''; } catch { uid = ''; }
    if (!uid) uid = `u_${Date.now()}_${Math.random().toString(36).slice(2,8)}`;
    localStorage.setItem(LS.USER_ID, uid);
  }

  if (userIdEl) {
    userIdEl.value = uid;
    userIdEl.readOnly = true;
    userIdEl.setAttribute('aria-readonly','true');
  }
  return uid;
}

ensureUserId();

function getUserId(){
  return (userIdEl?.value?.trim() || localStorage.getItem(LS.USER_ID) || ensureUserId()).trim();
}


function joinUrl(base, path) { const b=(base||'').replace(/\/+$/,''); const p=(path||'').replace(/^\/+/,''); return `${b}/${p}`; }
function ensurePrefix(base) {
  const b=(base||'').replace(/\/+$/,'');
  if (/(?:^|\/)(api\/v1\/softskills|softskills|api\/softskills)\/?$/i.test(b)) return b;
  return b + '/api/softskills';
}

async function fetchJSON(url, opt = {}) {
  const headers = new Headers(opt.headers || {});
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');

  // Μην βάζεις Content-Type σε GET για να αποφεύγεις άχρηστα preflights
  if ((opt.method || 'GET').toUpperCase() !== 'GET' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json; charset=utf-8');
  }

  // 🔑 API key: 1) από UI (localStorage), 2) από .env
  const lsKey = (localStorage.getItem(LS.API_KEY) || '').trim();
  const envKey = (import.meta.env?.VITE_API_KEY || '').trim();
  const apiKey = lsKey || envKey;
  if (apiKey && !headers.has('x-api-key')) headers.set('x-api-key', apiKey);

  const res = await fetch(url, { ...opt, headers });
  const raw = await res.text();

  let json = null;
  try { json = raw ? JSON.parse(raw) : null; } catch {}

  if (!res.ok) {
    const msg = (json && (json.detail || json.message)) || raw || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    err.body = raw;
    throw err;
  }
  return json;
}

function normalizeCategory(c){
  const map = {
    "Communication": "communication",
    "Leadership": "leadership",
    "Teamwork": "teamwork",
    "Problem Solving": "problem_solving"
  };
  return map[c] || String(c || "communication").toLowerCase().replace(/\s+/g,'_');
}

/* ================== State ================== */
let BUNDLE = [];
let CUR = 0;
let RESULTS = [];
let TIMER = { handle:null, remaining:DEFAULTS.secondsPerQuestion };

/* ================== Κρύψε πεδία dev από το UI ================== */

function updateNextButtonState() {
  const next = $('#btnNext');
  if (!next || !BUNDLE.length) return;

  const q = BUNDLE[CUR];
  const isScored = !!q?.scored;

  next.disabled = !isScored;
}


;(function hideApiBaseField() {
  const el = document.querySelector('#apiBase');
  if (!el) return;
  const row = el.closest('.row, .field, .form-row, .form-group, .input-row') || el.parentElement;
  if (row) row.classList.add('hidden'); else el.style.display = 'none';
})();
;(function hideBundleSelector() {
  const bundleSel = document.querySelector('#bundle');
  if (!bundleSel) return;
  const row = bundleSel.closest('.row, .field, .form-row, .form-group, .input-row') || bundleSel.parentElement;
  (row || bundleSel).classList.add('hidden');
})();

/* ================== Categories (dropdown) ================== */
;(async function initCategories() {
  const sel = categoryEl;
  if (!sel) return;
  const saved = localStorage.getItem(LS.CATEGORY) || 'Leadership';
  try {
    const base = ensurePrefix(getAPIBase());
    const res  = await fetchJSON(joinUrl(base,'/questions/categories'));
    const cats = Array.isArray(res) ? res : (Array.isArray(res?.categories) ? res.categories : []);
    if (cats.length) {
      sel.innerHTML = cats.map(c => `<option>${c}</option>`).join('');
      sel.value = cats.includes(saved) ? saved : cats[0];
    } else sel.value = saved;
  } catch { sel.value = saved; }
})();

$('#btnSave')?.addEventListener('click', (e)=>{
  e.preventDefault(); e.stopPropagation();
  localStorage.setItem(LS.API_BASE, ($('#apiBase')?.value||'').trim());
  localStorage.setItem(LS.USER_ID, ($('#userId')?.value||'').trim());
  localStorage.setItem(LS.CATEGORY, ($('#category')?.value||'Leadership'));
  const apiKeyEl = document.querySelector('#apiKey');
  if (apiKeyEl && apiKeyEl.value) localStorage.setItem(LS.API_KEY, apiKeyEl.value.trim());
  if (userIdEl) { userIdEl.readOnly = true; userIdEl.setAttribute('aria-readonly','true'); }
});

async function beginFlow(){
  const intro = document.getElementById('introPanel');
  if (intro){
    intro.classList.add('intro-hide');
    setTimeout(()=> intro.classList.add('hidden'), 360);
  }

    const instr = document.getElementById('instructionsPanel');
  if (instr){
    instr.classList.add('intro-hide');
    setTimeout(()=> instr.classList.add('hidden'), 360);
  }
  
  await startNewQuiz();
  const qb = document.querySelector('#quizBox');
  if (qb && qb.animate){
    qb.animate(
      [
        { opacity: 0, transform: 'translateY(6px) scale(.98)' },
        { opacity: 1, transform: 'translateY(0) scale(1)' }
      ],
      { duration: 280, easing: 'ease-out' }
    );
  }
}

document.querySelector('#btnStart')?.addEventListener('click', (e)=>{
  e.preventDefault(); e.stopPropagation(); beginFlow();
});
document.querySelector('#startBtn')?.addEventListener('click', (e)=>{
  e.preventDefault(); e.stopPropagation(); beginFlow();
});

/* ================== Enable Start ================== */
$('#btnStart') && ($('#btnStart').disabled=false);
$('#startBtn') && ($('#startBtn').disabled=false);

/* ================== Progress (localStorage) ================== */
function saveProgress(){
  const user = getUserId();
  const cat  = (categoryEl?.value||'Leadership').trim();
  const phase = (localStorage.getItem('QUIZ_PHASE') || 'PRE').trim();
  const key = LS.PROGRESS(user, cat, phase);

  const payload = {
    CUR,
    BUNDLE,
    RESULTS,
    ts: Date.now(),
    BRANCHED,
    LEVEL,
    FINISHED,
  };

  try {
    localStorage.setItem(key, JSON.stringify(payload));
    // console.log('Saved progress →', key, payload); // (προαιρετικά για debug)
  } catch {}
}
// ------- RESTORE PROGRESS AFTER REFRESH -------

function restoreProgressFromLocalStorage() {
  const user = getUserId();   // θα είναι stu_<token> αν υπάρχει token
  if (!user) return false;

  let bestKey = null;
  let bestPayload = null;

  // 1) Βρες την πιο πρόσφατη αποθηκευμένη πρόοδο ΜΟΝΟ για ΑΥΤΟΝ τον user
  const prefix = `QUIZ_PROGRESS:${user}:`;
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k || !k.startsWith(prefix)) continue;

    try {
      const raw = localStorage.getItem(k);
      if (!raw) continue;
      const data = JSON.parse(raw);
      if (!data || typeof data !== 'object' || !Array.isArray(data.BUNDLE)) continue;

      if (!bestPayload || (data.ts && data.ts > (bestPayload.ts || 0))) {
        bestKey = k;
        bestPayload = data;
      }
    } catch {
      // αγνόησε προβληματικά entries
    }
  }

  // Δεν βρέθηκε τίποτα για ΑΥΤΟΝ τον user → άσε το UI στο intro
  if (!bestKey || !bestPayload) return false;

  // 2) Διάβασε category & phase από το key
  // format: QUIZ_PROGRESS:<user>:<category>:<PHASE>
  const parts = bestKey.split(':');
  const cat   = (parts[2] || 'Leadership').trim();
  const phase = (parts[3] || 'PRE').trim();

  // 3) Φόρτωση state από το payload
  BUNDLE  = bestPayload.BUNDLE || [];
  CUR     = Math.min(Math.max(bestPayload.CUR || 0, 0), BUNDLE.length - 1);
  RESULTS = bestPayload.RESULTS || [];
  START_CATEGORY = cat;

  BRANCHED = !!bestPayload.BRANCHED;
  LEVEL    = bestPayload.LEVEL || null;
  FINISHED = !!bestPayload.FINISHED;

  // 4) Συγχρονισμός localStorage & UI (ώστε να συμφωνούν)
  localStorage.setItem(LS.CATEGORY, cat);
  localStorage.setItem('QUIZ_PHASE', phase);
  if (categoryEl) categoryEl.value = cat;

  if (userIdEl) {
    userIdEl.value = user;
    userIdEl.readOnly = true;
    userIdEl.setAttribute('aria-readonly', 'true');
  }

  // 5) Απόκρυψη intro / instructions, εμφάνιση quiz
  document.getElementById('introPanel')?.classList.add('hidden');
  document.getElementById('instructionsPanel')?.classList.add('hidden');
  document.getElementById('quizBox')?.classList.remove('hidden');

  // 6) Progress bar
  if (typeof setBar === 'function') {
    const expectedTotal = BRANCHED ? (BUNDLE.length || 16) : 16;
    const progressPercent = ((CUR + 1) / Math.max(expectedTotal, 1)) * 100;
    setBar(progressPercent);
  }

  // 7) Κάνε render την τρέχουσα ερώτηση
  if (typeof renderCurrent === 'function') {
    renderCurrent();
  } else {
    console.warn('renderCurrent() is not defined – update restoreProgressFromLocalStorage');
  }

  return true;
}

function clearProgress(){
  const user = getUserId();
  const cat  = (categoryEl?.value||'Leadership').trim();
  // καθάρισε και τα δύο για σιγουριά
  try {
    localStorage.removeItem(LS.PROGRESS(user, cat, 'PRE'));
    localStorage.removeItem(LS.PROGRESS(user, cat, 'POST'));
  } catch {}
}

/* ================== Render ================== */
function setBar(p){ const el=$('#bar'); if(el) el.style.width=`${p}%`; }
function clearResult(){
  const result = $('#result');
  if (result) result.classList.add('hidden');

  if ($('#score'))    $('#score').textContent = '';
  if ($('#answerId')) $('#answerId').textContent = '—';
  if ($('#keep'))     $('#keep').textContent = '—';
  if ($('#change'))   $('#change').textContent = '—';
  if ($('#action'))   $('#action').textContent = '—';
  if ($('#drill'))    $('#drill').textContent = '—';
  if ($('#fbText'))   $('#fbText').textContent = '';
}

function renderMCOptions(q){
  const mcArea=$('#mcArea'); const box=$('#mcOptions'); if(!mcArea||!box) return;
  box.innerHTML=''; box.classList.add('mc-grid');
  (q.options||[]).forEach((opt,idx)=>{
    const card=document.createElement('div'); card.className='mc-card'; card.tabIndex=0; card.setAttribute('role','radio'); card.setAttribute('aria-checked','false'); card.dataset.value=String(opt.id);
    const mark=document.createElement('div'); mark.className='mc-mark';
    const text=document.createElement('div'); text.className='mc-text'; text.textContent=opt.text;
    const radio=document.createElement('input'); radio.type='radio'; radio.name='mcOpt'; radio.value=String(opt.id); radio.id=`mc_${q.id}_${idx}`; radio.className='mc-hidden-radio';
    if(q.selected_id && String(q.selected_id)===String(opt.id)){ radio.checked=true; card.classList.add('selected'); card.setAttribute('aria-checked','true'); }
    const onSelect=()=>{ box.querySelectorAll('.mc-card.selected').forEach(el=>{el.classList.remove('selected'); el.setAttribute('aria-checked','false');}); card.classList.add('selected'); card.setAttribute('aria-checked','true'); radio.checked=true; q.selected_id=radio.value; saveProgress(); };
    card.addEventListener('click',onSelect);
    card.addEventListener('keydown',(e)=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); onSelect(); }});
    card.appendChild(mark); card.appendChild(text); card.appendChild(radio); box.appendChild(card);
  });
  mcArea.classList.remove('hidden');
}

let SWAPPING = false;

async function animateQuestionSwap(toIndex){
  if (SWAPPING) return;
  const card = document.querySelector('#quizBox .question');
  SWAPPING = true;
  if (card && card.animate){
    try {
      await card.animate(
        [
          { opacity: 1, transform: 'translateY(0) scale(1)' },
          { opacity: 0, transform: 'translateY(-4px) scale(.99)' }
        ],
        { duration: 180, easing: 'ease-out', fill: 'forwards' }
      ).finished;
    } catch(_) {}
  }
  CUR = toIndex;
  renderCurrent();
  if (card && card.animate){
    try {
      card.animate(
        [
          { opacity: 0, transform: 'translateY(6px) scale(.985)' },
          { opacity: 1, transform: 'translateY(0)  scale(1)' }
        ],
        { duration: 220, easing: 'ease-out', fill: 'forwards' }
      );
    } catch(_) {}
  }
  SWAPPING = false;
}

function renderCurrent(){
  if(!BUNDLE.length) return;
  const q=BUNDLE[CUR];

  $('#qId')&&($('#qId').textContent=q.id);
  $('#qText')&&($('#qText').textContent=q.text);
  $('#kindBadge')&&($('#kindBadge').textContent=(q.type||'').toUpperCase());
  $('#status')&&($('#status').textContent = `Κατηγορία: ${q.category || (categoryEl?.value || '')}`);

  const expectedTotal = BRANCHED ? (BUNDLE.length||16) : 16;
  $('#stepText')&&($('#stepText').textContent=`${CUR+1} / ${expectedTotal}`);

  const ans=$('#answer'); const mcArea=$('#mcArea');
  if(q.type==='open'){ ans&&(ans.value=q.answer||''); ans?.classList.remove('hidden'); mcArea?.classList.add('hidden'); }
  else{ ans?.classList.add('hidden'); renderMCOptions(q); }

  clearResult();
  $('#btnPrev')&&($('#btnPrev').disabled = (CUR===0));

  const pct=Math.round(((CUR+1)/Math.max(1,expectedTotal))*100); setBar(pct);
  const isLast = CUR >= expectedTotal-1;
  const next = $('#btnNext');
  if (next) {
    next.textContent = isLast ? 'Τέλος' : 'Επόμενο';
    next.dataset.role = isLast ? 'finish' : 'next';
  }

  // 🆕 ενεργοποίηση/απενεργοποίηση ανάλογα με το αν έχει βαθμολογηθεί η ερώτηση
  updateNextButtonState();
  startTimer(DEFAULTS.secondsPerQuestion);
}

/* ================== Timer ================== */
function stopTimer(){ if(TIMER.handle){ clearInterval(TIMER.handle); TIMER.handle=null; } }
function startTimer(seconds){
  stopTimer(); TIMER.remaining=seconds|0; const tEl=$('#timer');
  const tick=()=>{ if(tEl){ const m=String(Math.floor(TIMER.remaining/60)).padStart(2,'0'); const s=String(TIMER.remaining%60).padStart(2,'0'); tEl.textContent=`${m}:${s}`; }
    if(TIMER.remaining<=0){ stopTimer(); autoAdvanceOnTimeout(); return; } TIMER.remaining-=1; };
  tick(); TIMER.handle=setInterval(tick,1000);
}
function autoAdvanceOnTimeout() {
  const q = BUNDLE[CUR];

  // Αν δεν έχει βαθμολογηθεί, μην προχωράς σιωπηλά στην επόμενη
  if (!q?.scored) {
    alert('Ο χρόνος για αυτήν την ερώτηση τελείωσε. Μπορείς να πατήσεις "Αξιολόγηση" με ό,τι έχεις μέχρι τώρα ή να συμπληρώσεις λίγο ακόμη και μετά να βαθμολογήσεις.');
    return;
  }

  if (CUR < (BUNDLE.length - 1)) {
    CUR += 1;
    saveProgress();
    renderCurrent();
  }
}
/* ================== Data loaders ================== */
async function loadFour(category){
  const base = ensurePrefix(getAPIBase().trim());

  // Phase & Attempt (από το state του UI / URL)
  const phase   = (localStorage.getItem('QUIZ_PHASE') || 'PRE').trim(); // "PRE" | "POST"
  const attempt = (typeof ATTEMPT_NO !== 'undefined' ? ATTEMPT_NO : 1); // 1 | 2

 const url = joinUrl(
  base,
  `/questions/bundle` +
  `?category=${encodeURIComponent(category)}` +
  `&n_open=2&n_mc=2` +
  `&phase=${encodeURIComponent(phase)}` +
  `&attempt=${encodeURIComponent(attempt)}` +
  (DEBUG_SHOW_CORRECT ? `&include_correct=true` : ``)
);

  const data = await fetchJSON(url);

  // open: [{id, text}]
  const openQs = (data.open || []).slice(0, 2).map(q => ({
    id: q.id,
    text: String(q.text || ''),
    type: 'open',
    category
  }));

  const mcQs = (data.mc || []).slice(0, 2).map(q => {
    let options = [];
    if (Array.isArray(q.options)) {
      options = q.options.map(o => ({ id: String(o.id), text: String(o.text) }));
    } else if (Array.isArray(q.choices)) {
      options = q.choices.map((t, i) => ({ id: String(i), text: String(t) }));
    }

    const correct_id =
      typeof q.correct === 'number'
        ? String(q.correct)
        : (q.correct_id != null ? String(q.correct_id) : null);

    return {
      id: q.id,
      text: String(q.text || ''),
      type: 'mc',
      category,
      options,
      correct_id
    };
  });

  // Επιστρέφουμε πρώτα τα 2 MC και μετά τα 2 OPEN
  return [...mcQs, ...openQs];
} // ✅


/* ================== Start / navigation ================== */
async function startNewQuiz(){
  FINISHED = false;
  setBar(0);
  clearProgress();

  try{
    START_CATEGORY = (categoryEl?.value || 'Leadership').trim();
    BRANCHED = false;
    LEVEL = null;

    const starter = await loadFour(START_CATEGORY);

    BUNDLE = starter;
    CUR = 0;
    RESULTS = [];

    const st = $('#status');
    if (st){ st.dataset.type='ok'; st.textContent=`Ξεκινάμε με ${START_CATEGORY} (4 ερωτήσεις).`; }
    $('#quizBox')?.classList.remove('hidden');
    renderCurrent();
    saveProgress();

  }catch(err){
    $('#status')?.setAttribute('data-type','error');
    $('#status')&&($('#status').textContent=err?.message||'Σφάλμα φόρτωσης');
    alert(err?.message||'Σφάλμα φόρτωσης');
  }
}


categoryEl?.addEventListener('change', async (e) => {
  const prev = localStorage.getItem(LS.CATEGORY) || 'Leadership';
  localStorage.setItem(LS.CATEGORY, (e.target.value || '').trim());
  // καθάρισε και τα δύο phases για την ΠΡΟΗΓΟΥΜΕΝΗ και τη ΝΕΑ κατηγορία
  try {
    const user = getUserId();
    const oldCat = prev.trim();
    const newCat = (e.target.value || 'Leadership').trim();
    localStorage.removeItem(LS.PROGRESS(user, oldCat, 'PRE'));
    localStorage.removeItem(LS.PROGRESS(user, oldCat, 'POST'));
    localStorage.removeItem(LS.PROGRESS(user, newCat, 'PRE'));
    localStorage.removeItem(LS.PROGRESS(user, newCat, 'POST'));
  } catch {}
});

$('#btnPrev')?.addEventListener('click', async (e)=>{
  e.preventDefault(); e.stopPropagation();
  if (CUR > 0){
    const q = BUNDLE[CUR];
    if (q.type === 'open') q.answer = ($('#answer')?.value || '').trim();
    else {
      const sel = document.querySelector('input[name="mcOpt"]:checked');
      q.selected_id = sel ? sel.value : (q.selected_id || null);
    }
    saveProgress();
    await animateQuestionSwap(CUR - 1);
  }
});

/* “Επόμενο” όταν δεν είναι finish */
$('#btnNext')?.addEventListener('click', async (e)=>{
  const next = $('#btnNext');
  if (next?.dataset.role === 'finish') return;
  e.preventDefault(); e.stopPropagation();

  if (CUR === BUNDLE.length - 1 && !BRANCHED){
    alert('Κάνε πρώτα Βαθμολόγηση στην 4η ερώτηση για να συνεχίσουμε με τις προσαρμοστικές ερωτήσεις.');
    return;
  }
  if (CUR < BUNDLE.length - 1){
    const q = BUNDLE[CUR];
    if (q.type === 'open') q.answer = ($('#answer')?.value || '').trim();
    else {
      const sel = document.querySelector('input[name="mcOpt"]:checked');
      q.selected_id = sel ? sel.value : (q.selected_id || null);
    }
    saveProgress();
    await animateQuestionSwap(CUR + 1);
  }
});

/* keyboard shortcuts */
document.addEventListener('keydown', (e)=>{ if(e.key==='ArrowRight') $('#btnNext')?.click(); if(e.key==='ArrowLeft') $('#btnPrev')?.click(); });

/* ================== Coach Avatar helpers ================== */
const coachRoot   = document.getElementById('coachAvatar');
const coachBubble = coachRoot?.querySelector('.coach-avatar__bubble');
const coachText   = coachRoot?.querySelector('.coach-avatar__caption');
const coachImg    = coachRoot?.querySelector('.coach-avatar__image');

const COACH_IMG = {
  idle:  '/coach_closed.png',  // πριν από οποιαδήποτε βαθμολόγηση
  happy: '/coach_happy.png',
  sad:   '/coach_sad.png',
  moody: '/coach_moody.png',
};

// 🆕 Welcome state πριν γίνει οποιαδήποτε αξιολόγηση
function setCoachIdleWelcome() {
  if (!coachRoot || !coachBubble || !coachText || !coachImg) return;

  // Βάλε idle φάτσα
  coachImg.src = COACH_IMG.idle;

  // Βασικό animation (αναπνοή) όταν είναι ήρεμο
  coachBubble.classList.remove(
    'coach-avatar__bubble--thinking',
    'coach-avatar__bubble--mood-happy',
    'coach-avatar__bubble--mood-worried'
  );
  coachBubble.classList.add('coach-avatar__bubble--breathing');

  // Welcome μήνυμα
  coachText.textContent = 'Καλωσόρισες! Είμαι ο coach σου γι’ αυτό το quiz 🙂';
}

// όταν περιμένουμε απάντηση από το API
function setCoachThinking(on) {
  if (!coachRoot || !coachBubble) return;

  coachBubble.classList.toggle('coach-avatar__bubble--thinking', !!on);
  coachBubble.classList.toggle('coach-avatar__bubble--breathing', !on);

  if (coachText && on) {
    coachText.textContent = 'Υπολογίζω τα αποτελέσματά σου…';
  }

  // δεν αλλάζουμε εικόνα εδώ, κρατάμε την τελευταία “φάτσα”
}

// αλλάζει φάτσα + μήνυμα ανάλογα με τη βαθμολογία (0–10)
function setCoachMoodFromScore(score) {
  if (!coachBubble || !coachText || !coachImg) return;
  const s = Number(score || 0);

  coachBubble.classList.remove(
    'coach-avatar__bubble--mood-happy',
    'coach-avatar__bubble--mood-worried'
  );

  // σταματάει το idle breathing όταν μπαίνουμε σε score-mode
  coachBubble.classList.remove('coach-avatar__bubble--breathing');

  if (s >= 7.5) {
    // 🟢 υψηλή βαθμολογία
    coachBubble.classList.add('coach-avatar__bubble--mood-happy');
    coachImg.src = COACH_IMG.happy;
    coachText.textContent = 'Μπράβο, τα πας πολύ καλά! 💪';
  } else if (s <= 4.5) {
    // 🔴 χαμηλή βαθμολογία
    coachBubble.classList.add('coach-avatar__bubble--mood-worried');
    coachImg.src = COACH_IMG.sad;
    coachText.textContent = 'Κανένα άγχος, γι’ αυτό είμαι εδώ 😊';
  } else {
    // 🟡 μέτρια βαθμολογία
    coachImg.src = COACH_IMG.moody;
    coachText.textContent = 'Συνεχίζουμε, βήμα-βήμα!';
  }
}

// 🆕 Κάλεσέ το μία φορά στην αρχή (αν υπάρχει ο coach στο DOM)
if (coachRoot) {
  setCoachIdleWelcome();
}



/* ================== Scoring ================== */
function pick(...vals){ for(const v of vals){ if(v!=null && String(v).trim?.()!=='') return v; } return '—'; }
function normalizeAdvice(out){
  const coach = out?.coaching ?? out?.result?.coaching ?? (typeof out?.feedback==='object'? out.feedback : null) ?? {};
  return {
    keep: pick(coach.keep, coach.advice_keep, coach.positive, coach.strengths),
    change: pick(coach.change, coach.advice_change, coach.negative, coach.weaknesses, coach.improve),
    action: pick(coach.action, coach.next_steps, coach.plan, coach.suggested_action),
    drill: pick(coach.drill, coach.practice, coach.exercise, Array.isArray(coach.resources)? coach.resources.join(', ') : coach.resources),
  };
}
function pickScore(out){
  const s1=typeof out?.score==='number'?out.score:null;
  const s2=typeof out?.auto_score==='number'?out.auto_score:null;
  const s3=typeof out?.result?.score==='number'?out.result.score:null;
  return s1 ?? s2 ?? s3 ?? null;
}
function pickAnswerId(out){ return out?.answer_id ?? out?.result?.answer_id ?? out?.id ?? '—'; }

async function scoreOpen(API_BASE, category, question_id, text, user_id){
  const base=ensurePrefix(API_BASE); 
  const url=joinUrl(base,'/score-open?save=false&force_llm=true');
  return fetchJSON(url,{method:'POST',body:JSON.stringify({category,question_id,text,user_id})});
}

/* ================== BTN SCORE ================== */
let SCORING = false;

$('#btnScore')?.addEventListener('click', async (e) => {
  e.preventDefault();
  e.stopPropagation();
  if (SCORING) return; // anti double submit
  SCORING = true;
  setCoachThinking(true);
  if (!BUNDLE.length) {
    SCORING = false;
    return;
  }

  const q = BUNDLE[CUR];
  const API_BASE = getAPIBase().trim();
  const categoryLabel = q.category || (categoryEl?.value || 'Leadership').trim();
  const user_id = getUserId();
  const category = normalizeCategory(categoryLabel);

  const btn = $('#btnScore');
  const originalHTML = btn.innerHTML;

  // 🟡 Ενεργοποίηση spinner και disable κουμπιού
  btn.disabled = true;
  btn.innerHTML = `
    <span class="spinner" style="
      margin-right:6px;
      border:2px solid #fff;
      border-top:2px solid transparent;
      border-radius:50%;
      width:14px;
      height:14px;
      display:inline-block;
      vertical-align:middle;
      animation:spin 1s linear infinite;"></span>
    Αξιολόγηση...
  `;

  const busy = $('#busy');
  const resultBox = $('#result');
  // if (busy) busy.textContent = 'Αξιολόγηση...';
  resultBox?.classList.add('hidden');

  try {
    let out = null;

 // === OPEN TYPE ===
if (q.type === 'open') {
  const text = ($('#answer')?.value || '').trim();
  if (text.length < DEFAULTS.openMinLen) {
    alert(`Γράψε τουλάχιστον ${DEFAULTS.openMinLen} χαρακτήρες.`);
    $('#answer')?.focus();
    return;
  }

  // 1) LLM text scoring → measures (μόνο για features προς GLMP)
  const sres = await scoreOpen(API_BASE, categoryLabel, q.id, text, user_id);
  const t = sres?.measures || sres || {};
  const textMeasures = {
    clarity: toNum(t.clarity),
    coherence: toNum(t.coherence),
    topic_relevance: toNum(t.topic_relevance),
    vocabulary_range: toNum(t.vocabulary_range),
  };

  // 2) GLMP με text → αυτό είναι το score που βλέπει ο χρήστης στο quiz
  const base = ensurePrefix(API_BASE);
  const url = joinUrl(base, '/glmp/evaluate-and-save');
  const payload = {
    meta: { userId: user_id, answerId: q.id, category, modalities: ['text'] },
    text: { ...textMeasures, raw: text },
  };
  console.log('[OPEN] GLMP payload →', payload, 'POST', url);
  out = await fetchJSON(url, { method: 'POST', body: JSON.stringify(payload) });
  console.log('[OPEN] GLMP response ←', out);

  // 3) Πάρε το GLMP score (0–10)
  const glmpScore = (typeof out?.score === 'number') ? out.score : pickScore(out);

  // 4) Στείλ’ το στο backend για να το δει και το Rater UI 1:1
  if (typeof glmpScore === 'number') {
    try {
      const syncUrl = joinUrl(base, '/score-open-from-glmp?save=true');
      await fetchJSON(syncUrl, {
        method: 'POST',
        body: JSON.stringify({
          user_id: user_id,
          category: categoryLabel,  // "Leadership", "Teamwork", κλπ.
          question_id: q.id,
          text,
          score: glmpScore,         // 🔥 ίδιος βαθμός με αυτόν του quiz
        }),
      });
    } catch (e) {
      console.warn('[OPEN] failed to sync GLMP score to autorating', e);
    }
  }

  // 5) Κράτα την απάντηση στο local state
  q.answer = text;
  if (out && typeof out.id !== 'undefined') q.answerId = out.id;
}
    // === MULTIPLE CHOICE TYPE ===
    else {
      const radio = document.querySelector('input[name="mcOpt"]:checked');
      const selected_id = radio ? radio.value : (q.selected_id || null);
      if (!selected_id) {
        alert('Επίλεξε μία απάντηση.');
        return;
      }

      const correct_id = (q.correct_id != null) ? String(q.correct_id) : null;
      const acc = (correct_id != null) ? (String(selected_id) === correct_id ? 1 : 0) : 0;

      const base = ensurePrefix(API_BASE);
      const url = joinUrl(base, '/score-mc?save=true&force_llm=true');
       const payload = {
         user_id: user_id,
         category: category,          // ή categoryLabel, δουλεύει και έτσι
         question_id: q.id,
         question_text: q.text,
         options: q.options || [],
         selected_id,
         correct_id,
        };
      console.warn("DEBUG MC PAYLOAD", payload);
      console.log('[MC] GLMP payload →', payload, 'POST', url);
      out = await fetchJSON(url, { method: 'POST', body: JSON.stringify(payload) });
      console.log('[MC] GLMP response ←', out);

      q.selected_id = selected_id;
      if (out && typeof out.id !== 'undefined'){
      q.answerId = out.id;}
    }

    // === UI ενημέρωση ===
    const scoreVal = (typeof out?.score === 'number') ? out.score : pickScore(out);
    if ($('#score')) $('#score').textContent = (scoreVal ?? '').toString();
    if ($('#answerId')) $('#answerId').textContent = pickAnswerId(out);
    setCoachMoodFromScore(scoreVal);

    const adv = normalizeAdvice(out) || { keep: '', change: '', action: '', drill: '' };
    if ($('#keep')) $('#keep').textContent = adv.keep || '';
    if ($('#change')) $('#change').textContent = adv.change || '';
    if ($('#action')) $('#action').textContent = adv.action || '';
    if ($('#drill')) $('#drill').textContent = adv.drill || '';

    resultBox?.classList.remove('hidden');

    // 🆕 μαρκάρουμε την τρέχουσα ερώτηση ως βαθμολογημένη
    q.scored = true;
    updateNextButtonState();

    RESULTS.push({
      user_id,
      category: categoryLabel,
      question_id: q.id,
      type: q.type,
      selected_id: q.selected_id || null,
      text: q.answer || '',
      score: scoreVal ?? null,
      correct_id: q.correct_id ?? null,
    });
    saveProgress();

    // === Branch μετά την 4η ===
    if (!BRANCHED && CUR === 3) {
      const first4 = RESULTS.slice(0, 4).map(r => (typeof r.score === 'number' ? r.score : 0));
      const avg = first4.length ? (first4.reduce((a, b) => a + b, 0) / first4.length) : 0;
      LEVEL = bandFromAvg(avg);
      BRANCHED = true;

      const others = ALL_CATEGORIES.filter(c => c !== START_CATEGORY);
      const batches = [];
      for (const cat of others) batches.push(await loadFour(cat));
      BUNDLE = [...BUNDLE, ...batches.flat()];

      const lvl = $('#levelBadge');
      if (lvl) {
        lvl.textContent = `LEVEL: ${LEVEL.toUpperCase()}`;
        lvl.dataset.level = LEVEL;
      }

      stopTimer();
      startTimer(DEFAULTS.secondsPerQuestion);
      saveProgress();
    }

  } catch (err) {
    console.error('[Score Error]', err);
    alert('Σφάλμα στη βαθμολόγηση: ' + (err?.message || err));
  } finally {
    // 🟢 Επαναφορά κουμπιού
    if (busy) busy.textContent = '';
    btn.disabled = false;
    btn.innerHTML = originalHTML;
    SCORING = false;
    setCoachThinking(false);
  }
});


/* ================== Summary helpers ================== */
function buildSessionFromResults(results){
  const byCategory={}; const allScores=[];
  for(const r of results){ const cat=r.category||'General'; (byCategory[cat] ||= []).push(r); if(typeof r.score==='number') allScores.push(r.score); }
  return { byCategory, ordered:Object.keys(byCategory), allScores };
}
function computeSummary(session){
  if(!session) return { perCategory:{}, weakestCategory:null, overall:0 };
  const perCategory={}; let weakestCategory=null; let weakestVal=Number.POSITIVE_INFINITY;
  const all=session.allScores||[]; const overall = all.length? all.reduce((a,b)=>a+b,0)/all.length : 0;
  for(const [cat,arr] of Object.entries(session.byCategory||{})){
    const s=(arr||[]).map(r=> typeof r.score==='number'? r.score : null).filter(v=>v!=null);
    const avg= s.length? (s.reduce((a,b)=>a+b,0)/s.length) : 0;
    const rounded = Math.round(avg*100)/100;
    perCategory[cat]=rounded;
    if(avg < weakestVal){ weakestVal=avg; weakestCategory=cat; }
  }
  return { perCategory, weakestCategory, overall: Math.round(overall*100)/100 };
}

/* ========== Materials (single source of truth) ========== */
const CAT_SLUG = {
  "Leadership": "leadership",
  "Communication": "communication",
  "Teamwork": "teamwork",
  "Problem Solving": "problem_solving",
};
function bandFromScore10(x){
  const s = Number(x || 0);
  if (s < 4.5) return 'low';
  if (s >= 7.5) return 'high';
  return 'mid';
}
function makePdfUrl(categorySlug, level) {
  const cat = String(categorySlug || '').toLowerCase().replace(/\s+/g, '_');
  const lvl = String(level || '').toLowerCase();
  // Τα PDF είναι στο public/pdf/<category>_<level>.pdf
  return `/pdf/${cat}_${lvl}.pdf`;
}

// === COURSE PACK PAGES MAP (για attempt 1) ===
const COURSE_PACK_PAGES = {
  Communication: {
    low: [
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "1–6",
        note: "Βασικές αρχές σαφήνειας και τεχνικής γραφής."
      },
      {
        pdf: "Δ. Δομή και περιεχόμενο τεχνικών κειμένων",
        pages: "1–4",
        note: "Εισαγωγή στη βασική δομή ενός τεχνικού κειμένου."
      },
      {
        pdf: "ΣΤ. Ανάπτυξη Δεξιοτήτων Τεχνικής Παρουσίασης",
        pages: "1–4",
        note: "Πρώτες αρχές για το πώς παρουσιάζουμε τεχνικό περιεχόμενο."
      }
    ],
    mid: [
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "7–12",
        note: "Πρακτικές συμβουλές για βελτίωση σαφήνειας και συνοχής."
      },
      {
        pdf: "Δ. Δομή και περιεχόμενο τεχνικών κειμένων",
        pages: "5–10",
        note: "Ιεράρχηση περιεχομένου και καλύτερη ροή επιχειρημάτων."
      },
      {
        pdf: "ΣΤ. Ανάπτυξη Δεξιοτήτων Τεχνικής Παρουσίασης",
        pages: "5–10 | 41",
        note: "Βασική δομή τεχνικής παρουσίασης και storytelling. | Πολυδιάστατη επικοινωνία"
      }
    ],
    high: [
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "13–18",
        note: "Προχωρημένες τεχνικές σύνθεσης και βελτίωσης κειμένου."
      },
      {
        pdf: "Δ. Δομή και περιεχόμενο τεχνικών κειμένων",
        pages: "11–14",
        note: "Συνοχή, ρυθμός κειμένου και σύνδεση παραγράφων."
      },
      {
        pdf: "ΣΤ. Ανάπτυξη Δεξιοτήτων Τεχνικής Παρουσίασης",
        pages: "11–16 | 41 | 45",
        note: "Προχωρημένες τεχνικές παρουσίασης και αφήγησης. | Ολοκληρωμένη έκφραση. | Αλληλεπίδραση και εμπιστοσύνη"
      }
    ]
  },

  Teamwork: {
    low: [
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "7–10",
        note: "Συνεργασία μεταξύ μηχανικών στη συγγραφή κειμένων."
      },
      {
        pdf: "Δ. Δομή και περιεχόμενο τεχνικών κειμένων",
        pages: "27–28",
        note: "Ζήτηση βοήθειας για λάθη και Βοήθεια σε ορολογία."
      },
      {
        pdf: "Γ. Βιβλιογραφική αναζήτηση και οργάνωση",
        pages: "2–4",
        note: "Πώς μοιραζόμαστε την αναζήτηση και τα ευρήματα."
      }
    ],
    mid: [
      {
        pdf: "Ε. Η πρώτη προσέγγιση",
        pages: "9-10",
        note: "Γνώση των συνεργατών ως κοινό και Συνάδελφοι ως αποδέκτες."
      },
      {
        pdf: "Β. Βιβλιογραφική αναζήτηση και οργάνωση",
        pages: "6",
        note: "Αναζήτηση καθοδήγησης εντός ομάδας."
      },
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "10",
        note: "Αναγνώριση συμβολής άλλων (αναφορές)."
      }
    ],
    high: [
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "13-14",
        note: "Αναγνώριση συμβολής σε βάθος."
      },
      {
        pdf: "Β. Βιβλιογραφική αναζήτηση και οργάνωση ",
        pages: "4-5",
        note: "Σύνδεση με την επιστημονική κοινότητα και Εναρμόνιση με το συλλογικό πλαίσιο"
      },
      {
        pdf: "ΣΤ. Ανάπτυξη Δεξιοτήτων Τεχνικής Παρουσίασης",
        pages: "8–12",
        note: "Ομαδική παρουσίαση, ρόλοι και κύκλοι feedback."
      }
      ,{
        pdf: "Ε. Η πρώτη προσέγγιση",
        pages: "12",
        note: "Διαχείριση πολλαπλών ενδιαφερομένων."
      }
    ]
  },

  "Problem Solving": {
    low: [
      {
        pdf: "Γ. Βιβλιογραφική αναζήτηση και οργάνωση",
        pages: "12-16",
        note: "Αδυναμία κατανόησης πολύπλοκων εργασιών και Έλλειψη οργάνωσης πληροφοριών"
      },
      {
        pdf: "Β. Βιβλιογραφική αναζήτηση και οργάνωση (Μέρος Α)",
        pages: "1–4",
        note: "Βασικές στρατηγικές για να βρεις σχετικό υλικό."
      },
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "12–14",
        note: "Οργάνωση σκέψης πριν ξεκινήσεις να γράφεις τη λύση."
      }
    ],
    mid: [
      {
        pdf: "Β. Βιβλιογραφική αναζήτηση και οργάνωση (Μέρος Α)",
        pages: "5–10",
        note: "Κριτική αξιολόγηση πηγών και σύνδεσή τους με το πρόβλημα."
      },
      {
        pdf: "Γ. Βιβλιογραφική αναζήτηση και οργάνωση (Μέρος Β)",
        pages: "3–7",
        note: "Δομημένη ανάλυση πληροφοριών και επιλογή κατάλληλων πηγών."
      },
      {
        pdf: "Δ. Δομή και περιεχόμενο τεχνικών κειμένων",
        pages: "1–4",
        note: "Πώς χτίζεις λογική δομή για να εξηγήσεις μια λύση."
      }
    ],
    high: [
      {
        pdf: "Γ. Βιβλιογραφική αναζήτηση και οργάνωση (Μέρος Β)",
        pages: "8–13",
        note: "Σύνθεση γνώσης από πολλές πηγές για πολύπλοκα προβλήματα και Βαθιά ανάλυση."
      },
      {
        pdf: "Δ. Δομή και περιεχόμενο τεχνικών κειμένων",
        pages: "5–10",
        note: "Σύνδεση συμπερασμάτων με αποδείξεις και τεκμηρίωση."
      },
      {
        pdf: "Ε. Η πρώτη προσέγγιση",
        pages: "6–8",
        note: "Προχωρημένη αιτιολόγηση και σύγκριση εναλλακτικών λύσεων."
      }
    ]
  },
  Leadership: {
    low: [
      {
        pdf: "Γ. Βιβλιογραφική αναζήτηση και οργάνωση ",
        pages: "2",
        note: "Έλλειψη πρωτοβουλίας"
      },
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "7-10",
        note: "Υποτίμηση της συγγραφής, Βασικές δεξιότητες και Εντολές αντί καθοδήγησης"
      },
    ],
    mid: [
      {
        pdf: "Ε. Η πρώτη προσέγγιση",
        pages: "5–9",
        note: "Γνώση του κοινού και Αναφορά σε ανώτερους"
      },
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "6–10",
        note: "Αυξημένες ευθύνες σε υψηλότερες θέσεις και Λήψη αποφάσεων από managers"
      },
    ],
    high: [
      {
        pdf: "ΣΤ. Ανάπτυξη Δεξιοτήτων Τεχνικής Παρουσίασης",
        pages: "10–16",
        note: "Προχωρημένες τεχνικές παρουσίασης, χειρισμός δύσκολου κοινού και ηγεσία σε συζητήσεις."
      },
      {
        pdf: "Α. Τεχνική συγγραφή και Μηχανικοί",
        pages: "11–15",
        note: "Ηγετικός ρόλος στη διαμόρφωση τελικού τεχνικού κειμένου και λήψη αποφάσεων."
      },
      {
        pdf: "Γ. Βιβλιογραφική αναζήτηση και οργάνωση (Μέρος Β)",
        pages: "8–12",
        note: "Στρατηγικές αποφάσεις για το τι μπαίνει/βγαίνει από τη βιβλιογραφία και πώς κατευθύνεις την ομάδα."
      },
    ],
  },
};
function buildCoursePackSuggestions(summary) {
  const per = summary?.perCategory || {};
  if (!Object.keys(per).length) return [];

  const out = [];

  for (const [label, avg] of Object.entries(per)) {
    const band = bandFromScore10(avg); // low / mid / high
    const cfg  = COURSE_PACK_PAGES[label];
    if (!cfg) continue;

    const recs = cfg[band] || [];
    recs.forEach((r) => {
      out.push({
        category: label,
        band,
        pdf: r.pdf,
        pages: r.pages,
        note: r.note || "",
      });
    });
  }

  return out;
}

function renderCoursePackHTML(suggestions) {
  const items = Array.isArray(suggestions) ? suggestions : [];
  if (!items.length) return "";

  const lis = items
    .map((s) => {
      return `<li>
        <b>${s.category}</b> (<i>${s.band}</i>): 
        <span>δες τις σελίδες <b>${s.pages}</b> στο <u>${s.pdf}</u></span>
        ${s.note ? `<br/><small>${s.note}</small>` : ""}
      </li>`;
    })
    .join("");

  return `
    <div style="margin-top:16px;">
      <b>🎯 Στο εκπαιδευτικό υλικό του μαθήματος προτείνουμε:</b>
      <ul>${lis}</ul>
    </div>
  `;
}

// === Fallback PDFs από τα averages του summary ===
function buildMaterialsFromSummary(summary){
  const per = summary?.perCategory || {};
  const out = [];
  for (const [label, avg] of Object.entries(per)){
    const slug = CAT_SLUG[label] || String(label || '').toLowerCase().replace(/\s+/g,'_');
    const lvl  = bandFromScore10(avg); // low | mid | high
    out.push({ category: slug, level: lvl, url: makePdfUrl(slug, lvl) });
  }
  return out;
}

/** Ενιαία παραγωγή υλικών: backend > fallback από summary */
function resolveMaterials(quizComplete, summary){
  if (quizComplete && Array.isArray(quizComplete.materials) && quizComplete.materials.length){
    return quizComplete.materials.map(m => ({
      category: m.category || '',
      level: (m.level || '').toString().toLowerCase(),
      url: m.url || '#',
    }));
  }
  const per = summary?.perCategory || {};
  return Object.entries(per).map(([label, avg]) => {
    const slug = CAT_SLUG[label] || label.toLowerCase().replace(/\s+/g,'_');
    const lvl  = bandFromScore10(avg);
    return { category: slug, level: lvl, url: makePdfUrl(slug, lvl) };
  });
}
function prettyCat(labelOrSlug){
  const map = { leadership:'Leadership', communication:'Communication', teamwork:'Teamwork', problem_solving:'Problem Solving' };
  const k = String(labelOrSlug||'').toLowerCase().replace(/\s+/g,'_');
  return map[k] || labelOrSlug;
}
function renderMaterialsHTML(materials) {
  const items = Array.isArray(materials) ? materials : [];
  if (!items.length) return '';
  const lis = items.map(m => {
    const cat = prettyCat(m.category || '');
    const lvl = (m.level || '').toString();
    const href = m.url || '#';
    return `<li>${cat} — <i>${lvl}</i>: <a href="${href}" target="_blank" rel="noopener">άνοιγμα PDF</a></li>`;
  }).join('');
  return `<div style="margin-top:12px;"><b>Προτεινόμενα PDFs:</b><ul>${lis}</ul></div>`;
}

/* ================== Session-Plan (new) ================== */
function buildPlanPayload(userId, summary, results){
  const perCategory = summary.perCategory || {};
  const ranked = Object.entries(perCategory).sort((a,b)=>a[1]-b[1]).map(([name,avg])=>({name, avg}));
  const weakest = ranked[0]?.name || null;
  return {
    meta: {
      userId,
      level: (LEVEL || bandFromAvg(summary.overall)),
      overall: summary.overall,
      perCategory,
      weakestCategory: weakest
    },
    answers: results.map(r => ({
      questionId: r.question_id,
      category: r.category,
      type: r.type,
      score: (typeof r.score==='number'? r.score : null),
      selected_id: r.selected_id ?? null,
      correct_id: r.correct_id ?? null,
      text: (r.text || '')
    }))
  };
}

async function fetchSessionPlan(API_BASE, payload){
  const base = ensurePrefix(API_BASE);
  const url  = joinUrl(base, '/glmp/session-plan');
  return fetchJSON(url, { method: 'POST', body: JSON.stringify(payload) });
}

function renderPlanHTML(plan, summary, materials) {
  const levelLabel = (LEVEL || bandFromAvg(summary.overall) || "").toUpperCase();
  const per = summary.perCategory || {};
  const list = Object.entries(per)
    .map(([c,v]) => `<li>${c}: <b>${Number(v).toFixed(2)}</b></li>`).join('');

  const p = plan || {};
  const title = p.title || 'Πλάνο 2 εβδομάδων (personalized)';
  const why   = p.summary || 'Το πλάνο εστιάζει στα αδύναμα σημεία σας για γρήγορη βελτίωση.';
  const steps = Array.isArray(p.steps) ? p.steps : [];
  const resources = Array.isArray(p.resources) ? p.resources : [];

  const matsHtml = renderMaterialsHTML(Array.isArray(materials) ? materials : []);

  // 🆕 ΝΕΟ: προτάσεις από course pack ΜΟΝΟ στο PRE (attempt=1)
  const phase = (localStorage.getItem('QUIZ_PHASE') || 'PRE').trim();
  const courseSuggestions =
    phase === 'PRE' ? buildCoursePackSuggestions(summary) : [];
  const coursePackHtml = renderCoursePackHTML(courseSuggestions);

  const thanks = `<p style="margin-top:16px;">Ευχαριστούμε που ολοκληρώσατε το τεστ! 🎉</p>`;

  return [
    `<p><b>Level:</b> ${levelLabel}</p>`,
    `<p><b>Συνολικός μέσος όρος:</b> ${Number(summary.overall).toFixed(2)}</p>`,
    `<div style="margin:8px 0;"><b>Μέσοι όροι ανά κατηγορία:</b><ul>${list}</ul></div>`,
    (summary.weakestCategory ? `<p><b>Προτεινόμενη μελέτη (αδύναμο πεδίο):</b> ${summary.weakestCategory}</p>` : ''),
    `<hr/>`,
    `<h4 style="margin:12px 0 4px;">${title}</h4>`,
    `<p><i>Σύνοψη πλάνου:</i> ${why}</p>`,
    (steps.length ? `<div><b>Βήματα (2 εβδομάδες):</b><ol>${steps.map(s=>`<li>${s}</li>`).join('')}</ol></div>` : ''),
    // (resources.length ? `<div><b>Πόροι:</b><ul>${resources.map(r=>`<li><a href="${r.url}" target="_blank" rel="noopener">${r.title}</a></li>`).join('')}</ul></div>` : ''),
    matsHtml,
    // 🆕 εδώ μπαίνει το block με τις συγκεκριμένες σελίδες
    coursePackHtml,
    thanks,
    `<p>Μπορείς να κατεβάσεις CSV με τα αποτελέσματά σου από τα κουμπιά παρακάτω.</p>`
  ].join('');
}




function exportSessionCSV(){
  const uid = getUserId();

  // 1) Header
  const headers = [
    'user_id','category','question_id','type','score','selected_id','correct_id','text'
  ];

  // 2) Helper: safe quote & normalize
  const SEP = ';';                    // Excel-friendly για ελληνικά Windows
  const EOL = '\r\n';                 // CRLF
  const q = (v) => {
    const s = (v == null ? '' : String(v));
    // καθάρισε CR/LF και υπερβολικά κενά για πιο "φιλικό" preview στο Excel
    const cleaned = s.replace(/\r?\n|\r/g, ' ').replace(/\s+/g, ' ').trim();
    // escape εσωτερικά " με ""
    return `"${cleaned.replace(/"/g, '""')}"`;
  };

  // 3) Rows
  const rows = [];
  rows.push(headers.map(q).join(SEP));

  for (const r of RESULTS) {
    rows.push([
      uid,
      r.category || '',
      r.question_id || r.id || '',
      r.type || '',
      (typeof r.score === 'number' ? r.score : ''),
      r.selected_id || '',
      r.correct_id || '',
      (r.text || '')
    ].map(q).join(SEP));
  }

  // 4) BOM για σωστό UTF-8 στο Excel + CRLF line endings
  const BOM = '\uFEFF';
  const csv = BOM + rows.join(EOL) + EOL;

  // 5) Download
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = `softskills_results_${uid}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}



function exportPlanTXT(plan, summary, materials) {
  const uid = getUserId();
  const levelLabel = (LEVEL || bandFromAvg(summary.overall) || "").toUpperCase();
  const per = summary.perCategory || {};
  const phase = (localStorage.getItem('QUIZ_PHASE') || 'PRE').trim(); // "PRE" | "POST"
  const attempt = ATTEMPT_NO || 1;

  const lines = [];

  lines.push('Soft Skills Quiz – Ατομικό Πλάνο Μάθησης');
  lines.push(`Χρήστης: ${uid}`);
  lines.push(`Attempt: ${attempt} (${phase === 'PRE' ? 'Αρχικό τεστ (PRE)' : 'Τελικό τεστ (POST)'})`);
  lines.push('');
  lines.push(`Συνολικός μέσος όρος: ${Number(summary.overall || 0).toFixed(2)} / 10`);
  lines.push(`Level: ${levelLabel}`);
  lines.push('');

  lines.push('Μέσοι όροι ανά κατηγορία:');
  for (const [cat, v] of Object.entries(per)) {
    lines.push(`- ${cat}: ${Number(v || 0).toFixed(2)} / 10`);
  }
  lines.push('');

  const title = plan?.title || 'Πλάνο 2 εβδομάδων (personalized)';
  const why   = plan?.summary || 'Το πλάνο εστιάζει στα αδύναμα σημεία σου για γρήγορη βελτίωση.';
  lines.push(`Τίτλος πλάνου: ${title}`);
  lines.push('');
  lines.push('Σύνοψη:');
  lines.push(why);
  lines.push('');

  if (Array.isArray(plan?.steps) && plan.steps.length) {
    lines.push('Βήματα (2 εβδομάδες):');
    plan.steps.forEach((step, idx) => {
      lines.push(`${idx + 1}. ${step}`);
    });
    lines.push('');
  }

  // 🔀 Διαχείριση PDFs & course pack ανά attempt
  let effectiveMaterials = Array.isArray(materials) ? materials : [];
  let courseSuggestions = [];

  if (phase === 'PRE') {
    // Attempt 1: δείχνουμε και PDFs και course-pack σελίδες
    if (effectiveMaterials.length) {
      lines.push('Προτεινόμενα PDFs για μελέτη:');
      effectiveMaterials.forEach((m) => {
        const cat = prettyCat(m.category || '');
        const lvl = (m.level || '').toString();
        lines.push(`- ${cat} [${lvl}]: ${m.url}`);
      });
      lines.push('');
    }

    courseSuggestions = buildCoursePackSuggestions(summary);
    if (courseSuggestions.length) {
      lines.push('Προτεινόμενες σελίδες από το υλικό μαθήματος:');
      courseSuggestions.forEach((s, idx) => {
        lines.push(`${idx + 1}. Κατηγορία: ${s.category} (level: ${s.band})`);
        lines.push(`   PDF: ${s.pdf}`);
        lines.push(`   Σελίδες: ${s.pages}`);
        if (s.note) lines.push(`   Σχόλιο: ${s.note}`);
      });
      lines.push('');
    }
  } else {
    // Attempt 2 (POST): δεν βάζουμε καθόλου PDFs ούτε course-pack
    // κρατάμε μόνο τα σκορ & το πλάνο
  }

  lines.push('Σημείωση: Αυτό το πλάνο βασίζεται στις απαντήσεις σου στο συγκεκριμένο attempt του quiz και μπορείς να το χρησιμοποιήσεις ως οδηγό για στοχευμένη μελέτη.');

  const txt = lines.join('\r\n');
  const blob = new Blob([txt], { type: 'text/plain;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = `softskills_plan_${uid}_attempt${attempt}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ================== Modal ================== */
function ensureModal(){
  let bd = document.querySelector('#thanksBackdrop');
  if (bd) return bd;

  bd = document.createElement('div');
  bd.id = 'thanksBackdrop';
  bd.className = 'backdrop';

  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-labelledby', 'final-title');

  const header = document.createElement('div');
  header.className = 'modal__header';
  header.innerHTML = `<h3 id="final-title">Ολοκλήρωση αξιολόγησης</h3>`;

  const body = document.createElement('div');
  body.className = 'modal__body';
  body.id = 'modalBody';

  const footer = document.createElement('div');
  footer.className = 'modal__actions';

  const btnCsv = document.createElement('button');
  btnCsv.id = 'btnThanksExport';
  btnCsv.type = 'button';
  btnCsv.className = 'btn btn-secondary';
  btnCsv.textContent = 'Κατέβασμα CSV';


  const btnPlan = document.createElement('button');
  btnPlan.id = 'btnThanksPlan';
  btnPlan.type = 'button';
  btnPlan.className = 'btn btn-secondary';
  btnPlan.textContent = 'Κατέβασμα Πλάνου & Προτάσεων';

  const btnClose = document.createElement('button');
  btnClose.id = 'btnThanksClose';
  btnClose.type = 'button';
  btnClose.className = 'btn btn-primary';
  btnClose.textContent = 'Κλείσιμο';
  btnClose.disabled = false;

  // 🔒 ΔΕΝ βασιζόμαστε πουθενά αλλού — δένουμε εδώ τον handler
  btnClose.addEventListener('click', (e)=>{
    e.preventDefault();
    e.stopPropagation();
    closeThanksModal();       // θα κάνει reload & επιστροφή στην αρχή
  });

  // Εναλλακτικό fallback με middle-click/enter/space
  btnClose.addEventListener('keydown', (e)=>{
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      closeThanksModal();
    }
  });

  footer.append(btnCsv, btnPlan, btnClose);
  modal.append(header, body, footer);
  bd.appendChild(modal);
  document.body.appendChild(bd);
  return bd;
}



/* Κεντρικό κλείσιμο του modal (με καθάρισμα listeners) */
function closeThanksModal(){
  const bd = document.getElementById('thanksBackdrop');
  if (!bd) return;

  bd.classList.remove('show');

  // καθάρισε Esc handler αν υπάρχει
  if (bd._escHandler){
    document.removeEventListener('keydown', bd._escHandler);
    bd._escHandler = null;
  }

  // μικρή καθυστέρηση για το transition, έπειτα reload στην αρχική
  setTimeout(() => {
    window.location.reload(); // κρατά token/attempt και σε γυρίζει στην αρχή
  }, 200);
}

function bindModalButtons(bd, planObj, summary, materials){
  // κουμπί κλεισίματος
  bd.querySelector('#btnThanksClose')?.addEventListener('click', (e)=>{
    e.preventDefault();
    closeThanksModal();
  });

  // export CSV (υπήρχε ήδη)
  const btnCsv = bd.querySelector('#btnThanksExport');
  btnCsv?.addEventListener('click', (e)=>{
    e.preventDefault();
    exportSessionCSV();
  });

  const btnPlan = bd.querySelector('#btnThanksPlan');
  btnPlan?.addEventListener('click', (e)=>{
    e.preventDefault();
    exportPlanTXT(planObj, summary, materials);
  });

  // κλικ πάνω στο backdrop (έξω από το modal) => κλείσιμο
  bd.addEventListener('click', (e)=>{
    if (e.target === bd) closeThanksModal();
  });

  // Esc => κλείσιμο
  bd._escHandler = (ev) => {
    if (ev.key === 'Escape'){
      ev.preventDefault();
      closeThanksModal();
    }
  };
  document.addEventListener('keydown', bd._escHandler);
}

/* ================== QUIZ COMPLETE helper (ΝΕΟ) ================== */
async function postQuizComplete({ userId, phase, results }) {
  const base = ensurePrefix(getAPIBase().trim());
  const url  = joinUrl(base, '/quiz/complete');

  // Δίνουμε προτεραιότητα σε API key από localStorage (UI override).
  const headers = {};
  const k = (localStorage.getItem(LS.API_KEY) || '').trim();
  if (k) headers['x-api-key'] = k;

  return fetchJSON(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ userId, phase, results }),
  });
}

function materialsFromServerLevels(levelsObj){
  if (!levelsObj || typeof levelsObj !== 'object') return [];

  const keyToLabel = {
    leadership: 'Leadership',
    communication: 'Communication',
    teamwork: 'Teamwork',
    problem_solving: 'Problem Solving',
  };

  const out = [];
  for (const [key, lvlRaw] of Object.entries(levelsObj)){
    const label = keyToLabel[key] || key.replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase());
    const lvl = String(lvlRaw || '').toLowerCase();    // low | mid | high από backend
    const url = makePdfUrl(label, lvl);                // φτιάχνουμε μόνοι μας το σωστό URL
    out.push({ category: label, level: lvl, url });
  }
  return out;
}

/* ================== Finale ================== */
async function finalizeQuiz(){
  if (FINISHED) return;
  FINISHED = true;

  // Αποθήκευση τελευταίας απάντησης
  const q = BUNDLE[CUR];
  if (q) {
    if (q.type === 'open') {
      q.answer = ($('#answer')?.value || '').trim();
    } else {
      const radio = document.querySelector('input[name="mcOpt"]:checked');
      q.selected_id = radio ? radio.value : (q.selected_id || null);
    }
    saveProgress();
  }

  // Build session/summary
  const session = buildSessionFromResults(RESULTS);
  const summary = computeSummary(session);

  // Fallback materials (από τα averages του frontend)
  const fallbackMaterials = buildMaterialsFromSummary(summary);

  // Προετοιμασία payload για /quiz/complete
  const resultsForApi = {};
  for (const [cat, val] of Object.entries(summary.perCategory || {})) {
    resultsForApi[cat] = Math.round((val || 0) * 100);
  }
  const userId = (localStorage.getItem('QUIZ_USER') || getUserId() || 'anonymous').trim();
  const phase  = (localStorage.getItem('QUIZ_PHASE') || 'PRE').trim();

  // Κάλεσε backend
  let quizComplete = null;
  try {
    quizComplete = await postQuizComplete({ userId, phase, results: resultsForApi });
  } catch (e) {
    console.warn('quiz/complete failed', e);
    quizComplete = null;
  }

// για να βγάλουμε τα PDFs (low / mid / high).
  // const finalMaterials = buildMaterialsFromSummary(summary);

  // Αν θέλουμε να τα στείλουμε και πίσω στο server για logging:
    let finalMaterials = [];
  if (phase === 'PRE') {
    finalMaterials = buildMaterialsFromSummary(summary);

    // Αν θέλουμε να τα στείλουμε και πίσω στο server για logging:
    if (quizComplete) {
      quizComplete.materials = finalMaterials;
    }
  }

  // Ετοίμασε/άνοιξε modal
  const bd   = ensureModal();
  const body = bd.querySelector('#modalBody');
  const titleEl = bd.querySelector('#final-title');
  if (titleEl) titleEl.textContent = 'Ολοκλήρωση αξιολόγησης';
  if (body) body.innerHTML = `<div style="opacity:.8; padding:8px 0;">Φόρτωση πλάνου…</div>`;
  bd.classList.add('show');

  // Ζήτα πλάνο (ή fallback)
  let plan = null;
  try {
    const API_BASE = getAPIBase().trim();
    const payload = buildPlanPayload(getUserId(), summary, RESULTS);
    plan = await fetchSessionPlan(API_BASE, payload);
  } catch (e) {
    console.warn('[SessionPlan] fallback → client-only', e);
  }
  if (!plan) {
    const resources = suggestionsForSingle(summary.weakestCategory);
    plan = {
      title: 'Πλάνο 2 εβδομάδων (personalized)',
      summary: 'Η βελτίωση της δομής περιεχομένου είναι κρίσιμη για την αποτελεσματική επικοινωνία.',
      steps: [
        'Αναλύστε τη δομή του περιεχομένου σας και προσδιορίστε τα κύρια σημεία που θέλετε να μεταφέρετε.',
        'Δημιουργήστε ένα μικρό λογικό πλαίσιο για την παρουσίαση (εισαγωγή – κύριο μέρος – συμπέρασμα).',
        'Εξασκηθείτε στην παρουσίαση με τη νέα δομή, εστιάζοντας στη ροή και τη σύνδεση των ιδεών.'
      ],
      resources: (resources || [])
    };
  }

  // Πέρασε στο modal τα ΤΕΛΙΚΑ materials
  if (!quizComplete) quizComplete = {};
  quizComplete.materials = finalMaterials;

if (body) body.innerHTML = renderPlanHTML(plan, summary, finalMaterials);
bindModalButtons(bd, plan, summary, finalMaterials);
}

/* ================== Robust FINISH handler ================== */
document.addEventListener('click', (e)=>{
  const next = e.target.closest('#btnNext');
  if (!next) return;
  if (next.dataset.role !== 'finish') return;
  e.preventDefault(); e.stopPropagation();
  finalizeQuiz();
}, true);

/* ================== Initial status ================== */
;(function showReady(){
  const st = document.querySelector('#status');
  if (st) { st.dataset.type = 'ok'; st.textContent = 'Έτοιμο. Διάλεξε Κατηγορία και πάτα Έναρξη.'; }
})();

// ------- AUTO-RESTORE ON PAGE LOAD -------

window.addEventListener('DOMContentLoaded', () => {
  const restored = restoreProgressFromLocalStorage();
  if (!restored) {
    // Δεν βρέθηκε αποθηκευμένη πρόοδος → άσε το UI όπως είναι (intro & start)
    // Αν θες να κάνεις κάτι έξτρα στην πρώτη φόρτωση, βάλε το εδώ.
  }
});