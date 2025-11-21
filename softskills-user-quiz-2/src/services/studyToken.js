// src/services/studyToken.js

function getQueryParam(name) {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search || '');
  return params.get(name);
}

// Βασικό study token: από ?token= ή από localStorage
export function getStudyToken() {
  if (typeof window === 'undefined') return '';

  const fromUrl = getQueryParam('token');
  const fromLS  = window.localStorage.getItem('study_token');

  const token = fromUrl || fromLS || '';
  if (token) {
    window.localStorage.setItem('study_token', token);
  }
  return token;
}

// Από το URL (?attempt=1/2/3), default 1
export function getAttemptNo() {
  const raw = getQueryParam('attempt');
  const n = parseInt(raw || '1', 10);
  return (n === 1 || n === 2 || n === 3) ? n : 1;
}

// Placeholder: αν αργότερα θες "signed" token από backend
export async function ensureSignedStudyToken() {
  // προς το παρόν απλώς επιστρέφει το raw token
  return getStudyToken();
}
