/**
 * src/App.jsx — meet2note Review (P3).
 *
 * Spec UI: docs/spec/export-format.md §4.
 * - Sidebar: input meeting id, filter confidence (all/red/yellow/green),
 *   nút Export (khoá theo gate R6 + đếm thẻ đỏ).
 * - Main 4 cột: Quyết định | Công việc | Vướng mắc & Chưa chốt | Yêu cầu & Phản hồi.
 * - Thẻ: content + badge + evidence expandable (quote+ts+speaker+role) +
 *   3 nút Đồng ý / Sửa / Loại + form sửa inline (content/owner/due/link_to_decision).
 * - Discarded thu gọn dưới final.
 * - Banner `known_limitations` + hiển thị file export sau POST 200.
 *
 * Triết lý MVP: tối giản, không đẹp, gọi API thật (xem api.js).
 */

import { useEffect, useMemo, useState } from 'react'
import { getReview, putReview, postExport, getTranscript, uploadMeeting } from './api.js'
import './App.css'

// ─── Badge helpers ────────────────────────────────────────────────────────
function badge(conf) {
  const c = Number(conf ?? 0)
  if (c < 0.5) return { label: '🔴 đỏ', cls: 'badge-red' }
  if (c < 0.75) return { label: '🟡 vàng', cls: 'badge-yellow' }
  return { label: '🟢 xanh', cls: 'badge-green' }
}

function isRed(conf) {
  return Number(conf ?? 0) < 0.5
}

// ─── Card component ──────────────────────────────────────────────────────
function ItemCard({ item, onAgree, onEdit, onRemove, onShowEvidence }) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => initialDraft(item))
  const b = badge(item.confidence)

  const contentText =
    item.type === 'task' ? item.what || '' : item.content || ''

  return (
    <div className={`card ${b.cls}`}>
      <div className="card-head">
        <span className="card-id">{item.id}</span>
        <span className={`badge ${b.cls}`}>{b.label}</span>
        <span className="card-conf">{(Number(item.confidence ?? 0)).toFixed(2)}</span>
      </div>

      <div className="card-body">
        {!editing ? (
          <p className="card-content">{contentText}</p>
        ) : (
          <div className="card-edit">
            <label>
              Content:
              <textarea
                value={draft.content}
                onChange={(e) =>
                  setDraft({ ...draft, content: e.target.value })
                }
              />
            </label>
            {item.type === 'task' && (
              <>
                <label>
                  Owner:
                  <input
                    value={draft.owner}
                    onChange={(e) =>
                      setDraft({ ...draft, owner: e.target.value })
                    }
                  />
                </label>
                <label>
                  Due (YYYY-MM-DD hoặc TBD):
                  <input
                    value={draft.due}
                    onChange={(e) =>
                      setDraft({ ...draft, due: e.target.value })
                    }
                  />
                </label>
              </>
            )}
            <label>
              link_to_decision:
              <input
                value={draft.link_to_decision}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    link_to_decision: e.target.value,
                  })
                }
              />
            </label>
            <div className="row">
              <button
                onClick={() => {
                  onEdit(item, draft)
                  setEditing(false)
                }}
              >
                Lưu
              </button>
              <button onClick={() => setEditing(false)}>Huỷ</button>
            </div>
          </div>
        )}

        {/* Metadata phụ (decision reason / task due / blocker severity / ...) */}
        <ul className="card-meta">
          {item.type === 'decision' && (
            <>
              <li>decided_by: {item.decided_by || '—'}</li>
              {item.reason && <li>lý do: {item.reason}</li>}
              {item.supersedes?.length > 0 && (
                <li>thay thế: {item.supersedes.join(', ')}</li>
              )}
              {item.status && <li>status: {item.status}</li>}
            </>
          )}
          {item.type === 'task' && (
            <>
              <li>owner: {item.owner || 'TBD'}</li>
              <li>due: {item.due || 'TBD'}</li>
              {item.due_hint && <li>due_hint: {item.due_hint}</li>}
              {item.link_to_decision && (
                <li>link: {item.link_to_decision}</li>
              )}
            </>
          )}
          {item.type === 'blocker' && (
            <>
              <li>cần: {item.needs_action_from || 'TBD'}</li>
              {item.severity && <li>severity: {item.severity}</li>}
            </>
          )}
          {item.type === 'open_issue' && (
            <>
              <li>next_step: {item.next_step}</li>
              {item.next_step_owner && (
                <li>owner: {item.next_step_owner}</li>
              )}
              {item.system_generated && (
                <li className="hint">(system_generated)</li>
              )}
            </>
          )}
          {item.type === 'requirement' && (
            <>
              <li>origin: {item.origin}</li>
              <li>raised_by: {item.raised_by}</li>
            </>
          )}
        </ul>
      </div>

      {/* Evidence expandable */}
      {Array.isArray(item.evidence) && item.evidence.length > 0 && (
        <div className="card-evidence">
          <button className="link" onClick={() => setOpen(!open)}>
            {open ? '▾' : '▸'} {item.evidence.length} evidence
          </button>
          {open && (
            <ul>
              {item.evidence.map((ev, i) => (
                <li key={i}>
                  <button
                    className="link ts-btn"
                    title="Xem transcript quanh lượt này"
                    onClick={() => onShowEvidence && onShowEvidence(ev)}
                  >
                    [{ev.timestamp}]
                  </button>{' '}
                  <span className="speaker">{ev.speaker}</span>{' '}
                  <span className="role">({ev.role_in_discussion})</span>:{' '}
                  <span className="quote">“{ev.quote}”</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="card-actions">
        <button onClick={() => onAgree(item)}>Đồng ý</button>
        <button onClick={() => setEditing(true)}>Sửa</button>
        <button className="danger" onClick={() => onRemove(item)}>
          Loại
        </button>
      </div>
    </div>
  )
}

function initialDraft(item) {
  return {
    content: item.content ?? item.what ?? '',
    owner: item.owner ?? '',
    due: item.due ?? '',
    link_to_decision: item.link_to_decision ?? '',
  }
}

// ─── Discarded (under final decision) ─────────────────────────────────────
function DiscardedList({ items }) {
  if (!items.length) return null
  return (
    <details className="discarded">
      <summary>Lịch sử: thay thế {items.map((i) => i.id).join(', ')}</summary>
      {items.map((it) => (
        <div key={it.id} className="card discarded-card">
          <div className="card-head">
            <span className="card-id">{it.id}</span>
            <span className="badge badge-discarded">discarded</span>
          </div>
          <p className="card-content">{it.content}</p>
        </div>
      ))}
    </details>
  )
}

// ─── Main App ────────────────────────────────────────────────────────────
export default function App() {
  const [meetingId, setMeetingId] = useState('tc2')
  const [meetingInput, setMeetingInput] = useState('tc2')
  const [state, setState] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('all') // all | red | yellow | green
  const [exportFiles, setExportFiles] = useState(null)
  const [exportError, setExportError] = useState(null)
  // Transcript drawer: { meeting, turns, source, targetTurn } | null
  const [transcript, setTranscript] = useState(null)
  const [transcriptCache, setTranscriptCache] = useState({})
  // Upload form
  const [upFile, setUpFile] = useState(null)
  const [upId, setUpId] = useState('')
  const [upTitle, setUpTitle] = useState('')
  const [upDate, setUpDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [upParts, setUpParts] = useState('Lan (PM)\nNam (BA)\nHà (Dev)')
  const [upMsg, setUpMsg] = useState(null)

  // Gọi GET /api/v1/review
  async function load(target) {
    setBusy(true)
    setError(null)
    setExportFiles(null)
    setExportError(null)
    try {
      const data = await getReview(target)
      setState(data)
      setMeetingId(target)
    } catch (e) {
      setError(`GET /api/v1/review → ${e.status ?? '?'}: ${JSON.stringify(e.body)}`)
      setState(null)
    } finally {
      setBusy(false)
    }
  }

  // Auto-load ban đầu
  useEffect(() => {
    load('tc2')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Đếm badge từ items hiện tại
  const counts = useMemo(() => {
    const c = { red: 0, yellow: 0, green: 0 }
    ;(state?.items ?? []).forEach((it) => {
      const conf = Number(it.confidence ?? 0)
      if (conf < 0.5) c.red++
      else if (conf < 0.75) c.yellow++
      else c.green++
    })
    return c
  }, [state])

  const redCount = counts.red
  const gateOpen = redCount === 0

  // Chia items theo cột + theo filter
  const partitioned = useMemo(() => {
    const pass = (conf) => {
      if (filter === 'all') return true
      const c = Number(conf ?? 0)
      if (filter === 'red') return c < 0.5
      if (filter === 'yellow') return c >= 0.5 && c < 0.75
      if (filter === 'green') return c >= 0.75
      return true
    }
    const items = (state?.items ?? []).filter((it) => pass(it.confidence))
    // Trong cột Quyết định, chỉ hiển thị final; discarded gộp lại để render thu gọn.
    const finalDecisions = items.filter(
      (it) => it.type === 'decision' && it.status === 'final',
    )
    const discardedByFinal = finalDecisions.reduce((acc, fd) => {
      const ids = fd.supersedes || []
      const matched = items.filter(
        (it) => it.type === 'decision' && ids.includes(it.id),
      )
      acc[fd.id] = matched
      return acc
    }, {})
    return {
      finalDecisions,
      discardedByFinal,
      tasks: items.filter((it) => it.type === 'task'),
      blockers: items.filter((it) => it.type === 'blocker'),
      openIssues: items.filter((it) => it.type === 'open_issue'),
      requirements: items.filter((it) => it.type === 'requirement'),
      knowledge: items.filter((it) => it.type === 'knowledge'),
    }
  }, [state, filter])

  // ── Mutations: agree / edit / remove ────────────────────────────────
  function applyChange(changes) {
    if (!state) return
    setBusy(true)
    putReview(meetingId, state.items, changes)
      .then((resp) => {
        // Re-load để có state.json mới + confirmed_stamp.json được ghi
        return load(meetingId).then(() => resp)
      })
      .then((resp) => {
        // Thông báo nhẹ
        console.log('PUT ok:', resp)
      })
      .catch((e) => {
        setError(`PUT /api/v1/review → ${e.status ?? '?'}: ${JSON.stringify(e.body)}`)
      })
      .finally(() => setBusy(false))
  }

  function onAgree(item) {
    applyChange([
      { item_id: item.id, action: 'agree', old: null, new: null },
    ])
  }

  function onEdit(item, draft) {
    const old = {}
    const nw = {}
    if ((item.content ?? '') !== draft.content) {
      old.content = item.content
      nw.content = draft.content
    }
    if (item.type === 'task') {
      if ((item.owner ?? '') !== draft.owner) {
        old.owner = item.owner
        nw.owner = draft.owner
      }
      if ((item.due ?? '') !== draft.due) {
        old.due = item.due
        nw.due = draft.due
      }
    }
    if ((item.link_to_decision ?? '') !== draft.link_to_decision) {
      old.link_to_decision = item.link_to_decision
      nw.link_to_decision = draft.link_to_decision
    }
    const change = { item_id: item.id, action: 'edit', old, new: nw }
    if (Object.keys(nw).length === 0) return // nothing changed
    applyChange([change])
  }

  function onRemove(item) {
    applyChange([
      { item_id: item.id, action: 'remove', old: null, new: null },
    ])
  }

  // ── Transcript drawer: bấm evidence → hiện ±4 turns quanh turn đó ──
  async function showEvidence(ev) {
    if (!ev) return
    setBusy(true)
    try {
      let entry = transcriptCache[meetingId]
      if (!entry) {
        const data = await getTranscript(meetingId)
        entry = { turns: data.turns || [], source: data.source || '' }
        setTranscriptCache((c) => ({ ...c, [meetingId]: entry }))
      }
      setTranscript({ meeting: meetingId, ...entry, targetTurn: ev.turn ?? null })
    } catch (e) {
      setError(`GET /api/v1/transcript → ${e.status ?? '?'}: ${JSON.stringify(e.body)}`)
    } finally {
      setBusy(false)
    }
  }

  function parseParticipants(text) {
    // Mỗi dòng: "Tên (role)" — aliases tự = [tên].
    return (text || '')
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const m = l.match(/^(.*?)\s*\((.*?)\)\s*$/)
        const name = (m ? m[1] : l).trim()
        const role = (m ? m[2] : 'member').trim() || 'member'
        return { name, role, aliases: [name] }
      })
      .filter((p) => p.name)
  }

  // ── Upload transcript + chạy pipeline ngay ──────────────────────────
  async function doUpload() {
    setUpMsg(null)
    setError(null)
    if (!upFile) {
      setUpMsg('Chưa chọn file (.txt/.srt).')
      return
    }
    setBusy(true)
    try {
      const resp = await uploadMeeting({
        file: upFile,
        meetingId: upId.trim(),
        title: upTitle.trim() || upFile.name,
        date: upDate,
        participants: JSON.stringify(parseParticipants(upParts)),
      })
      setState(resp.state)
      setMeetingId(resp.meeting_id)
      setMeetingInput(resp.meeting_id)
      setTranscriptCache((c) => ({ ...c, [resp.meeting_id]: null }))
      setUpMsg(`✅ Xong: ${resp.turns_count} turns → ${resp.state.items?.length ?? 0} items. Review bên dưới.`)
    } catch (e) {
      if (e.status === 503) {
        setUpMsg(`⏳ LLM chưa sẵn sàng (503): bật Ollama rồi thử lại. Chi tiết: ${JSON.stringify(e.body)}`)
      } else {
        setUpMsg(`❌ Upload lỗi (${e.status ?? '?'}): ${JSON.stringify(e.body)}`)
      }
    } finally {
      setBusy(false)
    }
  }

  // ── Export ──────────────────────────────────────────────────────────
  function doExport() {
    setBusy(true)
    setExportError(null)
    setExportFiles(null)
    postExport(meetingId)
      .then((resp) => {
        setExportFiles(resp.files || [])
      })
      .catch((e) => {
        if (e.status === 403) {
          const reds = e.body?.red_items ?? []
          setExportError(
            `403 gate_red_items — còn thẻ đỏ: ${reds.join(', ')}. Xử lý hết trước khi export.`,
          )
        } else if (e.status === 400) {
          setExportError(`400 not_confirmed — ${e.body?.detail ?? ''}`)
        } else {
          setExportError(`${e.status ?? '?'}: ${JSON.stringify(e.body)}`)
        }
      })
      .finally(() => setBusy(false))
  }

  return (
    <div className="app">
      {/* ─── Sidebar ──────────────────────────────────────────────── */}
      <aside className="sidebar">
        <h1>meet2note</h1>
        <p className="subtitle">Review · P3</p>

        <div className="meeting-input">
          <label>
            Meeting id:
            <input
              value={meetingInput}
              onChange={(e) => setMeetingInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && load(meetingInput)}
              data-testid="meeting-input"
            />
          </label>
          <button onClick={() => load(meetingInput)} disabled={busy}>
            Load
          </button>
        </div>

        <div className="filter">
          <span>Confidence filter:</span>
          {['all', 'red', 'yellow', 'green'].map((f) => (
            <label key={f}>
              <input
                type="radio"
                name="filter"
                value={f}
                checked={filter === f}
                onChange={() => setFilter(f)}
              />
              {f}
            </label>
          ))}
        </div>

        <div className="export-block">
          <div className="counts">
            <span className="badge badge-red">🔴 {counts.red}</span>{' '}
            <span className="badge badge-yellow">🟡 {counts.yellow}</span>{' '}
            <span className="badge badge-green">🟢 {counts.green}</span>
          </div>
          <button
            className="export-btn"
            disabled={!gateOpen || busy}
            onClick={doExport}
            data-testid="export-btn"
          >
            {gateOpen ? 'Export' : `Khoá (${redCount} đỏ)`}
          </button>
          {exportFiles && exportFiles.length > 0 && (
            <div className="export-result">
              <p>✅ Export xong:</p>
              <ul>
                {exportFiles.map((f) => (
                  <li key={f}>
                    <code>{f}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {exportError && <p className="err">{exportError}</p>}
        </div>

        <div className="upload-block">
          <h3>⬆ Upload transcript</h3>
          <label>
            File .txt/.srt:
            <input
              type="file"
              accept=".txt,.srt"
              onChange={(e) => setUpFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label>
            Meeting id (trống = từ tên file):
            <input value={upId} onChange={(e) => setUpId(e.target.value)} />
          </label>
          <label>
            Title:
            <input value={upTitle} onChange={(e) => setUpTitle(e.target.value)} />
          </label>
          <label>
            Date:
            <input
              type="date"
              value={upDate}
              onChange={(e) => setUpDate(e.target.value)}
            />
          </label>
          <label>
            Participants (mỗi dòng: Tên (role)):
            <textarea
              rows={3}
              value={upParts}
              onChange={(e) => setUpParts(e.target.value)}
            />
          </label>
          <button onClick={doUpload} disabled={busy}>
            {busy ? 'Đang chạy pipeline…' : 'Upload + chạy'}
          </button>
          {upMsg && <p className="upmsg">{upMsg}</p>}
        </div>

        {error && <p className="err">{error}</p>}
      </aside>

      {/* ─── Main ─────────────────────────────────────────────────── */}
      <main className="main">
        {!state && <p>Chưa load meeting.</p>}
        {state && (
          <>
            <header className="meeting-header">
              <h2>
                {state.meeting?.title} — {state.meeting?.date}
              </h2>
              <p>
                meeting id: <code>{state.meeting?.id}</code> · pipeline{' '}
                <code>{state.meeting?.pipeline_version}</code>
              </p>
              {state.no_decision && (
                <p className="warn">⚠ no_decision=true</p>
              )}
            </header>

            {state.brief && (
              <div className="brief">
                <p>
                  <strong>Vấn đề:</strong> {state.brief.problem}
                </p>
                {(state.brief.outcomes ?? []).length > 0 && (
                  <ul>
                    {(state.brief.outcomes ?? []).map((o, i) => (
                      <li key={i}>
                        {o.text}{' '}
                        <code>→ {(o.ref_ids ?? []).join(', ')}</code>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="columns">
              {/* Quyết định */}
              <section className="col">
                <h3>✅ Quyết định ({partitioned.finalDecisions.length})</h3>
                {partitioned.finalDecisions.map((d) => (
                  <div key={d.id}>
                    <ItemCard
                      item={d}
                      onAgree={onAgree}
                      onEdit={onEdit}
                      onRemove={onRemove} onShowEvidence={showEvidence}
                    />
                    <DiscardedList
                      items={partitioned.discardedByFinal[d.id] ?? []}
                    />
                  </div>
                ))}
              </section>

              {/* Công việc */}
              <section className="col">
                <h3>📌 Công việc ({partitioned.tasks.length})</h3>
                {partitioned.tasks.map((t) => (
                  <ItemCard
                    key={t.id}
                    item={t}
                    onAgree={onAgree}
                    onEdit={onEdit}
                    onRemove={onRemove} onShowEvidence={showEvidence}
                  />
                ))}
              </section>

              {/* Vướng mắc & Chưa chốt */}
              <section className="col">
                <h3>
                  ⚠️ Vướng mắc &amp; Chưa chốt ({partitioned.blockers.length +
                    partitioned.openIssues.length})
                </h3>
                {partitioned.blockers.map((b) => (
                  <ItemCard
                    key={b.id}
                    item={b}
                    onAgree={onAgree}
                    onEdit={onEdit}
                    onRemove={onRemove} onShowEvidence={showEvidence}
                  />
                ))}
                {partitioned.openIssues.map((o) => (
                  <ItemCard
                    key={o.id}
                    item={o}
                    onAgree={onAgree}
                    onEdit={onEdit}
                    onRemove={onRemove} onShowEvidence={showEvidence}
                  />
                ))}
              </section>

              {/* Yêu cầu & Phản hồi */}
              <section className="col">
                <h3>
                  📋 Yêu cầu &amp; Phản hồi ({partitioned.requirements.length +
                    partitioned.knowledge.length})
                </h3>
                {partitioned.requirements.map((r) => (
                  <ItemCard
                    key={r.id}
                    item={r}
                    onAgree={onAgree}
                    onEdit={onEdit}
                    onRemove={onRemove} onShowEvidence={showEvidence}
                  />
                ))}
                {partitioned.knowledge.map((k) => (
                  <ItemCard
                    key={k.id}
                    item={k}
                    onAgree={onAgree}
                    onEdit={onEdit}
                    onRemove={onRemove} onShowEvidence={showEvidence}
                  />
                ))}
              </section>
            </div>

            {Array.isArray(state.known_limitations) &&
              state.known_limitations.length > 0 && (
                <div className="limitations">
                  <h3>⚠ known_limitations</h3>
                  <ul>
                    {state.known_limitations.map((lim, i) => (
                      <li key={i}>{lim}</li>
                    ))}
                  </ul>
                </div>
              )}
          </>
        )}

        {transcript && (
          <div className="drawer">
            <div className="drawer-head">
              <strong>
                📜 Transcript {transcript.meeting} ({transcript.source})
              </strong>
              <button onClick={() => setTranscript(null)}>Đóng ✕</button>
            </div>
            <div className="drawer-body">
              {transcript.turns
                .filter(
                  (t) =>
                    transcript.targetTurn == null ||
                    Math.abs((t.turn ?? 0) - transcript.targetTurn) <= 4,
                )
                .map((t) => (
                  <p
                    key={t.turn}
                    className={
                      t.turn === transcript.targetTurn ? 'turn-hl' : ''
                    }
                  >
                    <code>
                      [{t.t_start}] {t.speaker}:
                    </code>{' '}
                    {t.text}
                  </p>
                ))}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}