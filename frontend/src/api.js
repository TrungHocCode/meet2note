/**
 * src/api.js — fetch wrapper gọi backend FastAPI (api-contract.md).
 *
 * Mọi hàm throw object `{ status, body }` khi !ok để UI phân biệt 403/404/...
 * không cần parse status từ Error message.
 */

const BASE = '' // proxy Vite đã trỏ `/api` + `/health` + `/auth` → :8000.

// ─── Auth (P6b): access token trong localStorage, refresh trong cookie httpOnly ─

const TOKEN_KEY = 'm2n_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch (_e) {
    return ''
  }
}

function setToken(t) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  } catch (_e) {
    /* private mode — bỏ qua */
  }
}

function authHeaders(extra = {}) {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}`, ...extra } : { ...extra }
}

export async function login(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    credentials: 'include', // nhận refresh cookie httpOnly
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  })
  const body = await _jsonOrThrow(res)
  setToken(body.access_token)
  return getMe()
}

export async function register(email, password) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  await _jsonOrThrow(res) // 201 — chưa login, gọi login() tiếp
  return login(email, password)
}

export async function logout() {
  try {
    await fetch(`${BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders(),
    })
  } finally {
    setToken('')
  }
}

export async function getMe() {
  const res = await fetch(`${BASE}/auth/me`, {
    credentials: 'include',
    headers: authHeaders(),
  })
  return _jsonOrThrow(res)
}

async function _jsonOrThrow(res) {
  // 204 / rỗng → body = {}
  const text = await res.text()
  let body = {}
  if (text) {
    try {
      body = JSON.parse(text)
    } catch (_e) {
      body = { raw: text }
    }
  }
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`)
    err.status = res.status
    err.body = body
    throw err
  }
  return body
}

export async function getReview(meeting) {
  const url = `${BASE}/api/v1/review?meeting=${encodeURIComponent(meeting)}`
  const res = await fetch(url, {
    method: 'GET',
    credentials: 'include',
    headers: authHeaders(),
  })
  return _jsonOrThrow(res)
}

export async function putReview(meeting, items, changes) {
  const url = `${BASE}/api/v1/review?meeting=${encodeURIComponent(meeting)}`
  const res = await fetch(url, {
    method: 'PUT',
    credentials: 'include',
    headers: authHeaders({ 'content-type': 'application/json' }),
    body: JSON.stringify({ items, changes }),
  })
  return _jsonOrThrow(res)
}

export async function postExport(meeting) {
  const url = `${BASE}/api/v1/export?meeting=${encodeURIComponent(meeting)}`
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: authHeaders(),
  })
  return _jsonOrThrow(res)
}

export async function getHealth() {
  const res = await fetch(`${BASE}/health`)
  return _jsonOrThrow(res)
}

export async function listMeetings() {
  const res = await fetch(`${BASE}/api/v1/meetings`, {
    method: 'GET',
    credentials: 'include',
    headers: authHeaders(),
  })
  return _jsonOrThrow(res)
}

export async function getTranscript(meeting) {  const url = `${BASE}/api/v1/transcript?meeting=${encodeURIComponent(meeting)}`
  const res = await fetch(url, {
    method: 'GET',
    credentials: 'include',
    headers: authHeaders(),
  })
  return _jsonOrThrow(res)
}

export async function uploadMeeting({ file, meetingId, title, date, participants }) {
  const form = new FormData()
  form.append('file', file)
  if (meetingId) form.append('meeting_id', meetingId)
  form.append('title', title || file?.name || 'Cuộc họp upload')
  form.append('date', date)
  form.append('participants', participants || '[]')
  const res = await fetch(`${BASE}/api/v1/meetings/upload`, {
    method: 'POST',
    credentials: 'include',
    headers: authHeaders(), // KHÔNG set content-type — browser tự thêm boundary
    body: form,
  })
  return _jsonOrThrow(res)
}