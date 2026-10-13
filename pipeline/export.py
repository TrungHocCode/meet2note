"""
pipeline/export.py — Sinh file minutes.md + tasks_jira.csv từ confirmed state (P3).

Triết lý (AGENTS.md §1, R6, R7):
- LLM đề xuất → code kiểm chứng → con người chốt → export từ bản đã confirmed.
- Đọc `confirmed_state.json` (PUT /api/v1/save đã ghi từ React). KHÔNG fallback lén
  sang `state.json` thô — nếu host chưa review thì không có gì để confirm.
- Gate R6 đã enforce ở backend + React; file export vẫn render trung thực
  (badge 🟢/🟡/🔴 theo confidence — không giấu nếu lọt qua).

Spec:
- `docs/spec/export-format.md` §1 (minutes.md Jinja2 template)
- §2 (tasks_jira.csv)
- §3 (review_log.json — ghi bởi backend/api.py, không thuộc module này)

Đầu vào: MeetingState (Pydantic schema) hoặc dict cùng shape.
Đầu ra: file được ghi vào runs/<meeting_id>/<ts>/minutes.md + tasks_jira.csv.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import logging
import time
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Paths + version
# ──────────────────────────────────────────────────────────────────────

# Thư mục templates cùng cấp file này.
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Time chuẩn ISO cho metadata footer.
_TS_ISO = lambda: _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _confidence_badge(conf: float) -> str:
    """🟢 ≥0.75 · 🟡 0.50-0.75 · 🔴 <0.50 (taxonomy §5)."""
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return "🔴"
    if c < 0.50:
        return "🔴"
    if c < 0.75:
        return "🟡"
    return "🟢"


def _coerce_state(state: Any) -> dict[str, Any]:
    """Chấp nhận cả Pydantic MeetingState lẫn dict — đều trả dict plain.

    Lý do: cho phép test gọi với dict literal (không cần khởi tạo model),
    đồng thời vẫn dùng được với Pydantic model trong code production.
    """
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if isinstance(state, dict):
        return state
    raise TypeError(
        f"state phải là MeetingState (Pydantic) hoặc dict, got {type(state).__name__}"
    )


def _role_label(role: str | None) -> str:
    """Map role_in_discussion → tiếng Việt cho evidence (human-readable).

    Spec không bắt buộc việt hoá nhưng giúp người đọc biết ngữ cảnh.
    """
    mapping = {
        "propose": "đề xuất",
        "object": "phản đối",
        "decide": "chốt",
        "confirm": "xác nhận",
        "info": "thông tin",
    }
    return mapping.get((role or "").lower(), role or "info")


def _flatten_evidence(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Đính role_in_message (tiếng Việt) + giữ field gốc."""
    out = []
    for ev in item.get("evidence", []) or []:
        out.append({
            **ev,
            "role_in_message": _role_label(ev.get("role_in_discussion")),
        })
    return out


def _ensure_render_context(state: dict[str, Any]) -> dict[str, Any]:
    """Build context cho Jinja2 từ state dict.

    Lý do tách: dễ test (assert theo group), dễ thêm trường mà không sửa template.
    """
    items = state.get("items", []) or []
    meeting = state.get("meeting") or {}
    # Nếu meeting không phải dict → ép về dict rỗng (template dùng {{ meeting.X }}).
    if not isinstance(meeting, dict):
        meeting = {"id": str(meeting)}
    # Defaults — confirmed_state.json (api-contract §2) chỉ chứa meeting name,
    # thiếu title/date/pipeline_version. Fill bằng placeholder hiển thị rõ.
    meeting.setdefault("id", "?")
    meeting.setdefault("title", "(chưa có title)")
    meeting.setdefault("date", "")
    meeting.setdefault("pipeline_version", "?")

    decisions: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    open_issues: list[dict[str, Any]] = []
    requirements: list[dict[str, Any]] = []
    knowledge: list[dict[str, Any]] = []

    for it in items:
        # Mọi item đính badge phục vụ template (gate R6 đã chặn đỏ trước).
        it = dict(it)
        it["badge"] = _confidence_badge(it.get("confidence"))
        t = it.get("type")
        if t == "decision":
            # Chỉ in final trong mục chính; discarded chỉ xuất hiện
            # trong dòng "Thay thế ..." của final.
            if it.get("status") == "final":
                it["evidence"] = _flatten_evidence(it)
                # Objections lưu evidence trong decision; chuẩn hoá format nếu có.
                norm_obj = []
                for obj in it.get("objections", []) or []:
                    if isinstance(obj, dict):
                        norm_obj.append({
                            **obj,
                            "role_in_message": _role_label(
                                obj.get("role_in_discussion")
                            ),
                        })
                it["objections"] = norm_obj
                decisions.append(it)
        elif t == "task":
            tasks.append(it)
        elif t == "blocker":
            blockers.append(it)
        elif t == "open_issue":
            open_issues.append(it)
        elif t == "requirement":
            requirements.append(it)
        elif t == "knowledge":
            knowledge.append(it)

    return {
        "meeting": meeting,
        "brief": state.get("brief"),
        "decisions": decisions,
        "tasks": tasks,
        "blockers": blockers,
        "open_issues": open_issues,
        "requirements": requirements,
        "knowledge": knowledge,
        "known_limitations": state.get("known_limitations", []) or [],
    }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def render_minutes(state: Any) -> str:
    """Render minutes.md theo template `templates/minutes.md.j2`.

    Trả chuỗi markdown hoàn chỉnh. Caller chịu trách nhiệm ghi file.
    """
    state_dict = _coerce_state(state)
    ctx = _ensure_render_context(state_dict)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,  # thiếu biến → lỗi rõ, không in rỗng
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tpl = env.get_template("minutes.md.j2")
    return tpl.render(**ctx)


def render_jira_csv(state: Any) -> str:
    """Render tasks_jira.csv theo spec export-format.md §2.

    Quy tắc:
    - Header cố định: Summary,Issue Type,Assignee,Due Date,Labels,Description.
    - Summary prefix `[D1]` / `[T2]`... để trace về decision/task.
    - Owner/Due = "TBD" → ô trống + note vào Description.
    - Labels: `{meeting_id};decision-{id}` hoặc `{meeting_id};task-{id}`.
    - Description: evidence đầu tiên `[HH:MM:SS] speaker: "quote"`.
    """
    state_dict = _coerce_state(state)
    items = state_dict.get("items", []) or []
    meeting_id = state_dict.get("meeting", {}).get("id", "unknown")

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["Summary", "Issue Type", "Assignee", "Due Date", "Labels", "Description"]
    )

    for it in items:
        t = it.get("type")
        item_id = it.get("id", "?")
        prefix = _prefix_for_type(t)
        if prefix is None:
            continue  # chỉ export decision + task ra Jira (spec §2)

        # Content theo từng loại
        if t == "decision":
            # Discarded bỏ qua — không phải việc phải làm. Chỉ final xuất Jira
            # (matches minutes.md: chỉ dòng "Thay thế D0" trong final).
            if it.get("status") != "final":
                continue
            content = (it.get("content") or "").strip()
            if not content:
                continue
            label_kind = f"decision-{item_id}"
        elif t == "task":
            content = (it.get("what") or "").strip()
            if not content:
                continue
            label_kind = f"task-{item_id}"
        else:
            continue

        summary = f"[{item_id}] {content}"

        # Owner / Due → TBD → ô trống + note Description
        owner = (it.get("owner") or "").strip() or ""
        due = (it.get("due") or "").strip() or ""
        tbd_notes: list[str] = []
        if owner.upper() == "TBD":
            owner = ""
            tbd_notes.append("Owner TBD - cần gán")
        if due.upper() == "TBD":
            due = ""
            tbd_notes.append("Due TBD - cần xác định")
        # due_hint giữ gốc (R2) — note vào Description
        if it.get("due_hint"):
            tbd_notes.append(f"due_hint: {it['due_hint']}")

        # Description: evidence đầu + TBD notes
        ev = (it.get("evidence") or [{}])[0]
        desc_parts: list[str] = []
        if ev.get("quote"):
            ts = ev.get("timestamp", "?")
            spk = ev.get("speaker", "?")
            desc_parts.append(f'Evidence [{ts}] {spk}: "{ev["quote"]}"')
        if tbd_notes:
            desc_parts.append(" | ".join(tbd_notes))

        writer.writerow([
            summary,
            "Task",
            owner,
            due,
            f"{meeting_id};{label_kind}",
            " — ".join(desc_parts),
        ])

    return buf.getvalue()


def _prefix_for_type(t: str | None) -> str | None:
    """Map type → prefix Summary. None = bỏ qua."""
    if t in ("decision", "task"):
        return t[0].upper()  # 'D' hoặc 'T'
    return None


# ──────────────────────────────────────────────────────────────────────
# export_meeting — top-level orchestrator
# ──────────────────────────────────────────────────────────────────────


def _latest_run_dir(meeting_id: str, runs_dir: Path) -> Path | None:
    """Tìm runs/<meeting>/<ts> mới nhất."""
    base = runs_dir / meeting_id
    if not base.is_dir():
        return None
    children = sorted(
        [p for p in base.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    return children[0] if children else None


def export_meeting(
    meeting_id: str,
    runs_dir: str | Path,
    *,
    now_ts: str | None = None,
) -> dict[str, Any]:
    """Sinh minutes.md + tasks_jira.csv từ confirmed_state.json.

    Args:
        meeting_id: ID meeting (vd: 'tc2').
        runs_dir: Thư mục runs/ (Path hoặc str).
        now_ts: Override timestamp (test). Mặc định = `time.strftime("%Y%m%d-%H%M%S")`.

    Returns:
        dict với key 'files' (list đường dẫn tương đối) — khớp api-contract §3.

    Raises:
        FileNotFoundError: Không có run / không có confirmed_state.json —
            báo lỗi rõ ràng (KHÔNG fallback sang state.json thô).
        ValueError: Confirmed state không có `items`.
    """
    runs_path = Path(runs_dir).resolve()
    run_dir = _latest_run_dir(meeting_id, runs_path)
    if run_dir is None:
        raise FileNotFoundError(
            f"meeting not found: no run directory under {runs_path / meeting_id}. "
            f"Tip: chạy `python -m pipeline.cli run --meeting {meeting_id}` trước."
        )

    confirmed_path = run_dir / "confirmed_state.json"
    if not confirmed_path.exists():
        raise FileNotFoundError(
            f"confirmed_state.json not found in {run_dir}. "
            f"Export yêu cầu host đã review (PUT /api/v1/review) trước — "
            "không fallback sang state.json thô (gate R6)."
        )

    state = json.loads(confirmed_path.read_text(encoding="utf-8"))
    # Confirmed shape (api-contract §2) có thể thiếu `meeting` envelope —
    # bổ sung meeting id tối thiểu để template/render không lỗi.
    if "meeting" not in state or not isinstance(state.get("meeting"), dict):
        state["meeting"] = {"id": meeting_id}
    if "items" not in state:
        raise ValueError(
            f"confirmed_state.json thiếu key 'items' — meeting={meeting_id}"
        )

    # Tính lại stats theo items hiện tại (để CSV/Label không stale).
    # Không enforce badge gate — caller (API) đã làm.
    minutes_md = render_minutes(state)
    jira_csv = render_jira_csv(state)

    # Ghi file vào timestamp dir mới (audit: mỗi lần export = 1 dir mới).
    ts = now_ts or time.strftime("%Y%m%d-%H%M%S")
    out_dir = run_dir / ts
    # Nếu trùng timestamp (gọi nhiều lần trong cùng giây) → thêm suffix.
    suffix = 0
    while out_dir.exists():
        suffix += 1
        out_dir = run_dir / f"{ts}-{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)

    minutes_path = out_dir / "minutes.md"
    csv_path = out_dir / "tasks_jira.csv"
    minutes_path.write_text(minutes_md, encoding="utf-8")
    csv_path.write_text(jira_csv, encoding="utf-8")

    # Trả đường dẫn relative cho dễ đọc + absolute để log/debug.
    rel_minutes = minutes_path.relative_to(runs_path.parent).as_posix()
    rel_csv = csv_path.relative_to(runs_path.parent).as_posix()
    abs_minutes = str(minutes_path.resolve())
    abs_csv = str(csv_path.resolve())

    logger.info(
        "[export] meeting=%s wrote minutes.md (%d chars) + tasks_jira.csv "
        "(%d rows) → %s",
        meeting_id,
        len(minutes_md),
        jira_csv.count("\n"),
        out_dir,
    )

    return {
        "files": [rel_minutes, rel_csv],
        "absolute_paths": [abs_minutes, abs_csv],
        "generated_at": _TS_ISO(),
        "out_dir": str(out_dir.resolve()),
    }


__all__ = [
    "render_minutes",
    "render_jira_csv",
    "export_meeting",
]