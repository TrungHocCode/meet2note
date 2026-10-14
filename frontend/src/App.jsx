/**
 * src/App.jsx — meet2note Review.
 *
 * Spec UI (nguồn chân lý — KHÔNG mô tả lại UI ở đây):
 * - docs/design/layout.md      bố cục + breakpoint
 * - docs/design/components.md  component + trạng thái + map R1-R8
 * - docs/design/tokens.md      token (Tailwind v4 @theme)
 * - docs/spec/ui-spec.md       hợp đồng hành vi + acceptance checklist
 *
 * Bất biến không được vỡ khi sửa file này:
 * - data-testid="meeting-input" / "export-btn" (cam kết ở ui-spec §9)
 * - export-btn DISABLED khi còn item confidence < 0.50 chưa xử lý (gate R6)
 * - PUT /review luôn gửi kèm `changes` (audit, ADR-0004)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Download,
  Link2,
  Pencil,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import {
  getReview,
  putReview,
  postExport,
  getTranscript,
  uploadMeeting,
} from './api.js'
import { Alert, AlertDescription, AlertTitle } from './components/ui/alert.jsx'
import { Badge } from './components/ui/badge.jsx'
import { Button } from './components/ui/button.jsx'
import { Card } from './components/ui/card.jsx'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from './components/ui/collapsible.jsx'
import { Input } from './components/ui/input.jsx'
import { Label } from './components/ui/label.jsx'
import { Progress } from './components/ui/progress.jsx'
import { Separator } from './components/ui/separator.jsx'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from './components/ui/sheet.jsx'
import { Skeleton } from './components/ui/skeleton.jsx'
import { Textarea } from './components/ui/textarea.jsx'
import { ToggleGroup, ToggleGroupItem } from './components/ui/toggle-group.jsx'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from './components/ui/tooltip.jsx'
import { Toaster, toast } from './components/ui/sonner.jsx'

// ─── Helpers thuần ─────────────────────────────────────────────────────────

function levelOf(conf) {
  const c = Number(conf ?? 0)
  if (c < 0.5) return 'red'
  if (c < 0.75) return 'yellow'
  return 'green'
}

const LEVEL_VN = { red: 'đỏ', yellow: 'vàng', green: 'xanh' }
const CONF_VARIANT = { red: 'conf-red', yellow: 'conf-amber', green: 'conf-green' }

const TYPE_LABEL = {
  decision: 'Quyết định',
  task: 'Công việc',
  blocker: 'Vướng mắc',
  open_issue: 'Chưa chốt',
  requirement: 'Yêu cầu',
  knowledge: 'Kiến thức',
}

function isInteractiveTarget(e) {
  const t = e.target
  if (!t || !t.closest) return false
  return Boolean(t.closest('input, textarea, select, [contenteditable="true"]'))
}

// ─── Evidence: hiện sẵn 2 dòng + "+N" ───────────────────────────────────────

function EvidenceLines({ evidence, onShow }) {
  const [expanded, setExpanded] = useState(false)
  if (!Array.isArray(evidence) || evidence.length === 0) return null
  const shown = expanded ? evidence : evidence.slice(0, 2)
  return (
    <div className="flex flex-col gap-1">
      {shown.map((ev, i) => (
        <div
          key={i}
          className="rounded-md border-l-2 bg-evidence-bg px-2 py-1 text-xs leading-relaxed"
          style={{ borderLeftColor: 'var(--color-evidence-rule)' }}
        >
          <button
            type="button"
            onClick={() => onShow(ev)}
            title="Mở transcript tại lượt này"
            className="min-h-6 min-w-6 font-mono text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            [{ev.timestamp}]
          </button>{' '}
          <span className="font-semibold">{ev.speaker}</span>{' '}
          <span className="text-xs text-muted-foreground">({ev.role_in_discussion})</span>:{' '}
          <q className="italic break-words">“{ev.quote}”</q>
        </div>
      ))}
      {evidence.length > 2 && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="self-start text-xs text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
        >
          {expanded ? 'Thu gọn' : `+${evidence.length - 2} evidence`}
        </button>
      )}
    </div>
  )
}

// ─── Meta pills theo loại item (ui-spec §3.2 + §4) ──────────────────────────
// Quy ước thống nhất: mọi pill đều dạng `nhãn: giá trị`, cùng cỡ/shape;
// mỗi loại item HIỆN ĐỦ bộ field của nó (thiếu → "—" mờ, không im lặng bỏ qua
// — trừ link/hint chỉ có khi tồn tại). Severity/origin Việt hóa + tooltip.

const SEVERITY_VN = { low: 'Thấp', medium: 'Trung bình', high: 'Cao' }
const ORIGIN_VN = { customer: 'Khách hàng', internal: 'Nội bộ', partner: 'Đối tác', unknown: 'Chưa rõ' }

function Meta({ label, children, tone = 'secondary', hint }) {
  const pill = (
    <Badge variant={tone}>
      <span className="font-normal text-muted-foreground">{label}:</span> {children}
    </Badge>
  )
  if (!hint) return pill
  return (
    <Tooltip>
      <TooltipTrigger asChild>{pill}</TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  )
}

function MetaPills({ item, allIds }) {
  const pills = []
  const missing = <span className="text-muted-foreground">—</span>
  if (item.type === 'task') {
    pills.push(
      <Meta key="owner" label="Người làm" tone={item.owner === 'TBD' ? 'conf-amber' : 'secondary'}>
        {item.owner === 'TBD' ? 'TBD' : item.owner}
      </Meta>,
    )
    pills.push(
      <Meta
        key="due"
        label="Hạn"
        tone={item.due === 'TBD' ? 'conf-amber' : 'secondary'}
        hint={item.due_hint ? `Chữ gốc trong họp: “${item.due_hint}”` : undefined}
      >
        {item.due === 'TBD' ? 'TBD' : item.due}
        {item.due_source === 'inferred' ? ' · suy luận' : ''}
      </Meta>,
    )
    if (item.link_to_decision) {
      const ok = allIds.has(item.link_to_decision)
      pills.push(
        <Meta key="link" label="Theo QĐ" tone={ok ? 'secondary' : 'destructive'}>
          <Link2 className="size-3" /> {item.link_to_decision}
          {!ok ? ' (không tồn tại)' : ''}
        </Meta>,
      )
    }
  }
  if (item.type === 'decision') {
    pills.push(
      <Meta key="by" label="Người chốt">{item.decided_by || missing}</Meta>,
    )
    pills.push(
      <Meta key="sup" label="Thay thế">
        {(item.supersedes ?? []).length > 0 ? item.supersedes.join(', ') : 'quyết định gốc'}
      </Meta>,
    )
  }
  if (item.type === 'blocker') {
    pills.push(
      <Meta
        key="need" label="Người gỡ"
        tone={item.needs_action_from === 'TBD' ? 'conf-amber' : 'secondary'}
      >
        {item.needs_action_from || 'TBD'}
      </Meta>,
    )
    pills.push(
      <Meta
        key="sev" label="Mức nặng"
        hint="Mức nghiêm trọng của vướng mắc: Thấp (chờ được) / Trung bình (chậm tiến độ) / Cao (chặn cả team)"
      >
        {SEVERITY_VN[item.severity] ?? item.severity ?? missing}
      </Meta>,
    )
  }
  if (item.type === 'open_issue') {
    pills.push(
      <Meta key="nso" label="Người tiếp">
        {item.next_step_owner || missing}
      </Meta>,
    )
    if (item.system_generated) pills.push(<Badge key="sys" variant="conf-amber">hệ thống tạo</Badge>)
  }
  if (item.type === 'requirement') {
    pills.push(
      <Meta
        key="origin" label="Nguồn"
        hint="Ai đặt yêu cầu: Khách hàng / Nội bộ / Đối tác / Chưa rõ"
      >
        {ORIGIN_VN[item.origin] ?? item.origin ?? missing}
      </Meta>,
    )
    pills.push(
      <Meta key="rb" label="Người nêu">{item.raised_by || missing}</Meta>,
    )
  }
  if (item.type === 'knowledge') {
    ;(item.tags ?? []).forEach((t) => {
      pills.push(<Badge key={`tag-${t}`} variant="outline">{t}</Badge>)
    })
    if (item.context) pills.push(<Badge key="ctx" variant="outline">{item.context}</Badge>)
  }
  if (pills.length === 0) return null
  return <div className="flex flex-wrap gap-1">{pills}</div>
}

// ─── Cảnh báo semantic trên card (ui-spec §4) ───────────────────────────────

function SemanticAlerts({ item }) {
  const [objectionsOpen, setObjectionsOpen] = useState(false)
  return (
    <>
      {item.unresolved_reversal === true && (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Đảo quyết định (A→B→A) — cần host chốt</AlertTitle>
        </Alert>
      )}
      {Array.isArray(item.objections) && item.objections.length > 0 && (
        <Collapsible open={objectionsOpen} onOpenChange={setObjectionsOpen}>
          <div className="rounded-lg border border-conf-amber/40 bg-conf-amber-bg px-3 py-2 text-xs text-conf-amber">
            <CollapsibleTrigger className="flex w-full items-center gap-1 font-semibold">
              <ChevronDown className="size-3" />⛔ Objection ({item.objections.length})
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-1 flex flex-col gap-1">
                {item.objections.map((o, i) => (
                  <li key={i}>
                    [{o.timestamp}] <strong>{o.speaker}</strong>: “{o.quote}”
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </div>
        </Collapsible>
      )}
    </>
  )
}

// ─── Card item ───────────────────────────────────────────────────────────────

function ItemCard({
  item, allIds, focused, confirmed, cardRef,
  onAgree, onEdit, onRemove, onShowEvidence,
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => ({
    content: item.content ?? item.what ?? '',
    owner: item.owner ?? '',
    due: item.due ?? '',
    link_to_decision: item.link_to_decision ?? '',
  }))
  const level = levelOf(item.confidence)
  const red = level === 'red'
  const yellow = level === 'yellow'
  const contentText = item.type === 'task' ? item.what || '' : item.content || ''
  const showActions = editing || focused || red

  return (
    <Card
      ref={cardRef}
      tabIndex={0}
      data-testid={`card-${item.id}`}
      aria-label={`${TYPE_LABEL[item.type] ?? item.type} ${item.id}, confidence ${item.confidence}, mức ${LEVEL_VN[level]}`}
      className={[
        'break-words p-3 transition-shadow duration-150 ease-out hover:shadow-card hover:-translate-y-px',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
        focused ? 'outline-2 outline-offset-2 outline-ring' : '',
        red ? 'border-conf-red/40 border-l-4 bg-conf-red-bg/40' : '',
        yellow ? 'border-conf-amber/40 border-l-4 bg-conf-amber-bg/30' : '',
        !red && !yellow ? 'border-conf-green/30 border-l-4 bg-conf-green-bg/30' : '',
        confirmed ? 'opacity-60' : '',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-center gap-2">
        <code className="font-mono text-xs text-muted-foreground">{item.id}</code>
        <Badge variant="secondary">{TYPE_LABEL[item.type] ?? item.type}</Badge>
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Badge
                variant={CONF_VARIANT[level]}
                aria-label={`confidence ${item.confidence}, mức ${LEVEL_VN[level]}`}
              >
                {LEVEL_VN[level]} {Number(item.confidence ?? 0).toFixed(2)}
              </Badge>
            </span>
          </TooltipTrigger>
          <TooltipContent>{item.confidence_reason || 'không có lý do'}</TooltipContent>
        </Tooltip>
        {red && !confirmed && <Badge variant="destructive">cần xử lý</Badge>}
        {confirmed && <Badge variant="conf-green">✓ đã xác nhận</Badge>}
      </div>

      <p className="mt-2 text-sm font-medium leading-relaxed break-words">{contentText}</p>

      <div className="mt-2">
        <SemanticAlerts item={item} />
      </div>

      <div className="mt-2">
        <MetaPills item={item} allIds={allIds} />
      </div>

      {/* Câu dài (lý do / next_step) render dạng text wrap, KHÔNG pill
          (pill có whitespace-nowrap nên tràn khung — lỗi đã gặp). */}
      {item.type === 'decision' && item.reason && (
        <p className="mt-1 text-xs text-muted-foreground break-words">
          Lý do: {item.reason}
        </p>
      )}
      {item.type === 'open_issue' && item.next_step && (
        <p className="mt-1 text-xs text-muted-foreground break-words">
          Next: {item.next_step}
        </p>
      )}

      <div className="mt-2" data-testid={`card-${item.id}-evidence`}>
        <EvidenceLines evidence={item.evidence} onShow={onShowEvidence} />
      </div>

      {editing ? (
        <div className="mt-2 flex flex-col gap-2">
          <Label htmlFor={`edit-content-${item.id}`}>Nội dung</Label>
          <Textarea
            id={`edit-content-${item.id}`}
            value={draft.content}
            onChange={(e) => setDraft({ ...draft, content: e.target.value })}
          />
          {item.type === 'task' && (
            <>
              <Label htmlFor={`edit-owner-${item.id}`}>Owner</Label>
              <Input
                id={`edit-owner-${item.id}`}
                value={draft.owner}
                onChange={(e) => setDraft({ ...draft, owner: e.target.value })}
              />
              <Label htmlFor={`edit-due-${item.id}`}>Due (YYYY-MM-DD hoặc TBD)</Label>
              <Input
                id={`edit-due-${item.id}`}
                value={draft.due}
                onChange={(e) => setDraft({ ...draft, due: e.target.value })}
              />
            </>
          )}
          <Label htmlFor={`edit-link-${item.id}`}>link_to_decision</Label>
          <Input
            id={`edit-link-${item.id}`}
            value={draft.link_to_decision}
            onChange={(e) => setDraft({ ...draft, link_to_decision: e.target.value })}
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => {
                onEdit(item, draft)
                setEditing(false)
              }}
            >
              <Check className="size-4" /> Lưu
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
              <X className="size-4" /> Huỷ (Esc)
            </Button>
          </div>
        </div>
      ) : (
        showActions && (
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => onAgree(item)}
              data-testid={`card-${item.id}-agree`}
              className="flex-1"
            >
              <Check className="size-4" /> Đồng ý
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditing(true)}
              data-testid={`card-${item.id}-edit`}
              className="flex-1"
            >
              <Pencil className="size-4" /> Sửa
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => onRemove(item)}
              className="flex-1"
            >
              <Trash2 className="size-4" /> Loại
            </Button>
          </div>
        )
      )}
    </Card>
  )
}

// ─── Lịch sử supersedes thu gọn ──────────────────────────────────────────────

function DiscardedList({ items }) {
  if (!items.length) return null
  return (
    <Collapsible className="mb-2 ml-3">
      <CollapsibleTrigger className="text-xs text-muted-foreground underline-offset-2 hover:underline">
        Lịch sử: thay thế {items.map((i) => i.id).join(', ')}
      </CollapsibleTrigger>
      <CollapsibleContent>
        {items.map((it) => (
          <div key={it.id} className="mt-1 rounded-lg border bg-card p-2 text-xs text-muted-foreground">
            <code className="font-mono">{it.id}</code> · {it.content}
            {Array.isArray(it.objections) && it.objections.length > 0 && (
              <ul className="mt-1 flex flex-col gap-1">
                {it.objections.map((o, i) => (
                  <li key={i}>
                    [{o.timestamp}] <strong>{o.speaker}</strong>: “{o.quote}”
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  )
}

// ─── Cột ─────────────────────────────────────────────────────────────────────

function Column({ title, items, render, emptyHint }) {
  return (
    <section className="flex min-w-0 flex-col gap-3">
      <h3 className="font-heading text-sm font-semibold">
        {title}{' '}
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {items.length}
        </span>
      </h3>
      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
          Không có mục nào{emptyHint ? ` — ${emptyHint}` : ''}
        </div>
      ) : (
        items.map(render)
      )}
    </section>
  )
}

// ─── Drawer transcript (Sheet) ─────────────────────────────────────────────

function TranscriptSheet({ view, drawerError, onClose }) {
  const targetRef = useRef(null)
  useEffect(() => {
    if (view && targetRef.current) {
      targetRef.current.scrollIntoView({ block: 'center' })
    }
  }, [view])
  return (
    <Sheet
      open={view !== null}
      onOpenChange={(o) => {
        if (!o) onClose()
      }}
    >
      <SheetContent showClose={false}>
        <div className="flex items-center justify-between gap-2">
          <div>
            <SheetTitle>Transcript · turn {view?.targetTurn ?? '?'}</SheetTitle>
            <SheetDescription>
              {view?.source} · ±4 lượt quanh câu trích
            </SheetDescription>
          </div>
          <Button size="sm" variant="outline" onClick={onClose}>
            Đóng (Esc)
          </Button>
        </div>
        {drawerError && (
          <Alert variant="destructive">
            <AlertDescription>{drawerError}</AlertDescription>
          </Alert>
        )}
        <div className="flex-1 overflow-y-auto rounded-lg border p-3 text-xs leading-relaxed">
          {(view?.turns ?? [])
            .filter(
              (t) =>
                view?.targetTurn == null ||
                Math.abs((t.turn ?? 0) - view.targetTurn) <= 4,
            )
            .map((t) => {
              const isTarget = t.turn === view?.targetTurn
              const body = (() => {
                const q = view?.quote
                if (!isTarget || !q || !t.text.includes(q)) return t.text
                const [head, ...rest] = t.text.split(q)
                return (
                  <>
                    {head}
                    <mark className="bg-hl-bg outline outline-hl-border">{q}</mark>
                    {rest.join(q)}
                  </>
                )
              })()
              return (
                <p
                  key={t.turn}
                  ref={isTarget ? targetRef : undefined}
                  className={isTarget ? 'rounded bg-hl-bg p-1 outline outline-hl-border' : 'p-1'}
                >
                  <code className="font-mono text-muted-foreground">
                    [{t.t_start}] {t.speaker}:
                  </code>{' '}
                  {body}
                </p>
              )
            })}
        </div>
      </SheetContent>
    </Sheet>
  )
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [meetingId, setMeetingId] = useState('tc2')
  const [meetingInput, setMeetingInput] = useState('tc2')
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('all')
  const [exportFiles, setExportFiles] = useState(null)
  const [exportError, setExportError] = useState(null)
  const [loadError, setLoadError] = useState(null)
  // Overlay phiên review: confirmed + removed + sửa local.
  const [confirmedIds, setConfirmedIds] = useState(() => new Set())
  const [removedIds, setRemovedIds] = useState(() => new Set())
  const [editedItems, setEditedItems] = useState({})
  // Transcript drawer + cache.
  const [transcriptCache, setTranscriptCache] = useState({})
  const [drawer, setDrawer] = useState(null)
  const [drawerError, setDrawerError] = useState(null)
  const openerRef = useRef(null)
  // Upload form.
  const [upFile, setUpFile] = useState(null)
  const [upId, setUpId] = useState('')
  const [upTitle, setUpTitle] = useState('')
  const [upDate, setUpDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [upParts, setUpParts] = useState('Lan (PM)\nNam (BA)\nHà (Dev)')
  const [upMsg, setUpMsg] = useState(null)
  const [upBusy, setUpBusy] = useState(false)
  // Keyboard focus.
  const [focusedId, setFocusedId] = useState(null)
  const cardRefs = useRef({})
  const onAgreeRef = useRef(null)
  const onRemoveRef = useRef(null)
  const showEvidenceRef = useRef(null)

  const allIds = useMemo(() => new Set((state?.items ?? []).map((i) => i.id)), [state])

  const visibleItems = useMemo(() => {
    return (state?.items ?? [])
      .filter((it) => !removedIds.has(it.id))
      .map((it) => (editedItems[it.id] ? { ...it, ...editedItems[it.id] } : it))
  }, [state, removedIds, editedItems])

  async function load(target, opts = {}) {
    const { keepOverlay = false } = opts
    setBusy(true)
    setLoadError(null)
    setExportFiles(null)
    setExportError(null)
    if (!keepOverlay) {
      // Chỉ reset overlay khi đổi meeting / upload mới. Reload sau PUT phải
      // GIỮ overlay (confirmed/removed/edited) — xóa là mất pill "đã xác nhận",
      // card nháy về như cũ (bug: bấm Đồng ý chỉ thấy nhấp nháy).
      setConfirmedIds(new Set())
      setRemovedIds(new Set())
      setEditedItems({})
      setFocusedId(null)
      setDrawer(null)
    }
    try {
      const data = await getReview(target)
      setState(data)
      setMeetingId(target)
    } catch (e) {
      setLoadError(
        e.status === 404
          ? `Chưa chạy cli run cho meeting này (404). Chạy: python -m pipeline.cli run --meeting ${target}`
          : `GET /api/v1/review → ${e.status ?? '?'}: ${JSON.stringify(e.body)}`,
      )
      setState(null)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    load('tc2')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function sendPut(itemsToSend, changes) {
    setBusy(true)
    try {
      const resp = await putReview(meetingId, itemsToSend, changes)
      await load(meetingId, { keepOverlay: true })
      return resp
    } finally {
      setBusy(false)
    }
  }

  function currentItemsForPut() {
    return (state?.items ?? [])
      .filter((it) => !removedIds.has(it.id))
      .map((it) => (editedItems[it.id] ? { ...it, ...editedItems[it.id] } : it))
  }

  function onAgree(item) {
    const changes = [{ item_id: item.id, action: 'agree', old: null, new: null }]
    setConfirmedIds((s) => new Set(s).add(item.id))
    sendPut(currentItemsForPut(), changes).catch(() => {
      setConfirmedIds((s) => {
        const n = new Set(s)
        n.delete(item.id)
        return n
      })
    })
  }

  function onEdit(item, draft) {
    const old = {}
    const nw = {}
    if (item.type === 'task') {
      if ((item.what ?? '') !== draft.content) nw.what = draft.content
    } else if ((item.content ?? '') !== draft.content) {
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
    if (Object.keys(nw).length === 0) return
    setEditedItems((m) => ({ ...m, [item.id]: nw }))
    setConfirmedIds((s) => new Set(s).add(item.id))
    sendPut(
      currentItemsForPut().map((it) => (it.id === item.id ? { ...it, ...nw } : it)),
      [{ item_id: item.id, action: 'edit', old, new: nw }],
    ).catch(() => {
      setEditedItems((m) => {
        const n = { ...m }
        delete n[item.id]
        return n
      })
    })
  }

  function onRemove(item) {
    setRemovedIds((s) => new Set(s).add(item.id))
    sendPut(
      currentItemsForPut().filter((it) => it.id !== item.id),
      [{ item_id: item.id, action: 'remove', old: null, new: null }],
    ).catch(() => {
      setRemovedIds((s) => {
        const n = new Set(s)
        n.delete(item.id)
        return n
      })
    })
    toast(`Đã loại ${item.id}`, {
      description: 'Item vẫn nằm trong runs/ (audit).',
      duration: 8000,
      action: {
        label: 'Hoàn tác',
        onClick: () => {
          setRemovedIds((s) => {
            const n = new Set(s)
            n.delete(item.id)
            return n
          })
          sendPut(currentItemsForPut(), [
            { item_id: item.id, action: 'agree', old: null, new: { restored: true } },
          ]).catch(() => {})
        },
      },
    })
  }

  onAgreeRef.current = onAgree
  onRemoveRef.current = onRemove

  const redItems = useMemo(
    () => visibleItems.filter((it) => levelOf(it.confidence) === 'red' && !confirmedIds.has(it.id)),
    [visibleItems, confirmedIds],
  )
  const gateOpen = redItems.length === 0 && visibleItems.length > 0

  function doExport() {
    setExportError(null)
    setExportFiles(null)
    postExport(meetingId)
      .then((resp) => setExportFiles(resp.files || []))
      .catch((e) => {
        if (e.status === 403) {
          const reds = e.body?.red_items ?? []
          setExportError(`Còn thẻ đỏ chưa xử lý: ${reds.join(', ')}. Xử lý hết trước khi export.`)
        } else if (e.status === 400) {
          setExportError(`Chưa confirm: ${e.body?.detail ?? ''}`)
        } else {
          setExportError(`${e.status ?? '?'}: ${JSON.stringify(e.body)}`)
        }
      })
  }

  async function showEvidence(ev) {
    if (!ev) return
    openerRef.current = document.activeElement
    try {
      let entry = transcriptCache[meetingId]
      if (!entry) {
        const data = await getTranscript(meetingId)
        entry = { turns: data.turns || [], source: data.source || '' }
        setTranscriptCache((c) => ({ ...c, [meetingId]: entry }))
      }
      const found = entry.turns.some((t) => t.turn === ev.turn)
      setDrawerError(found ? null : `Không tìm thấy turn ${ev.turn} trong transcript.`)
      setDrawer({
        turns: entry.turns,
        source: entry.source,
        targetTurn: found ? ev.turn : null,
        quote: ev.quote,
      })
    } catch (e) {
      setDrawerError(
        e.status === 404
          ? 'Không tìm thấy transcript cho meeting này.'
          : `Lỗi tải transcript: ${e.status ?? '?'}`
      )
      setDrawer({ turns: [], source: '', targetTurn: null, quote: ev?.quote })
    }
  }

  showEvidenceRef.current = showEvidence

  function closeDrawer() {
    setDrawer(null)
    setDrawerError(null)
    if (openerRef.current && openerRef.current.focus) openerRef.current.focus()
  }

  function parseParticipants(text) {
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

  async function doUpload() {
    setUpMsg(null)
    if (!upFile) {
      setUpMsg('Chưa chọn file (.txt/.srt/.docx).')
      return
    }
    setUpBusy(true)
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
      setConfirmedIds(new Set())
      setRemovedIds(new Set())
      setEditedItems({})
      setDrawer(null)
      setUpMsg(`Xong: ${resp.turns_count} turns → ${resp.state.items?.length ?? 0} items. Review bên dưới.`)
    } catch (e) {
      if (e.status === 503) {
        setUpMsg('LLM chưa sẵn sàng (503): bật Ollama rồi thử lại.')
      } else {
        setUpMsg(`Lỗi (${e.status ?? '?'}): ${JSON.stringify(e.body)}`)
      }
    } finally {
      setUpBusy(false)
    }
  }

  const counts = useMemo(() => {
    const c = { red: 0, yellow: 0, green: 0, all: visibleItems.length }
    visibleItems.forEach((it) => {
      c[levelOf(it.confidence)]++
    })
    return c
  }, [visibleItems])

  const partitioned = useMemo(() => {
    const pass =
      filter === 'all' ? () => true :
      filter === 'red' ? (conf) => levelOf(conf) === 'red' :
      filter === 'yellow' ? (conf) => levelOf(conf) === 'yellow' :
        (conf) => levelOf(conf) === 'green'
    const items = visibleItems.filter((it) => pass(it.confidence))
    const risk = (it) => ({ red: 0, yellow: 1, green: 2 })[levelOf(it.confidence)]
    const byRisk = (arr) => [...arr].sort((a, b) => {
      const r = risk(a) - risk(b)
      if (r !== 0) return r
      const ac = confirmedIds.has(a.id) ? 1 : 0
      const bc = confirmedIds.has(b.id) ? 1 : 0
      return ac - bc
    })
    const finalDecisions = byRisk(items.filter((it) => it.type === 'decision' && it.status === 'final'))
    const discardedByFinal = {}
    finalDecisions.forEach((fd) => {
      discardedByFinal[fd.id] = items.filter(
        (it) => it.type === 'decision' && (fd.supersedes || []).includes(it.id),
      )
    })
    return {
      finalDecisions,
      discardedByFinal,
      tasks: byRisk(items.filter((it) => it.type === 'task')),
      blockers: byRisk(items.filter((it) => it.type === 'blocker')),
      openIssues: byRisk(items.filter((it) => it.type === 'open_issue')),
      requirements: byRisk(items.filter((it) => it.type === 'requirement')),
      knowledge: byRisk(items.filter((it) => it.type === 'knowledge')),
    }
  }, [visibleItems, filter, confirmedIds])

  const flatVisibleIds = useMemo(() => {
    const cols = [
      partitioned.finalDecisions,
      partitioned.tasks,
      partitioned.blockers,
      partitioned.openIssues,
      partitioned.requirements,
      partitioned.knowledge,
    ]
    return cols.flat().map((it) => it.id)
  }, [partitioned])

  const itemById = useCallback(
    (id) => visibleItems.find((it) => it.id === id),
    [visibleItems],
  )

  const focusCard = useCallback((id) => {
    setFocusedId(id)
    requestAnimationFrame(() => {
      cardRefs.current[id]?.focus?.()
      cardRefs.current[id]?.scrollIntoView({ block: 'center' })
    })
  }, [])

  useEffect(() => {
    function onKey(e) {
      if (isInteractiveTarget(e)) {
        if (e.key === 'Escape' && document.activeElement) document.activeElement.blur()
        return
      }
      if (e.key === 'Escape') {
        if (drawer) closeDrawer()
        return
      }
      if (flatVisibleIds.length === 0) return
      const idx = flatVisibleIds.indexOf(focusedId)
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        focusCard(flatVisibleIds[Math.min(idx + 1, flatVisibleIds.length - 1)] ?? flatVisibleIds[0])
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        focusCard(flatVisibleIds[Math.max(idx - 1, 0)] ?? flatVisibleIds[0])
      } else if (e.key === 'a') {
        const it = itemById(focusedId ?? flatVisibleIds[0])
        if (it && onAgreeRef.current) onAgreeRef.current(it)
      } else if (e.key === 'e') {
        const id = focusedId ?? flatVisibleIds[0]
        const btn = document.querySelector(`[data-testid="card-${id}-edit"]`)
        if (btn) btn.click()
        else {
          const anyBtn = document.querySelector(`[data-testid="card-${id}"] button`)
          if (anyBtn) anyBtn.focus()
        }
      } else if (e.key === 'x') {
        const it = itemById(focusedId ?? flatVisibleIds[0])
        if (it && onRemoveRef.current) onRemoveRef.current(it)
      } else if (e.key === 'Enter') {
        const it = itemById(focusedId ?? flatVisibleIds[0])
        if (it && it.evidence?.[0] && showEvidenceRef.current) {
          showEvidenceRef.current(it.evidence[0])
        }
      } else if (['1', '2', '3', '4'].includes(e.key)) {
        setFilter({ 1: 'all', 2: 'red', 3: 'yellow', 4: 'green' }[e.key])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flatVisibleIds, focusedId, drawer, focusCard, itemById])

  function cardProps(it) {
    return {
      item: it,
      allIds,
      focused: focusedId === it.id,
      confirmed: confirmedIds.has(it.id),
      cardRef: (el) => {
        cardRefs.current[it.id] = el
      },
      onAgree,
      onEdit,
      onRemove,
      onShowEvidence: showEvidence,
    }
  }

  return (
    <div className="min-h-screen bg-background font-sans text-sm text-foreground">
      <Toaster />
      <div className="grid min-h-screen xl:grid-cols-[280px_1fr]">
        {/* ─── Sidebar ──────────────────────────────────────────── */}
        <aside className="flex flex-col gap-4 border-b bg-card p-4 xl:h-screen xl:overflow-y-auto xl:border-r xl:border-b-0">
          <div>
            <h1 className="font-heading text-xl font-bold">meet2note</h1>
            {state?.meeting && (
              <p className="text-xs text-muted-foreground">
                {state.meeting.title} · {state.meeting.date}
              </p>
            )}
          </div>

          <Collapsible defaultOpen>
            <CollapsibleTrigger className="flex w-full items-center gap-1 text-sm font-semibold">
              <ChevronDown className="size-4" /> ① Meeting
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 flex flex-col gap-2">
              <Label htmlFor="meeting-id">Meeting id</Label>
              <Input
                id="meeting-id"
                value={meetingInput}
                onChange={(e) => setMeetingInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') load(meetingInput)
                }}
                data-testid="meeting-input"
              />
              <Button onClick={() => load(meetingInput)} disabled={busy}>
                {busy ? 'Đang tải…' : 'Load'}
              </Button>
              {loadError && (
                <Alert variant="destructive">
                  <AlertDescription>{loadError}</AlertDescription>
                </Alert>
              )}
              {busy && !state && (
                <div className="flex flex-col gap-2" aria-label="đang tải">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>

          <Collapsible defaultOpen>
            <CollapsibleTrigger className="flex w-full items-center gap-1 text-sm font-semibold">
              <ChevronDown className="size-4" /> ② Review
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 flex flex-col gap-3">
              <div>
                <div className="flex items-center justify-between text-xs">
                  <span aria-live="polite">
                    Đã xác nhận {confirmedIds.size}/{visibleItems.length}
                  </span>
                </div>
                <Progress
                  value={visibleItems.length === 0 ? 0 : (confirmedIds.size / visibleItems.length) * 100}
                  className="mt-1"
                />
              </div>
              <ToggleGroup type="single" value={filter} onValueChange={(v) => v && setFilter(v)}>
                <ToggleGroupItem value="all">tất cả {counts.all}</ToggleGroupItem>
                <ToggleGroupItem value="red">🔴 {counts.red}</ToggleGroupItem>
                <ToggleGroupItem value="yellow">🟡 {counts.yellow}</ToggleGroupItem>
                <ToggleGroupItem value="green">🟢 {counts.green}</ToggleGroupItem>
              </ToggleGroup>
              {gateOpen ? (
                <Alert variant="ok">
                  <AlertTitle>Đủ điều kiện export</AlertTitle>
                </Alert>
              ) : (
                <Alert variant="destructive">
                  <AlertTitle>Còn {redItems.length} thẻ đỏ chưa xử lý</AlertTitle>
                  <AlertDescription>{redItems.map((it) => it.id).join(', ')}</AlertDescription>
                </Alert>
              )}
              <Button onClick={doExport} disabled={!gateOpen || busy} data-testid="export-btn">
                <Download className="size-4" />
                {gateOpen ? 'Export' : `Khoá (${redItems.length} đỏ)`}
              </Button>
              {exportFiles && exportFiles.length > 0 && (
                <Alert variant="ok">
                  <AlertTitle>Export xong</AlertTitle>
                  <AlertDescription>
                    <ul>
                      {exportFiles.map((f) => (
                        <li key={f}>
                          <code className="text-xs">{f}</code>
                        </li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              )}
              {exportError && (
                <Alert variant="destructive">
                  <AlertDescription>{exportError}</AlertDescription>
                </Alert>
              )}
              {Array.isArray(state?.known_limitations) && state.known_limitations.length > 0 && (
                <Collapsible>
                  <CollapsibleTrigger className="flex w-full items-center gap-1 text-xs text-muted-foreground">
                    <ChevronDown className="size-3" />
                    ⚠ known_limitations ({state.known_limitations.length})
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <ul className="mt-1 flex max-h-40 flex-col gap-1 overflow-y-auto text-xs text-muted-foreground">
                      {state.known_limitations.map((lim, i) => (
                        <li key={i}>{lim}</li>
                      ))}
                    </ul>
                  </CollapsibleContent>
                </Collapsible>
              )}
            </CollapsibleContent>
          </Collapsible>

          <Collapsible>
            <CollapsibleTrigger className="flex w-full items-center gap-1 text-sm font-semibold">
              <ChevronDown className="size-4" /> ③ Upload
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 flex flex-col gap-2">
              <Label htmlFor="up-file">File transcript</Label>
              <Input
                id="up-file"
                type="file"
                accept=".txt,.srt,.docx"
                onChange={(e) => setUpFile(e.target.files?.[0] ?? null)}
                data-testid="upload-file"
                className="hidden"
              />
              <Label
                htmlFor="up-file"
                className="flex cursor-pointer flex-col items-center gap-1 rounded-lg border-2 border-dashed border-primary/40 bg-primary/5 px-3 py-4 text-center text-xs text-foreground transition-colors hover:border-primary hover:bg-primary/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <Upload className="size-5 text-primary" />
                {upFile ? (
                  <>
                    <span className="font-semibold break-words">{upFile.name}</span>
                    <span className="text-muted-foreground">
                      {(upFile.size / 1024).toFixed(1)} KB — bấm để đổi file
                    </span>
                  </>
                ) : (
                  <>
                    <span className="font-semibold">Bấm để chọn file</span>
                    <span className="text-muted-foreground">.txt / .srt / .docx</span>
                  </>
                )}
              </Label>
              <Label htmlFor="up-id">Meeting id (trống = từ tên file)</Label>
              <Input id="up-id" value={upId} onChange={(e) => setUpId(e.target.value)} />
              <Label htmlFor="up-title">Title</Label>
              <Input id="up-title" value={upTitle} onChange={(e) => setUpTitle(e.target.value)} />
              <Label htmlFor="up-date">Date</Label>
              <Input id="up-date" type="date" value={upDate} onChange={(e) => setUpDate(e.target.value)} />
              <Label htmlFor="up-parts">Participants (mỗi dòng: Tên (role))</Label>
              <Textarea
                id="up-parts"
                rows={3}
                value={upParts}
                onChange={(e) => setUpParts(e.target.value)}
              />
              <Button onClick={doUpload} disabled={upBusy} data-testid="upload-submit">
                <Upload className="size-4" />
                {upBusy ? 'Đang chạy pipeline…' : 'Upload + chạy'}
              </Button>
              {upMsg && <p className="text-xs">{upMsg}</p>}
            </CollapsibleContent>
          </Collapsible>

          <Separator />
          <p className="text-xs text-muted-foreground">
            Phím tắt: <code>j/k</code> di chuyển · <code>a</code> đồng ý ·{' '}
            <code>e</code> sửa · <code>x</code> loại · <code>Enter</code> mở transcript ·{' '}
            <code>1–4</code> lọc
          </p>
        </aside>

        {/* ─── Main ─────────────────────────────────────────────── */}
        <main className="min-w-0 p-4 xl:h-screen xl:overflow-y-auto">
          {!state && !busy && (
            <p className="text-sm text-muted-foreground">
              Chưa load meeting. Nhập id ở sidebar → Load (gợi ý: tc1..tc5).
            </p>
          )}
          {busy && !state && (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex flex-col gap-2 rounded-lg border p-3">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ))}
            </div>
          )}
          {state && (
            <>
              <header className="sticky top-0 z-10 max-h-16 overflow-hidden bg-background/90 pb-2 backdrop-blur">
                <h2 className="font-heading text-lg font-semibold">
                  {state.meeting?.title} — {state.meeting?.date}
                </h2>
                <p className="text-xs text-muted-foreground">
                  meeting id: <code>{state.meeting?.id}</code> · pipeline{' '}
                  <code>{state.meeting?.pipeline_version}</code>
                </p>
              </header>

              {(state.meeting?.participants ?? []).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {(state.meeting.participants ?? []).map((p) => (
                    <Badge key={p.name} variant="secondary">
                      {p.name} · {p.role}
                    </Badge>
                  ))}
                </div>
              )}

              {state.no_decision && (
                <Alert variant="warn" className="mt-2">
                  <AlertTitle>Họp không chốt nội dung nào — xem Open Issue</AlertTitle>
                </Alert>
              )}

              {state.brief && (
                <Alert variant="info" className="mt-2">
                  <AlertTitle>Vấn đề: {state.brief.problem}</AlertTitle>
                  {(state.brief.outcomes ?? []).length > 0 && (
                    <AlertDescription>
                      <ul className="mt-1 flex flex-col gap-1">
                        {(state.brief.outcomes ?? []).map((o, i) => (
                          <li key={i}>
                            {o.text}{' '}
                            {(o.ref_ids ?? []).map((r) => (
                              <Badge key={r} variant="outline" className="mr-1">
                                {r}
                              </Badge>
                            ))}
                          </li>
                        ))}
                      </ul>
                    </AlertDescription>
                  )}
                </Alert>
              )}

              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <Column
                  title="✅ Quyết định"
                  items={partitioned.finalDecisions}
                  emptyHint={filter !== 'all' ? 'thử tắt lọc' : ''}
                  render={(d) => (
                    <div key={d.id}>
                      <ItemCard
                        {...cardProps(d)}
                        cardRef={(el) => {
                          cardRefs.current[d.id] = el
                        }}
                      />
                      <DiscardedList items={partitioned.discardedByFinal[d.id] ?? []} />
                    </div>
                  )}
                />
                <Column
                  title="📌 Công việc"
                  items={partitioned.tasks}
                  emptyHint={filter !== 'all' ? 'thử tắt lọc' : ''}
                  render={(t) => (
                    <ItemCard
                      {...cardProps(t)}
                      cardRef={(el) => {
                        cardRefs.current[t.id] = el
                      }}
                    />
                  )}
                />
                <Column
                  title="⚠️ Vướng mắc & Chưa chốt"
                  items={[...partitioned.blockers, ...partitioned.openIssues]}
                  emptyHint={filter !== 'all' ? 'thử tắt lọc' : ''}
                  render={(b) => (
                    <ItemCard
                      {...cardProps(b)}
                      cardRef={(el) => {
                        cardRefs.current[b.id] = el
                      }}
                    />
                  )}
                />
                <Column
                  title="📋 Yêu cầu & Phản hồi"
                  items={[...partitioned.requirements, ...partitioned.knowledge]}
                  emptyHint="cột này thường rỗng ở họp nhỏ"
                  render={(r) => (
                    <ItemCard
                      {...cardProps(r)}
                      cardRef={(el) => {
                        cardRefs.current[r.id] = el
                      }}
                    />
                  )}
                />
              </div>
            </>
          )}
        </main>
      </div>

      <TranscriptSheet
        view={drawer}
        drawerError={drawerError}
        onClose={closeDrawer}
      />
    </div>
  )
}
