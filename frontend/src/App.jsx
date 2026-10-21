/**
 * src/App.jsx — meet2note Review Workspace.
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
  ArrowRight,
  Check,
  CheckCheck,
  ChevronDown,
  Download,
  FileText,
  Filter,
  History,
  Keyboard,
  Link2,
  LogOut,
  Pencil,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  Trash2,
  Upload,
  UserCheck,
  X,
  Zap,
} from 'lucide-react'
import {
  downloadExport,
  getMe,
  getReview,
  listMeetings,
  login,
  logout,
  putReview,
  postExport,
  getTranscript,
  register,
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

const ROLE_VN = {
  propose: 'đề xuất',
  object: 'phản đối',
  decide: 'chốt',
  confirm: 'xác nhận',
  info: 'thông tin',
}

function isInteractiveTarget(e) {
  const t = e.target
  if (!t || !t.closest) return false
  return Boolean(t.closest('input, textarea, select, [contenteditable="true"]'))
}

function loadConfirmedSession(meetingId) {
  if (!meetingId) return new Set()
  try {
    const raw = sessionStorage.getItem(`m2n_confirmed_${meetingId}`)
    if (!raw) return new Set()
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? new Set(arr) : new Set()
  } catch {
    return new Set()
  }
}

function saveConfirmedSession(meetingId, setObj) {
  if (!meetingId) return
  try {
    sessionStorage.setItem(`m2n_confirmed_${meetingId}`, JSON.stringify([...setObj]))
  } catch {
    // ignore storage quota errors
  }
}

function itemInvolvesParticipant(item, participantName) {
  if (!participantName) return true
  const p = participantName.toLowerCase()
  const fields = [
    item.decided_by,
    item.owner,
    item.needs_action_from,
    item.next_step_owner,
    item.raised_by,
  ]
  if (fields.some((f) => String(f || '').toLowerCase() === p)) return true
  if (
    Array.isArray(item.evidence) &&
    item.evidence.some((ev) => String(ev.speaker || '').toLowerCase() === p)
  ) {
    return true
  }
  return false
}

function itemMatchesQuery(item, query) {
  if (!query) return true
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = [
    item.id,
    item.content,
    item.what,
    item.reason,
    item.next_step,
    item.owner,
    item.decided_by,
    item.due,
    item.due_hint,
    ...(item.evidence ?? []).map((ev) => `${ev.speaker} ${ev.quote} ${ev.timestamp}`),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return hay.includes(q)
}

// ─── Evidence: hiện sẵn 2 dòng + "+N" ───────────────────────────────────────

function EvidenceLines({ evidence, onShow }) {
  const [expanded, setExpanded] = useState(false)
  if (!Array.isArray(evidence) || evidence.length === 0) return null
  const shown = expanded ? evidence : evidence.slice(0, 2)
  return (
    <div className="flex flex-col gap-1.5">
      {shown.map((ev, i) => {
        const isDecide = ev.role_in_discussion === 'decide'
        return (
          <div
            key={i}
            className={`rounded-lg border border-border/60 border-l-3 bg-evidence-bg px-2.5 py-1.5 text-xs leading-relaxed transition-colors hover:border-primary/40 ${
              isDecide ? 'border-l-primary' : ''
            }`}
            style={!isDecide ? { borderLeftColor: 'var(--color-evidence-rule)' } : undefined}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={() => onShow(ev)}
                title="Mở transcript tại lượt này"
                className="inline-flex min-h-6 min-w-6 items-center rounded bg-primary/10 px-1.5 py-0.5 font-mono text-xs font-semibold text-primary underline-offset-2 transition-colors hover:bg-primary hover:text-primary-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                [{ev.timestamp}]
              </button>
              <span className="font-semibold text-foreground">{ev.speaker}</span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                {ROLE_VN[ev.role_in_discussion] ?? ev.role_in_discussion}
              </span>
            </div>
            <p className="mt-1 italic text-foreground/90 break-words">
              <q>“{ev.quote}”</q>
            </p>
          </div>
        )
      })}
      {evidence.length > 2 && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="self-start text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
        >
          {expanded ? 'Thu gọn bằng chứng' : `+${evidence.length - 2} bằng chứng khác`}
        </button>
      )}
    </div>
  )
}

// ─── Meta pills theo loại item (ui-spec §3.2 + §4) ──────────────────────────

const SEVERITY_VN = { low: 'Thấp', medium: 'Trung bình', high: 'Cao' }
const ORIGIN_VN = { customer: 'Khách hàng', internal: 'Nội bộ', partner: 'Đối tác', unknown: 'Chưa rõ' }

function Meta({ label, children, tone = 'secondary', hint, onClick }) {
  const pill = (
    <Badge
      variant={tone}
      onClick={onClick}
      className={onClick ? 'cursor-pointer transition-transform hover:scale-105' : ''}
    >
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

function MetaPills({ item, allIds, linkedTasksByDecision, onJumpToItem }) {
  const pills = []
  const missing = <span className="text-muted-foreground">—</span>
  const confReason = String(item.confidence_reason || '')
  if (item.type === 'task') {
    const isDueRevised = Boolean(
      item.due_hint && (item.due_hint.includes('revised') || item.due_hint.includes('→')),
    )
    pills.push(
      <Meta key="owner" label="Người làm" tone={item.owner === 'TBD' ? 'conf-amber' : 'secondary'}>
        {item.owner === 'TBD' ? 'TBD' : item.owner}
      </Meta>,
    )
    pills.push(
      <Meta
        key="due"
        label="Hạn"
        tone={item.due === 'TBD' || isDueRevised ? 'conf-amber' : 'secondary'}
        hint={item.due_hint ? `Chữ gốc trong họp: “${item.due_hint}”` : undefined}
      >
        {item.due === 'TBD' ? 'TBD' : item.due}
        {item.due_source === 'inferred' ? ' · suy luận' : ''}
        {isDueRevised ? ' · đã dời hạn' : ''}
      </Meta>,
    )
    if (item.link_to_decision) {
      const ok = allIds.has(item.link_to_decision)
      pills.push(
        <Meta
          key="link"
          label="Theo QĐ"
          tone={ok ? 'secondary' : 'destructive'}
          hint={ok ? `Bấm để nhảy tới quyết định ${item.link_to_decision}` : 'ID quyết định không tồn tại'}
          onClick={ok && onJumpToItem ? () => onJumpToItem(item.link_to_decision) : undefined}
        >
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
    const linkedTasks = linkedTasksByDecision?.[item.id] ?? []
    if (linkedTasks.length > 0) {
      pills.push(
        <Meta
          key="linked-tasks"
          label="Task phục vụ"
          tone="secondary"
          hint={`Bấm để nhảy tới công việc ${linkedTasks[0].id}`}
          onClick={onJumpToItem ? () => onJumpToItem(linkedTasks[0].id) : undefined}
        >
          <Link2 className="size-3" /> {linkedTasks.map((t) => t.id).join(', ')}
        </Meta>,
      )
    }
    if (confReason.includes('single-evidence-final')) {
      pills.push(
        <Meta
          key="m3c"
          label="Chuỗi"
          tone="conf-amber"
          hint="M3-C: Quyết định final chỉ có 1 evidence đơn lẻ (thiếu chuỗi propose → decide → confirm)"
        >
          1 evidence đơn lẻ
        </Meta>,
      )
    }
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
      if (t === 'reclassify') {
        pills.push(
          <Meta
            key="tag-reclassify"
            label="M3-D"
            tone="conf-amber"
            hint="Tự động phân loại lại từ Task sang Knowledge (quy ước/lâu dài, không có owner/due cụ thể)"
          >
            tự phân loại từ Task
          </Meta>,
        )
      } else {
        pills.push(<Badge key={`tag-${t}`} variant="outline">{t}</Badge>)
      }
    })
    if (item.context) pills.push(<Badge key="ctx" variant="outline">{item.context}</Badge>)
  }
  if (pills.length === 0) return null
  return <div className="flex flex-wrap gap-1.5">{pills}</div>
}

// ─── Cảnh báo semantic trên card (ui-spec §4) ───────────────────────────────

function SemanticAlerts({ item }) {
  const [objectionsOpen, setObjectionsOpen] = useState(false)
  return (
    <>
      {item.unresolved_reversal === true && (
        <Alert variant="destructive" className="mb-2">
          <AlertTriangle className="size-4" />
          <AlertTitle>Đảo quyết định (A→B→A) — cần host chốt</AlertTitle>
        </Alert>
      )}
      {Array.isArray(item.objections) && item.objections.length > 0 && (
        <Collapsible open={objectionsOpen} onOpenChange={setObjectionsOpen} className="mb-2">
          <div className="rounded-lg border border-conf-amber/40 bg-conf-amber-bg px-3 py-2 text-xs text-conf-amber">
            <CollapsibleTrigger className="flex w-full items-center justify-between gap-1 font-semibold">
              <span>⛔ Ý kiến phản đối được bảo lưu ({item.objections.length})</span>
              <ChevronDown className="size-3.5" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-1.5 flex flex-col gap-1 border-t border-conf-amber/20 pt-1.5">
                {item.objections.map((o, i) => (
                  <li key={i}>
                    {typeof o === 'string' ? (
                      o
                    ) : (
                      <>
                        [{o.timestamp}] <strong>{o.speaker}</strong>: “{o.quote}”
                      </>
                    )}
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
  item,
  allIds,
  participants,
  finalDecisionIds,
  linkedTasksByDecision,
  focused,
  confirmed,
  cardRef,
  onAgree,
  onEdit,
  onRemove,
  onShowEvidence,
  onHover,
  onJumpToItem,
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => ({
    content: item.content ?? item.what ?? '',
    owner: item.owner ?? '',
    due: item.due ?? '',
    link_to_decision: item.link_to_decision ?? '',
  }))

  function openEdit() {
    setDraft({
      content: item.content ?? item.what ?? '',
      owner: item.owner ?? '',
      due: item.due ?? '',
      link_to_decision: item.link_to_decision ?? '',
    })
    setEditing(true)
  }

  const level = levelOf(item.confidence)
  const red = level === 'red'
  const yellow = level === 'yellow'
  const contentText = item.type === 'task' ? item.what || '' : item.content || ''

  return (
    <Card
      ref={cardRef}
      tabIndex={0}
      onMouseEnter={() => onHover && onHover(item.id)}
      onMouseLeave={() => onHover && onHover(null)}
      data-testid={`card-${item.id}`}
      aria-label={`${TYPE_LABEL[item.type] ?? item.type} ${item.id}, confidence ${item.confidence}, mức ${LEVEL_VN[level]}`}
      className={[
        'group relative flex min-w-0 flex-col justify-between overflow-hidden break-words p-3 transition-all duration-150 ease-out hover:shadow-card-hover hover:-translate-y-0.5',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
        focused ? 'ring-2 ring-primary ring-offset-2 shadow-card-hover' : 'shadow-card',
        red ? 'border-conf-red/40 border-l-4 bg-conf-red-bg/35' : '',
        yellow ? 'border-conf-amber/40 border-l-4 bg-conf-amber-bg/25' : '',
        !red && !yellow ? 'border-conf-green/35 border-l-4 bg-card' : '',
        confirmed ? 'border-conf-green/60 bg-conf-green-bg/20' : '',
      ].join(' ')}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs font-semibold text-foreground">
              {item.id}
            </code>
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
          </div>
          <div className="flex items-center gap-1">
            {red && !confirmed && (
              <Badge variant="destructive" className="animate-pulse">
                cần xử lý
              </Badge>
            )}
            {confirmed && (
              <Badge variant="conf-green">
                <Check className="size-3" /> đã xác nhận
              </Badge>
            )}
          </div>
        </div>

        <p className="mt-2.5 text-sm font-semibold leading-snug text-foreground break-words">
          {contentText}
        </p>

        <div className="mt-2">
          <SemanticAlerts item={item} />
        </div>

        <div className="mt-2">
          <MetaPills
            item={item}
            allIds={allIds}
            linkedTasksByDecision={linkedTasksByDecision}
            onJumpToItem={onJumpToItem}
          />
        </div>

        {/* Câu dài (lý do / next_step) render dạng text wrap, KHÔNG pill */}
        {item.type === 'decision' && item.reason && (
          <p className="mt-2 rounded-md bg-muted/60 px-2.5 py-1.5 text-xs text-muted-foreground break-words">
            <strong className="font-medium text-foreground">Lý do chốt:</strong> {item.reason}
          </p>
        )}
        {item.type === 'open_issue' && item.next_step && (
          <p className="mt-2 rounded-md bg-conf-amber-bg/60 px-2.5 py-1.5 text-xs text-conf-amber break-words">
            <strong className="font-semibold">Bước tiếp theo:</strong> {item.next_step}
          </p>
        )}

        <div className="mt-2.5" data-testid={`card-${item.id}-evidence`}>
          <EvidenceLines evidence={item.evidence} onShow={onShowEvidence} />
        </div>
      </div>

      {editing ? (
        <div className="mt-3 flex flex-col gap-2.5 rounded-lg border border-primary/30 bg-muted/40 p-2.5">
          <div>
            <Label htmlFor={`edit-content-${item.id}`}>Nội dung</Label>
            <Textarea
              id={`edit-content-${item.id}`}
              value={draft.content}
              onChange={(e) => setDraft({ ...draft, content: e.target.value })}
              className="mt-1 bg-card"
            />
          </div>
          {item.type === 'task' && (
            <>
              <div>
                <Label htmlFor={`edit-owner-${item.id}`}>Người phụ trách (Owner)</Label>
                <Input
                  id={`edit-owner-${item.id}`}
                  value={draft.owner}
                  onChange={(e) => setDraft({ ...draft, owner: e.target.value })}
                  className="mt-1 bg-card"
                />
                {Array.isArray(participants) && participants.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {participants.map((p) => (
                      <button
                        key={p.name}
                        type="button"
                        onClick={() => setDraft({ ...draft, owner: p.name })}
                        className={`rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                          draft.owner === p.name
                            ? 'border-primary bg-primary text-primary-foreground'
                            : 'border-border bg-card text-foreground hover:border-primary'
                        }`}
                      >
                        {p.name}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => setDraft({ ...draft, owner: 'TBD' })}
                      className={`rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                        draft.owner === 'TBD'
                          ? 'border-conf-amber bg-conf-amber-bg text-conf-amber'
                          : 'border-border bg-card text-muted-foreground hover:border-conf-amber'
                      }`}
                    >
                      TBD
                    </button>
                  </div>
                )}
              </div>
              <div>
                <Label htmlFor={`edit-due-${item.id}`}>Hạn chót (YYYY-MM-DD hoặc TBD)</Label>
                <div className="mt-1 flex gap-1.5">
                  <Input
                    id={`edit-due-${item.id}`}
                    value={draft.due}
                    onChange={(e) => setDraft({ ...draft, due: e.target.value })}
                    className="bg-card"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setDraft({ ...draft, due: 'TBD' })}
                  >
                    TBD
                  </Button>
                </div>
              </div>
            </>
          )}
          <div>
            <Label htmlFor={`edit-link-${item.id}`}>Liên kết Quyết định (link_to_decision)</Label>
            <Input
              id={`edit-link-${item.id}`}
              value={draft.link_to_decision}
              onChange={(e) => setDraft({ ...draft, link_to_decision: e.target.value })}
              className="mt-1 bg-card"
            />
            {Array.isArray(finalDecisionIds) && finalDecisionIds.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {finalDecisionIds.map((did) => (
                  <button
                    key={did}
                    type="button"
                    onClick={() => setDraft({ ...draft, link_to_decision: did })}
                    className={`rounded-md border px-2 py-0.5 font-mono text-[11px] font-medium transition-colors ${
                      draft.link_to_decision === did
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border bg-card text-foreground hover:border-primary'
                    }`}
                  >
                    {did}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setDraft({ ...draft, link_to_decision: '' })}
                  className="rounded-md border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground hover:border-destructive"
                >
                  Bỏ link
                </button>
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-1.5 pt-1">
            <Button
              size="xs"
              className="min-w-0 w-full"
              onClick={() => {
                onEdit(item, draft)
                setEditing(false)
              }}
            >
              <Check className="size-3.5" /> Lưu
            </Button>
            <Button
              size="xs"
              variant="outline"
              className="min-w-0 w-full"
              onClick={() => setEditing(false)}
            >
              <X className="size-3.5" /> Huỷ
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-3 grid grid-cols-3 gap-1 border-t border-border/60 pt-2.5">
          <Button
            size="xs"
            variant={confirmed ? 'secondary' : 'outline'}
            onClick={() => onAgree(item)}
            data-testid={`card-${item.id}-agree`}
            className={`min-w-0 w-full px-1.5 text-[11px] ${
              confirmed
                ? 'border-conf-green/40 bg-conf-green-bg text-conf-green hover:bg-conf-green-bg/80'
                : 'hover:border-conf-green hover:text-conf-green'
            }`}
          >
            <Check className="size-3 shrink-0" />
            <span className="truncate">{confirmed ? 'Đã duyệt' : 'Đồng ý'}</span>
          </Button>
          <Button
            size="xs"
            variant="outline"
            onClick={openEdit}
            data-testid={`card-${item.id}-edit`}
            className="min-w-0 w-full px-1.5 text-[11px] hover:border-primary hover:text-primary"
          >
            <Pencil className="size-3 shrink-0" />
            <span className="truncate">Sửa</span>
          </Button>
          <Button
            size="xs"
            variant="outline"
            onClick={() => onRemove(item)}
            className="min-w-0 w-full px-1.5 text-[11px] text-destructive hover:border-destructive hover:bg-conf-red-bg"
            title="Loại khỏi biên bản (vẫn lưu vết audit)"
          >
            <Trash2 className="size-3 shrink-0" />
            <span className="truncate">Loại</span>
          </Button>
        </div>
      )}
    </Card>
  )
}

// ─── Lịch sử supersedes thu gọn (Timeline A → B) ─────────────────────────────

function DiscardedList({ items, onShowEvidence }) {
  if (!items.length) return null
  return (
    <Collapsible defaultOpen className="mt-1.5 mb-2 ml-3 border-l-2 border-primary/30 pl-3">
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-primary">
        <History className="size-3.5 text-primary" />
        <span>
          Lịch sử đảo chiều: đã thay thế {items.map((i) => i.id).join(', ')}
        </span>
        <ChevronDown className="size-3" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1.5 flex flex-col gap-1.5">
          {items.map((it) => (
            <div
              key={it.id}
              className="rounded-lg border border-dashed border-border bg-muted/50 p-2.5 text-xs text-muted-foreground"
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <code className="rounded bg-card px-1 py-0.5 font-mono font-semibold text-foreground">
                    {it.id}
                  </code>{' '}
                  <Badge variant="outline" className="text-[10px]">
                    đã bác bỏ (discarded)
                  </Badge>
                </div>
                {it.evidence?.[0] && onShowEvidence && (
                  <button
                    type="button"
                    onClick={() => onShowEvidence(it.evidence[0])}
                    className="font-mono text-[11px] text-primary hover:underline"
                  >
                    [{it.evidence[0].timestamp}]
                  </button>
                )}
              </div>
              <p className="mt-1 line-through decoration-muted-foreground/50">{it.content}</p>
              {Array.isArray(it.objections) && it.objections.length > 0 && (
                <ul className="mt-1.5 flex flex-col gap-1 border-t border-border/60 pt-1 text-[11px] text-conf-amber">
                  {it.objections.map((o, i) => (
                    <li key={i}>
                      {typeof o === 'string' ? (
                        o
                      ) : (
                        <>
                          ⛔ [{o.timestamp}] <strong>{o.speaker}</strong>: “{o.quote}”
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// ─── Cột Kanban ──────────────────────────────────────────────────────────────

function Column({ title, subtitle, items, render, emptyHint }) {
  const redCount = items.filter((i) => levelOf(i.confidence) === 'red').length
  return (
    <section className="flex min-w-0 flex-col gap-2.5 rounded-xl border border-border/80 bg-muted/35 p-2.5">
      <div className="flex items-center justify-between gap-2 border-b border-border/70 pb-2">
        <div className="min-w-0">
          <h3 className="font-heading text-sm font-bold text-foreground truncate">{title}</h3>
          {subtitle && <p className="text-[11px] text-muted-foreground truncate">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {redCount > 0 && (
            <span className="rounded-full bg-conf-red-bg px-2 py-0.5 text-[11px] font-semibold text-conf-red">
              {redCount} đỏ
            </span>
          )}
          <span className="rounded-full bg-card border border-border px-2.5 py-0.5 text-xs font-semibold text-foreground">
            {items.length}
          </span>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/50 px-4 py-8 text-center text-xs text-muted-foreground">
          <span>Không có mục nào{emptyHint ? ` — ${emptyHint}` : ''}</span>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">{items.map(render)}</div>
      )}
    </section>
  )
}

// ─── Drawer transcript (Sheet) ─────────────────────────────────────────────

function TranscriptSheet({ view, drawerError, onClose }) {
  const targetRef = useRef(null)
  const [showAllTurns, setShowAllTurns] = useState(false)
  const [turnQuery, setTurnQuery] = useState('')

  useEffect(() => {
    if (view && targetRef.current) {
      targetRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [view, showAllTurns])

  const allTurns = view?.turns ?? []
  const q = turnQuery.trim().toLowerCase()
  const filteredTurns = allTurns.filter((t) => {
    const inWindow =
      showAllTurns ||
      view?.targetTurn == null ||
      Math.abs((t.turn ?? 0) - view.targetTurn) <= 4
    if (!inWindow) return false
    if (!q) return true
    return (
      String(t.speaker || '').toLowerCase().includes(q) ||
      String(t.text || '').toLowerCase().includes(q) ||
      String(t.t_start || '').toLowerCase().includes(q)
    )
  })

  return (
    <Sheet
      open={view !== null}
      onOpenChange={(o) => {
        if (!o) onClose()
      }}
    >
      <SheetContent showClose={false} className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-2 border-b border-border pb-3">
          <div>
            <SheetTitle className="font-heading text-base">
              Transcript gốc · lượt #{view?.targetTurn ?? '?'}
            </SheetTitle>
            <SheetDescription className="text-xs">
              {view?.source || 'transcript'} ·{' '}
              {showAllTurns
                ? `Đang hiện toàn bộ (${allTurns.length} lượt)`
                : '±4 lượt quanh câu trích dẫn (R5)'}
            </SheetDescription>
          </div>
          <Button size="sm" variant="outline" onClick={onClose}>
            <X className="size-3.5" /> Đóng (Esc)
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-border bg-muted p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setShowAllTurns(false)}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                !showAllTurns ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground'
              }`}
            >
              ±4 lượt quanh câu trích
            </button>
            <button
              type="button"
              onClick={() => setShowAllTurns(true)}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                showAllTurns ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground'
              }`}
            >
              Toàn bộ ({allTurns.length})
            </button>
          </div>
          <div className="relative flex-1 min-w-[160px]">
            <Input
              value={turnQuery}
              onChange={(e) => {
                setTurnQuery(e.target.value)
                if (e.target.value && !showAllTurns) setShowAllTurns(true)
              }}
              placeholder="Tìm trong transcript..."
              className="h-8 text-xs"
            />
          </div>
        </div>

        {drawerError && (
          <Alert variant="destructive">
            <AlertDescription>{drawerError}</AlertDescription>
          </Alert>
        )}

        <div className="flex-1 overflow-y-auto rounded-xl border border-border bg-muted/30 p-3 text-xs leading-relaxed">
          <div className="flex flex-col gap-2">
            {filteredTurns.map((t) => {
              const isTarget = t.turn === view?.targetTurn
              const body = (() => {
                const q = view?.quote
                if (!isTarget || !q || !t.text.includes(q)) return t.text
                const [head, ...rest] = t.text.split(q)
                return (
                  <>
                    {head}
                    <mark className="rounded bg-hl-bg px-1 py-0.5 font-medium text-foreground outline outline-hl-border">
                      {q}
                    </mark>
                    {rest.join(q)}
                  </>
                )
              })()
              return (
                <div
                  key={t.turn}
                  ref={isTarget ? targetRef : undefined}
                  className={`rounded-lg border p-2.5 transition-colors ${
                    isTarget
                      ? 'border-hl-border bg-hl-bg/40 shadow-xs'
                      : 'border-border/60 bg-card'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                    <span>
                      <strong className="font-semibold text-foreground">{t.speaker}</strong> ·{' '}
                      <code className="font-mono">[{t.t_start}]</code>
                    </span>
                    <span className="font-mono">turn #{t.turn}</span>
                  </div>
                  <p className="mt-1 text-foreground break-words">{body}</p>
                </div>
              )
            })}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

// ─── Login (P6b — Split-screen Hero + 1-click Demo Login) ──────────────────

function LoginScreen({ onDone }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState('login') // login | register
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function runAuth(targetEmail, targetPassword, targetMode = mode) {
    setBusy(true)
    setError(null)
    try {
      const user =
        targetMode === 'login'
          ? await login(targetEmail.trim(), targetPassword)
          : await register(targetEmail.trim(), targetPassword)
      onDone(user)
    } catch (err) {
      setError(
        err.status === 401
          ? 'Email hoặc mật khẩu sai.'
          : err.status === 409
            ? 'Email đã tồn tại — chuyển sang Đăng nhập.'
            : `Lỗi ${err.status ?? '?'}: ${JSON.stringify(err.body)}`,
      )
    } finally {
      setBusy(false)
    }
  }

  function submit(e) {
    e.preventDefault()
    runAuth(email, password, mode)
  }

  function loginDemoAccount() {
    setMode('login')
    setEmail('demo@meet2note.app')
    setPassword('Demo1234')
    runAuth('demo@meet2note.app', 'Demo1234', 'login')
  }

  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-[1.15fr_0.85fr]">
      {/* Cột trái: Hero giới thiệu triết lý sản phẩm */}
      <div
        className="hidden flex-col justify-between p-10 lg:flex"
        style={{
          backgroundColor: 'var(--color-hero-bg)',
          color: 'var(--color-hero-fg)',
        }}
      >
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/15 px-3 py-1 text-xs font-semibold text-primary-foreground">
            <Sparkles className="size-3.5" />
            <span>AI Meeting State Engine · Mission 3 Ready</span>
          </div>
          <h1 className="mt-6 font-heading text-4xl font-bold leading-tight">
            Biến cuộc họp 60 phút thành quyết định &amp; công việc có bằng chứng.
          </h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed" style={{ color: 'var(--color-hero-muted)' }}>
            Không tóm tắt bay bổng — <strong className="text-white">meet2note</strong> trích xuất{' '}
            <strong className="text-white">trạng thái cuối cùng</strong> qua 8 quy tắc cứng R1–R8
            và 4 cổng kiểm chứng deterministic (M3).
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            <div
              className="rounded-xl border p-4"
              style={{
                backgroundColor: 'var(--color-hero-card)',
                borderColor: 'var(--color-hero-border)',
              }}
            >
              <div className="flex items-center gap-2 font-heading text-sm font-semibold">
                <History className="size-4 text-primary-foreground" />
                <span>Bắt trọn đảo chiều A → B</span>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed" style={{ color: 'var(--color-hero-muted)' }}>
                Đề xuất đầu họp bị lật ở phút cuối được chuyển thành <code>discarded</code>, giữ
                nguyên lịch sử <code>supersedes</code> và phản đối.
              </p>
            </div>
            <div
              className="rounded-xl border p-4"
              style={{
                backgroundColor: 'var(--color-hero-card)',
                borderColor: 'var(--color-hero-border)',
              }}
            >
              <div className="flex items-center gap-2 font-heading text-sm font-semibold">
                <ShieldCheck className="size-4 text-primary-foreground" />
                <span>Chống chốt giả &amp; bịa hạn (M3)</span>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed" style={{ color: 'var(--color-hero-muted)' }}>
                Cổng M3-A..D tự hạ cấp câu nói đùa/rút lại, chặn từ khóa mơ hồ (hedge), và lấy
                deadline sửa lần cuối kèm vết.
              </p>
            </div>
          </div>
        </div>

        {/* Minh hoạ trực quan luồng State */}
        <div
          className="rounded-xl border p-4 text-xs"
          style={{
            backgroundColor: 'var(--color-hero-card)',
            borderColor: 'var(--color-hero-border)',
          }}
        >
          <div className="flex items-center justify-between text-[11px] uppercase tracking-wider" style={{ color: 'var(--color-hero-muted)' }}>
            <span>Triết lý vận hành</span>
            <span>LLM đề xuất · Code kiểm chứng · Con người chốt</span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 font-mono text-xs">
            <span className="rounded bg-conf-red-bg/20 px-2 py-1 text-red-300 line-through">
              D0: Phương án A (discarded)
            </span>
            <ArrowRight className="size-4" />
            <span className="rounded bg-conf-green-bg/20 px-2.5 py-1 font-semibold text-emerald-300">
              ✓ D1: Chốt phương án B (final · 0.90)
            </span>
            <ArrowRight className="size-4" />
            <span className="rounded bg-primary/30 px-2.5 py-1 text-white">
              minutes.md + tasks_jira.csv
            </span>
          </div>
        </div>
      </div>

      {/* Cột phải: Form đăng nhập + 1-click Demo */}
      <div className="flex items-center justify-center p-6">
        <Card className="w-full max-w-md border-border/80 p-7 shadow-card">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-heading text-2xl font-bold text-foreground">meet2note</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {mode === 'login'
                  ? 'Đăng nhập vào không gian review biên bản họp.'
                  : 'Tạo tài khoản mới (mật khẩu tối thiểu 8 ký tự).'}
              </p>
            </div>
            <Badge variant="secondary" className="font-mono text-xs">
              v0.4 · M3
            </Badge>
          </div>

          <div className="mt-5 rounded-xl border border-primary/25 bg-accent/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs">
                <p className="font-semibold text-foreground">Trải nghiệm nhanh (Khuyên dùng)</p>
                <p className="text-muted-foreground">
                  Có sẵn dữ liệu mẫu <code>tc1..tc5</code> để duyệt thử ngay
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                onClick={loginDemoAccount}
                disabled={busy}
                className="shrink-0"
              >
                <Zap className="size-3.5" /> Vào tài khoản Demo
              </Button>
            </div>
          </div>

          <div className="my-4 flex items-center gap-3 text-xs text-muted-foreground">
            <Separator className="flex-1" />
            <span>hoặc dùng tài khoản riêng</span>
            <Separator className="flex-1" />
          </div>

          <form onSubmit={submit} className="flex flex-col gap-3.5">
            <div>
              <Label htmlFor="login-email">Email</Label>
              <Input
                id="login-email"
                type="email"
                autoComplete="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="login-password">Mật khẩu</Label>
              <Input
                id="login-password"
                type="password"
                placeholder="••••••••"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="mt-1"
              />
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" disabled={busy} className="mt-1 w-full">
              {busy ? 'Đang xử lý…' : mode === 'login' ? 'Đăng nhập' : 'Đăng ký tài khoản'}
            </Button>
            <button
              type="button"
              className="mt-1 text-center text-xs font-medium text-primary underline-offset-2 hover:underline"
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login')
                setError(null)
              }}
            >
              {mode === 'login' ? 'Chưa có tài khoản? Đăng ký mới' : 'Đã có tài khoản? Quay lại đăng nhập'}
            </button>
          </form>
        </Card>
      </div>
    </div>
  )
}

// ─── Main App ────────────────────────────────────────────────────────────────

export default function App() {
  const [meetingId, setMeetingId] = useState('')
  const [meetingInput, setMeetingInput] = useState('')
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('all')
  const [participantFilter, setParticipantFilter] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
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
  const searchInputRef = useRef(null)
  // Upload form.
  const [upFile, setUpFile] = useState(null)
  const [upId, setUpId] = useState('')
  const [upTitle, setUpTitle] = useState('')
  const [upDate, setUpDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [upParts, setUpParts] = useState('Lan (PM)\nNam (BA)\nHà (Dev)')
  const [upMsg, setUpMsg] = useState(null)
  const [upBusy, setUpBusy] = useState(false)
  // Auth (P6b): user null → hiện LoginScreen, không load meeting.
  const [user, setUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  // Danh sách meeting của mình — bấm xem lại, khỏi nhớ id.
  const [meetings, setMeetings] = useState([])
  // Keyboard focus.
  const [focusedId, setFocusedId] = useState(null)
  const [hoveredId, setHoveredId] = useState(null)
  const cardRefs = useRef({})
  const onAgreeRef = useRef(null)
  const onRemoveRef = useRef(null)
  const showEvidenceRef = useRef(null)

  const allIds = useMemo(() => new Set((state?.items ?? []).map((i) => i.id)), [state])

  const visibleItems = useMemo(() => {
    return (state?.items ?? [])
      .filter((it) => !removedIds.has(it.id))
      .filter((it) => !(it.type === 'decision' && it.status === 'discarded'))
      .map((it) => (editedItems[it.id] ? { ...it, ...editedItems[it.id] } : it))
  }, [state, removedIds, editedItems])

  // Lưu trạng thái đã xác nhận vào sessionStorage để đổi qua lại giữa các meeting không bị mất
  useEffect(() => {
    if (meetingId) {
      saveConfirmedSession(meetingId, confirmedIds)
    }
  }, [meetingId, confirmedIds])

  async function load(target, opts = {}) {
    const { keepOverlay = false } = opts
    if (!target || !target.trim()) return
    const cleanTarget = target.trim()
    setBusy(true)
    setLoadError(null)
    setExportFiles(null)
    setExportError(null)
    if (!keepOverlay) {
      setConfirmedIds(loadConfirmedSession(cleanTarget))
      setRemovedIds(new Set())
      setEditedItems({})
      setFocusedId(null)
      setParticipantFilter(null)
      setSearchQuery('')
      setDrawer(null)
    }
    try {
      const data = await getReview(cleanTarget)
      setState(data)
      setMeetingId(cleanTarget)
    } catch (e) {
      if (e.status === 401) {
        setUser(null)
        setState(null)
        return
      }
      setLoadError(
        e.status === 404
          ? `Không tìm thấy meeting "${cleanTarget}" (404). Kiểm tra lại ID hoặc chọn từ danh sách ①.`
          : `GET /api/v1/review → ${e.status ?? '?'}: ${JSON.stringify(e.body)}`,
      )
      setState(null)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    getMe()
      .then((u) => {
        if (!cancelled) setUser(u)
      })
      .catch(() => {
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setAuthChecked(true)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (authChecked && user) {
      setMeetingInput('')
      loadMeetings()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authChecked, user])

  async function loadMeetings() {
    try {
      const data = await listMeetings()
      setMeetings(data.meetings ?? [])
    } catch {
      setMeetings([])
    }
  }

  async function sendPut(itemsToSend, changes) {
    setBusy(true)
    try {
      const resp = await putReview(meetingId, itemsToSend, changes)
      await load(meetingId, { keepOverlay: true })
      loadMeetings()
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
    sendPut(currentItemsForPut(), changes)
      .then(() => {
        advanceFocus(item.id)
      })
      .catch(() => {
        setConfirmedIds((s) => {
          const n = new Set(s)
          n.delete(item.id)
          return n
        })
      })
  }

  // Duyệt nhanh toàn bộ thẻ Xanh chưa xác nhận trong 1 click (đồng bộ PUT changes)
  function onBatchAgreeGreen() {
    const unconfirmedGreens = visibleItems.filter(
      (it) => levelOf(it.confidence) === 'green' && !confirmedIds.has(it.id),
    )
    if (unconfirmedGreens.length === 0) return
    const changes = unconfirmedGreens.map((it) => ({
      item_id: it.id,
      action: 'agree',
      old: null,
      new: null,
    }))
    setConfirmedIds((s) => {
      const n = new Set(s)
      unconfirmedGreens.forEach((it) => n.add(it.id))
      return n
    })
    sendPut(currentItemsForPut(), changes)
      .then(() => {
        toast.success(`Đã xác nhận nhanh ${unconfirmedGreens.length} thẻ xanh`)
      })
      .catch(() => {
        toast.error('Lỗi khi xác nhận hàng loạt')
      })
  }

  function advanceFocus(fromId, excludeId = null) {
    const ids = flatVisibleIds.filter((id) => id !== excludeId)
    if (ids.length === 0) {
      setFocusedId(null)
      return
    }
    let idx = ids.indexOf(fromId)
    if (idx === -1) idx = 0
    else if (!excludeId) idx = Math.min(idx + 1, ids.length - 1)
    else idx = Math.min(idx, ids.length - 1)
    focusCard(ids[idx])
  }

  function onEdit(item, draft) {
    const old = {}
    const nw = {}
    if (item.type === 'task') {
      if ((item.what ?? '') !== draft.content) {
        old.what = item.what
        nw.what = draft.content
      }
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
      nw.link_to_decision = draft.link_to_decision || null
    }
    if (Object.keys(nw).length === 0) return
    setEditedItems((m) => ({ ...m, [item.id]: nw }))
    setConfirmedIds((s) => new Set(s).add(item.id))
    sendPut(
      currentItemsForPut().map((it) => (it.id === item.id ? { ...it, ...nw } : it)),
      [{ item_id: item.id, action: 'edit', old, new: nw }],
    )
      .then(() => {
        toast.success(`Đã cập nhật ${item.id}`)
      })
      .catch(() => {
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
    )
      .then(() => {
        advanceFocus(item.id, item.id)
      })
      .catch(() => {
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
  const unconfirmedGreenCount = useMemo(
    () => visibleItems.filter((it) => levelOf(it.confidence) === 'green' && !confirmedIds.has(it.id)).length,
    [visibleItems, confirmedIds],
  )
  const gateOpen = redItems.length === 0 && visibleItems.length > 0

  async function doExport() {
    setExportError(null)
    setExportFiles(null)
    try {
      // Nếu chưa confirm thẻ nào mà gate đã mở (0 thẻ đỏ), tự động ghi nhận confirm thẻ đầu tiên
      // để host không bị lỗi 400 "Hãy xác nhận ít nhất 1 thẻ" khi bấm Export ngay.
      if (confirmedIds.size === 0 && visibleItems.length > 0) {
        const firstItem = visibleItems[0]
        setConfirmedIds((s) => new Set(s).add(firstItem.id))
        await putReview(meetingId, currentItemsForPut(), [
          { item_id: firstItem.id, action: 'agree', old: null, new: null },
        ])
      }
      const resp = await postExport(meetingId)
      setExportFiles(resp.files || [])
      toast.success('Đã xuất biên bản minutes.md và tasks_jira.csv!')
    } catch (e) {
      if (e.status === 403) {
        const reds = e.body?.red_items ?? []
        setExportError(`Còn thẻ đỏ chưa xử lý: ${reds.join(', ')}. Xử lý hết trước khi export.`)
      } else if (e.status === 400) {
        setExportError(
          e.body?.detail ?? 'Hãy xác nhận ít nhất 1 thẻ trước khi export.',
        )
      } else {
        setExportError(`${e.status ?? '?'}: ${e.body?.detail ?? JSON.stringify(e.body)}`)
      }
    }
  }

  const [downloading, setDownloading] = useState(null)

  async function doDownload(name) {
    setDownloading(name)
    try {
      await downloadExport(meetingId, name)
    } catch (e) {
      toast.error(`Tải ${name} lỗi (${e.status ?? '?'}): ${e.body?.detail ?? ''}`)
    } finally {
      setDownloading(null)
    }
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
          : `Lỗi tải transcript: ${e.status ?? '?'}`,
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
      loadMeetings()
    } catch (e) {
      if (e.status === 503) {
        setUpMsg('LLM chưa sẵn sàng (503): bật Ollama rồi thử lại.')
      } else if (e.status === 409) {
        setUpMsg(
          'Meeting id này đã có người khác dùng. Đổi "Meeting id" khác (ví dụ thêm tên bạn) rồi upload lại.',
        )
      } else {
        setUpMsg(`Lỗi (${e.status ?? '?'}): ${e.body?.detail ?? JSON.stringify(e.body)}`)
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

  // Map ngược: mỗi Decision ID có những Task nào liên kết tới
  const linkedTasksByDecision = useMemo(() => {
    const map = {}
    visibleItems.forEach((it) => {
      if (it.type === 'task' && it.link_to_decision) {
        if (!map[it.link_to_decision]) map[it.link_to_decision] = []
        map[it.link_to_decision].push(it)
      }
    })
    return map
  }, [visibleItems])

  const finalDecisionIds = useMemo(
    () =>
      visibleItems
        .filter((it) => it.type === 'decision' && it.status === 'final')
        .map((it) => it.id),
    [visibleItems],
  )

  const partitioned = useMemo(() => {
    const passConf =
      filter === 'all' ? () => true :
      filter === 'red' ? (conf) => levelOf(conf) === 'red' :
      filter === 'yellow' ? (conf) => levelOf(conf) === 'yellow' :
        (conf) => levelOf(conf) === 'green'

    const items = visibleItems.filter(
      (it) =>
        passConf(it.confidence) &&
        itemInvolvesParticipant(it, participantFilter) &&
        itemMatchesQuery(it, searchQuery),
    )
    const risk = (it) => ({ red: 0, yellow: 1, green: 2 })[levelOf(it.confidence)]
    const byRisk = (arr) =>
      [...arr].sort((a, b) => {
        const r = risk(a) - risk(b)
        if (r !== 0) return r
        const ac = confirmedIds.has(a.id) ? 1 : 0
        const bc = confirmedIds.has(b.id) ? 1 : 0
        return ac - bc
      })
    const finalDecisions = byRisk(items.filter((it) => it.type === 'decision' && it.status === 'final'))
    const discardedByFinal = {}
    finalDecisions.forEach((fd) => {
      discardedByFinal[fd.id] = (state?.items ?? []).filter(
        (it) => it.type === 'decision' && (fd.supersedes || []).includes(it.id) && !removedIds.has(it.id),
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
  }, [visibleItems, filter, participantFilter, searchQuery, confirmedIds, state, removedIds])

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
      cardRefs.current[id]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
  }, [])

  // Nhảy tới 1 thẻ bất kỳ (tự động gỡ bộ lọc nếu thẻ đang bị ẩn do lọc)
  const jumpToItem = useCallback(
    (targetId) => {
      if (!targetId) return
      if (!flatVisibleIds.includes(targetId)) {
        setFilter('all')
        setParticipantFilter(null)
        setSearchQuery('')
      }
      setTimeout(() => focusCard(targetId), 50)
    },
    [flatVisibleIds, focusCard],
  )

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
      if (e.key === '/') {
        e.preventDefault()
        searchInputRef.current?.focus?.()
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
      participants: state?.meeting?.participants ?? [],
      finalDecisionIds,
      linkedTasksByDecision,
      focused: focusedId === it.id,
      hovered: hoveredId === it.id,
      onHover: setHoveredId,
      confirmed: confirmedIds.has(it.id),
      cardRef: (el) => {
        cardRefs.current[it.id] = el
      },
      onAgree,
      onEdit,
      onRemove,
      onShowEvidence: showEvidence,
      onJumpToItem: jumpToItem,
    }
  }

  if (!authChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <div className="flex w-full max-w-sm flex-col gap-2" aria-label="đang tải">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </div>
    )
  }

  if (!user) {
    return <LoginScreen onDone={(u) => setUser(u)} />
  }

  async function doLogout() {
    await logout()
    setUser(null)
    setState(null)
  }

  const progressPct =
    visibleItems.length === 0 ? 0 : Math.round((confirmedIds.size / visibleItems.length) * 100)

  return (
    <div className="min-h-screen bg-background font-sans text-sm text-foreground">
      <Toaster />
      <div className="grid min-h-screen xl:grid-cols-[276px_1fr]">
        {/* ─── Sidebar ──────────────────────────────────────────── */}
        <aside className="flex min-w-0 flex-col gap-4 overflow-x-hidden border-b border-border bg-card p-4 xl:h-screen xl:overflow-y-auto xl:border-r xl:border-b-0">
          {/* Brand Header */}
          <div className="rounded-xl border border-border/80 bg-muted/40 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="flex size-7 items-center justify-center rounded-lg bg-primary text-xs font-bold text-primary-foreground">
                  M2N
                </div>
                <div>
                  <h1 className="font-heading text-base font-bold leading-none">meet2note</h1>
                  <span className="text-[11px] text-muted-foreground">State Review Engine</span>
                </div>
              </div>
              <button
                type="button"
                onClick={doLogout}
                title="Đăng xuất"
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
              >
                <LogOut className="size-3.5" /> Thoát
              </button>
            </div>
            <p className="mt-2 truncate text-xs text-muted-foreground" title={user.email}>
              👤 {user.email}
            </p>
          </div>

          {/* ① Meeting Selector */}
          <Collapsible defaultOpen className="rounded-xl border border-border/70 bg-background/50 p-3">
            <CollapsibleTrigger className="flex w-full items-center justify-between text-xs font-bold uppercase tracking-wider text-muted-foreground">
              <span>① Cuộc họp của tôi ({meetings.length})</span>
              <ChevronDown className="size-4" />
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2.5 flex flex-col gap-2">
              {meetings.length > 0 && (
                <div
                  className="flex max-h-60 flex-col gap-1.5 overflow-y-auto pr-0.5"
                  role="list"
                  aria-label="Meeting của tôi"
                >
                  {meetings.map((m) => {
                    const active = m.id === meetingId
                    const badges = active
                      ? { red: counts.red, yellow: counts.yellow, green: counts.green }
                      : (m.badges ?? {})
                    return (
                      <button
                        key={m.id}
                        type="button"
                        role="listitem"
                        aria-current={active ? 'true' : undefined}
                        onClick={() => {
                          setMeetingInput(m.id)
                          load(m.id)
                        }}
                        className={`flex min-w-0 flex-col rounded-lg border p-2 text-left transition-all hover:border-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ${
                          active
                            ? 'border-primary bg-accent shadow-xs'
                            : 'border-border bg-card hover:bg-muted/40'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1">
                          <span className="truncate text-xs font-semibold text-foreground">
                            {m.title || m.id}
                          </span>
                          <code className="shrink-0 rounded bg-muted px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
                            {m.id}
                          </code>
                        </div>
                        <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                          <span>{m.date || m.id}</span>
                          <span className="flex items-center gap-1.5 font-medium">
                            {(badges.red ?? 0) > 0 && <span>🔴{badges.red}</span>}
                            {(badges.yellow ?? 0) > 0 && <span>🟡{badges.yellow}</span>}
                            {(badges.green ?? 0) > 0 && <span>🟢{badges.green}</span>}
                          </span>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
              <div className="pt-1">
                <Label htmlFor="meeting-id" className="text-xs">
                  Hoặc tải theo Meeting ID
                </Label>
                <div className="mt-1 flex gap-1.5">
                  <Input
                    id="meeting-id"
                    placeholder="vd: tc2, tc6..."
                    value={meetingInput}
                    onChange={(e) => setMeetingInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') load(meetingInput)
                    }}
                    data-testid="meeting-input"
                    className="h-8 text-xs"
                  />
                  <Button
                    size="sm"
                    onClick={() => load(meetingInput)}
                    disabled={busy}
                    className="h-8 shrink-0"
                  >
                    {busy ? '…' : 'Load'}
                  </Button>
                </div>
              </div>
              {loadError && (
                <Alert variant="destructive">
                  <AlertDescription className="break-words text-xs">{loadError}</AlertDescription>
                </Alert>
              )}
            </CollapsibleContent>
          </Collapsible>

          {/* ② Review Progress & Export Gate */}
          {state && (
            <Collapsible defaultOpen className="rounded-xl border border-border/70 bg-background/50 p-3">
              <CollapsibleTrigger className="flex w-full items-center justify-between text-xs font-bold uppercase tracking-wider text-muted-foreground">
                <span>② Tiến độ &amp; Xuất biên bản</span>
                <ChevronDown className="size-4" />
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2.5 flex flex-col gap-3">
                <div>
                  <div className="flex items-center justify-between text-xs">
                    <span aria-live="polite" className="font-medium">
                      Đã xác nhận {confirmedIds.size}/{visibleItems.length} mục
                    </span>
                    <span className="font-mono text-xs font-semibold text-primary">
                      {progressPct}%
                    </span>
                  </div>
                  <Progress value={progressPct} className="mt-1.5" />
                </div>

                <ToggleGroup
                  type="single"
                  value={filter}
                  onValueChange={(v) => v && setFilter(v)}
                  className="grid grid-cols-4 gap-1"
                >
                  <ToggleGroupItem value="all" className="text-xs px-1.5">
                    Tất cả {counts.all}
                  </ToggleGroupItem>
                  <ToggleGroupItem value="red" className="text-xs px-1.5">
                    🔴 {counts.red}
                  </ToggleGroupItem>
                  <ToggleGroupItem value="yellow" className="text-xs px-1.5">
                    🟡 {counts.yellow}
                  </ToggleGroupItem>
                  <ToggleGroupItem value="green" className="text-xs px-1.5">
                    🟢 {counts.green}
                  </ToggleGroupItem>
                </ToggleGroup>

                {gateOpen ? (
                  <Alert variant="ok" className="py-2">
                    <AlertTitle className="text-xs">✓ Đủ điều kiện xuất biên bản (0 thẻ đỏ)</AlertTitle>
                  </Alert>
                ) : (
                  <Alert variant="destructive" className="py-2">
                    <AlertTitle className="text-xs">
                      Còn {redItems.length} thẻ đỏ khoá Export (Gate R6)
                    </AlertTitle>
                    <AlertDescription className="text-xs">
                      Cần duyệt/sửa/loại: {redItems.map((it) => it.id).join(', ')}
                    </AlertDescription>
                  </Alert>
                )}

                <Button
                  onClick={doExport}
                  disabled={!gateOpen || busy}
                  data-testid="export-btn"
                  className="w-full"
                >
                  <Download className="size-4" />
                  {gateOpen ? 'Export minutes.md + CSV' : `Khoá (${redItems.length} đỏ)`}
                </Button>

                {exportFiles && exportFiles.length > 0 && (
                  <Alert variant="ok">
                    <AlertTitle className="text-xs">Export thành công — Tải về máy:</AlertTitle>
                    <AlertDescription>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {exportFiles.map((f) => {
                          const name = f.split('/').pop()
                          return (
                            <Button
                              key={f}
                              size="sm"
                              variant="outline"
                              disabled={downloading === name}
                              onClick={() => doDownload(name)}
                              className="h-7 text-xs bg-card"
                            >
                              <Download className="size-3" />
                              {downloading === name ? 'Đang tải…' : name}
                            </Button>
                          )
                        })}
                      </div>
                    </AlertDescription>
                  </Alert>
                )}

                {exportError && (
                  <Alert variant="destructive">
                    <AlertDescription className="text-xs">{exportError}</AlertDescription>
                  </Alert>
                )}

                {Array.isArray(state?.known_limitations) && state.known_limitations.length > 0 && (
                  <Collapsible>
                    <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md bg-muted px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
                      <span>⚠ Vết kiểm chứng &amp; giới hạn ({state.known_limitations.length})</span>
                      <ChevronDown className="size-3.5" />
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <ul className="mt-1.5 flex max-h-44 flex-col gap-1 overflow-y-auto rounded-md border border-border bg-card p-2 text-[11px] text-muted-foreground">
                        {state.known_limitations.map((lim, i) => (
                          <li key={i} className="border-b border-border/40 pb-1 last:border-0">
                            • {lim}
                          </li>
                        ))}
                      </ul>
                    </CollapsibleContent>
                  </Collapsible>
                )}
              </CollapsibleContent>
            </Collapsible>
          )}

          {/* ③ Upload Transcript */}
          <Collapsible
            defaultOpen={!state}
            className="rounded-xl border border-border/70 bg-background/50 p-3"
          >
            <CollapsibleTrigger className="flex w-full items-center justify-between text-xs font-bold uppercase tracking-wider text-muted-foreground">
              <span>③ Upload Transcript mới</span>
              <ChevronDown className="size-4" />
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2.5 flex flex-col gap-2">
              <Label htmlFor="up-file" className="text-xs">
                File transcript (.txt / .srt / .docx)
              </Label>
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
                className="flex cursor-pointer flex-col items-center gap-1 rounded-lg border-2 border-dashed border-primary/40 bg-primary/5 px-3 py-3.5 text-center text-xs text-foreground transition-colors hover:border-primary hover:bg-primary/10"
              >
                <Upload className="size-4 text-primary" />
                {upFile ? (
                  <>
                    <span className="font-semibold break-words">{upFile.name}</span>
                    <span className="text-[11px] text-muted-foreground">
                      {(upFile.size / 1024).toFixed(1)} KB — bấm để đổi file
                    </span>
                  </>
                ) : (
                  <>
                    <span className="font-semibold">Bấm để chọn file cuộc họp</span>
                    <span className="text-[11px] text-muted-foreground">Hỗ trợ .txt · .srt · .docx</span>
                  </>
                )}
              </Label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label htmlFor="up-id" className="text-xs">
                    Meeting ID
                  </Label>
                  <Input
                    id="up-id"
                    placeholder="tự sinh nếu trống"
                    value={upId}
                    onChange={(e) => setUpId(e.target.value)}
                    className="mt-0.5 h-8 text-xs"
                  />
                </div>
                <div>
                  <Label htmlFor="up-date" className="text-xs">
                    Ngày họp (R2)
                  </Label>
                  <Input
                    id="up-date"
                    type="date"
                    value={upDate}
                    onChange={(e) => setUpDate(e.target.value)}
                    className="mt-0.5 h-8 text-xs"
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="up-title" className="text-xs">
                  Tiêu đề cuộc họp
                </Label>
                <Input
                  id="up-title"
                  placeholder="vd: Họp chốt phương án thanh toán"
                  value={upTitle}
                  onChange={(e) => setUpTitle(e.target.value)}
                  className="mt-0.5 h-8 text-xs"
                />
              </div>
              <div>
                <Label htmlFor="up-parts" className="text-xs">
                  Người tham gia (mỗi dòng: Tên (vai trò))
                </Label>
                <Textarea
                  id="up-parts"
                  rows={3}
                  value={upParts}
                  onChange={(e) => setUpParts(e.target.value)}
                  className="mt-0.5 text-xs"
                />
              </div>
              <Button onClick={doUpload} disabled={upBusy} data-testid="upload-submit" className="mt-1">
                <Upload className="size-4" />
                {upBusy ? 'Đang chạy pipeline AI…' : 'Upload + Chạy Pipeline'}
              </Button>
              {upMsg && <p className="text-xs text-muted-foreground break-words">{upMsg}</p>}
            </CollapsibleContent>
          </Collapsible>

          {/* Phím tắt */}
          <div className="mt-auto rounded-lg border border-border/60 bg-muted/30 p-2.5 text-[11px] text-muted-foreground">
            <div className="flex items-center gap-1 font-semibold text-foreground">
              <Keyboard className="size-3.5" /> Phím tắt tốc độ (Review 2 phút)
            </div>
            <p className="mt-1 leading-relaxed">
              <code>j/k</code> di chuyển · <code>a</code> đồng ý · <code>e</code> sửa ·{' '}
              <code>x</code> loại · <code>Enter</code> mở câu gốc · <code>/</code> tìm kiếm ·{' '}
              <code>1–4</code> lọc màu
            </p>
          </div>
        </aside>

        {/* ─── Main Workspace ───────────────────────────────────── */}
        <main className="min-w-0 p-4 lg:p-5 xl:h-screen xl:overflow-y-auto">
          {!state && !busy && (
            <Card className="mx-auto mt-12 max-w-xl border-dashed p-8 text-center shadow-card">
              <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <FileText className="size-6" />
              </div>
              <h2 className="mt-4 font-heading text-xl font-bold">
                Chọn cuộc họp hoặc Upload transcript để bắt đầu
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Bấm vào một cuộc họp trong danh sách <strong>① Cuộc họp của tôi</strong> bên trái,
                hoặc tải lên file transcript mới ở mục <strong>③ Upload</strong>.
              </p>
              {meetings.length > 0 && (
                <div className="mt-5 flex flex-wrap justify-center gap-2">
                  {meetings.slice(0, 5).map((m) => (
                    <Button
                      key={m.id}
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setMeetingInput(m.id)
                        load(m.id)
                      }}
                    >
                      Mở {m.title || m.id}
                    </Button>
                  ))}
                </div>
              )}
            </Card>
          )}

          {busy && !state && (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex flex-col gap-2 rounded-xl border bg-card p-4">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-20 w-full" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ))}
            </div>
          )}

          {state && (
            <>
              {/* Sticky Top Command Bar — Đồng bộ trạng thái + Thao tác nhanh 2 phút */}
              <header className="sticky top-0 z-20 -mx-4 -mt-4 mb-4 border-b border-border bg-card/95 px-4 py-3 backdrop-blur lg:-mx-5 lg:-mt-5 lg:px-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-heading text-lg font-bold text-foreground truncate">
                        {state.meeting?.title}
                      </h2>
                      <Badge variant="outline" className="font-mono text-xs">
                        {state.meeting?.date}
                      </Badge>
                      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                        id: {state.meeting?.id} · v{state.meeting?.pipeline_version}
                      </code>
                    </div>
                  </div>

                  {/* Cụm nút hành động thông minh (Smart Review Actions) */}
                  <div className="flex flex-wrap items-center gap-2">
                    {redItems.length > 0 && (
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => jumpToItem(redItems[0].id)}
                        title="Nhảy tới thẻ đỏ đầu tiên cần xử lý"
                      >
                        <Target className="size-3.5" /> Xử lý thẻ Đỏ tiếp theo ({redItems.length})
                      </Button>
                    )}
                    {unconfirmedGreenCount > 0 && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={onBatchAgreeGreen}
                        disabled={busy}
                        className="border-conf-green/50 bg-conf-green-bg/50 text-conf-green hover:bg-conf-green-bg"
                        title="Xác nhận đồng loạt tất cả thẻ xanh có độ tin cậy cao (≥ 0.75)"
                      >
                        <CheckCheck className="size-3.5" /> Duyệt nhanh {unconfirmedGreenCount} thẻ Xanh
                      </Button>
                    )}
                  </div>
                </div>

                {/* Thanh tìm kiếm + Lọc theo Người tham gia */}
                <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground mr-1">
                      <UserCheck className="size-3.5" /> Người tham gia:
                    </span>
                    <button
                      type="button"
                      onClick={() => setParticipantFilter(null)}
                      className={`rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${
                        participantFilter === null
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-background text-muted-foreground hover:border-primary'
                      }`}
                    >
                      Tất cả
                    </button>
                    {(state.meeting?.participants ?? []).map((p) => {
                      const active = participantFilter === p.name
                      return (
                        <button
                          key={p.name}
                          type="button"
                          onClick={() => setParticipantFilter(active ? null : p.name)}
                          title={`Lọc các mục liên quan tới ${p.name} (${p.role})`}
                          className={`rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${
                            active
                              ? 'border-primary bg-primary text-primary-foreground'
                              : 'border-border bg-background text-foreground hover:border-primary'
                          }`}
                        >
                          {p.name} <span className="opacity-75">· {p.role}</span>
                        </button>
                      )
                    })}
                  </div>

                  <div className="relative flex items-center min-w-[220px]">
                    <Search className="pointer-events-none absolute left-2.5 size-3.5 text-muted-foreground" />
                    <Input
                      ref={searchInputRef}
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Tìm nội dung, người nói, ID... (phím /)"
                      className="h-8 pl-8 pr-7 text-xs bg-background"
                    />
                    {searchQuery && (
                      <button
                        type="button"
                        onClick={() => setSearchQuery('')}
                        className="absolute right-2 text-muted-foreground hover:text-foreground"
                        title="Xoá tìm kiếm"
                      >
                        <X className="size-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              </header>

              {/* Banner cảnh báo R3 (no_decision) */}
              {state.no_decision && (
                <Alert variant="warn" className="mb-3">
                  <AlertTriangle className="size-4" />
                  <AlertTitle>
                    Họp không chốt quyết định cuối nào (no_decision=true) — kiểm tra cột Chưa chốt (Open Issue)
                  </AlertTitle>
                </Alert>
              )}

              {/* Tóm tắt nhanh (Meeting Brief) có gắn Ref ID bấm nhảy tới thẻ */}
              {state.brief && (
                <Alert variant="info" className="mb-4 border-primary/25 shadow-xs">
                  <Sparkles className="size-4 text-primary" />
                  <AlertTitle className="font-heading text-sm">
                    Tóm tắt trọng tâm: {state.brief.problem}
                  </AlertTitle>
                  {(state.brief.outcomes ?? []).length > 0 && (
                    <AlertDescription>
                      <ul className="mt-1.5 flex flex-col gap-1.5 text-xs">
                        {(state.brief.outcomes ?? []).map((o, i) => (
                          <li key={i} className="flex flex-wrap items-center gap-1.5">
                            <span>• {o.text}</span>
                            {(o.ref_ids ?? []).map((r) => (
                              <button
                                key={r}
                                type="button"
                                onClick={() => jumpToItem(r)}
                                title={`Nhảy tới thẻ ${r}`}
                                className="inline-flex items-center gap-0.5 rounded-md border border-primary/40 bg-card px-1.5 py-0.5 font-mono text-[11px] font-semibold text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
                              >
                                <Link2 className="size-2.5" /> {r}
                              </button>
                            ))}
                          </li>
                        ))}
                      </ul>
                    </AlertDescription>
                  )}
                </Alert>
              )}

              {/* Đang bật bộ lọc phụ → hiện thanh nhắc xóa bộ lọc */}
              {(filter !== 'all' || participantFilter || searchQuery) && (
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-primary/30 bg-accent/60 px-3 py-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    <Filter className="size-3.5 text-primary" />
                    <span>
                      Đang hiển thị <strong>{flatVisibleIds.length}</strong>/{visibleItems.length} mục theo bộ lọc
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setFilter('all')
                      setParticipantFilter(null)
                      setSearchQuery('')
                    }}
                    className="font-semibold text-primary hover:underline"
                  >
                    Xoá tất cả bộ lọc
                  </button>
                </div>
              )}

              {/* 4 Cột Kanban */}
              <div className="grid gap-3.5 md:grid-cols-2 xl:grid-cols-4 items-start">
                <Column
                  title="✅ Quyết định"
                  subtitle="Trạng thái chốt cuối & lịch sử A→B"
                  items={partitioned.finalDecisions}
                  emptyHint={filter !== 'all' || participantFilter || searchQuery ? 'thử tắt bộ lọc' : ''}
                  render={(d) => (
                    <div key={d.id}>
                      <ItemCard
                        {...cardProps(d)}
                        cardRef={(el) => {
                          cardRefs.current[d.id] = el
                        }}
                      />
                      <DiscardedList
                        items={partitioned.discardedByFinal[d.id] ?? []}
                        onShowEvidence={showEvidence}
                      />
                    </div>
                  )}
                />
                <Column
                  title="📌 Công việc"
                  subtitle="Ai làm · Hạn chót · Theo quyết định nào"
                  items={partitioned.tasks}
                  emptyHint={filter !== 'all' || participantFilter || searchQuery ? 'thử tắt bộ lọc' : ''}
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
                  subtitle="Rủi ro chặn tiến độ & vấn đề treo"
                  items={[...partitioned.blockers, ...partitioned.openIssues]}
                  emptyHint={filter !== 'all' || participantFilter || searchQuery ? 'thử tắt bộ lọc' : ''}
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
                  title="📋 Yêu cầu & Tri thức"
                  subtitle="Phản hồi KH & quy ước dài hạn (M3-D)"
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
        key={`${drawer?.source ?? ''}-${drawer?.targetTurn ?? ''}`}
        view={drawer}
        drawerError={drawerError}
        onClose={closeDrawer}
      />
    </div>
  )
}
