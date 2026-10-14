/**
 * src/api.js — fetch wrapper gọi backend FastAPI (api-contract.md).
 *
 * Mọi hàm throw object `{ status, body }` khi !ok để UI phân biệt 403/404/...
 * không cần parse status từ Error message.
 */

const BASE = '' // proxy Vite đã trỏ `/api` + `/health` → :8000.

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
  const res = await fetch(url, { method: 'GET' })
  return _jsonOrThrow(res)
}

export async function putReview(meeting, items, changes) {
  const url = `${BASE}/api/v1/review?meeting=${encodeURIComponent(meeting)}`
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ items, changes }),
  })
  return _jsonOrThrow(res)
}

export async function postExport(meeting) {
  const url = `${BASE}/api/v1/export?meeting=${encodeURIComponent(meeting)}`
  const res = await fetch(url, { method: 'POST' })
  return _jsonOrThrow(res)
}

export async function getHealth() {
  const res = await fetch(`${BASE}/health`)
  return _jsonOrThrow(res)
}

export async function getTranscript(meeting) {
  const url = `${BASE}/api/v1/transcript?meeting=${encodeURIComponent(meeting)}`
  const res = await fetch(url, { method: 'GET' })
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
    body: form,
  })
  return _jsonOrThrow(res)
}