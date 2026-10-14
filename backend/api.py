"""
backend/api.py — FastAPI layer mỏng (ADR-0005) cho P2 review workflow + P3 export.

Đọc/ghi trực tiếp `runs/<meeting>/<ts>/state.json` + `review_log.json`.
KHÔNG chứa logic pipeline — chỉ adapter theo `docs/spec/api-contract.md`.
Export gọi `pipeline.export.export_meeting` (P3) — không tự render.

Endpoints (theo spec §1-§3 + P5 upload/transcript):
- GET  /health
- GET  /api/v1/review?meeting=tc2              → 200 state.json | 404
- PUT  /api/v1/review?meeting=tc2              → ghi confirmed_state.json + append review_log
- POST /api/v1/export?meeting=tc2              → 403 gate_red_items | 200 files | 404
- GET  /api/v1/transcript?meeting=tc2          → 200 turns | 404
- POST /api/v1/meetings/upload (multipart)     → chạy pipeline, 200 state | 400/422/503

CORS chỉ http://localhost:5173 (React dev theo AGENTS.md §2).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pipeline.export import export_meeting

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Paths + defaults
# ──────────────────────────────────────────────────────────────────────

# Default project root = parent của backend/ (theo cây PLAN_MVP 2.3).
# Có thể override qua env MEET2NOTE_ROOT khi chạy đường dẫn khác.
_DEFAULT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path(
    os.environ.get("MEET2NOTE_ROOT", str(_DEFAULT_ROOT))
).resolve()

# Time chuẩn ISO cho review entries.
_TS_ISO = lambda: _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ──────────────────────────────────────────────────────────────────────
# Pydantic models cho request body
# ──────────────────────────────────────────────────────────────────────


class ReviewChange(BaseModel):
    """Một thay đổi mà host thực hiện (ADR-0004 — audit)."""

    item_id: str = Field(..., min_length=1)
    action: str = Field(..., pattern="^(agree|edit|remove)$")
    old: dict[str, Any] | None = None
    new: dict[str, Any] | None = None


class ReviewPutBody(BaseModel):
    items: list[dict[str, Any]] = Field(..., min_length=0)
    changes: list[ReviewChange] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _latest_run_dir(meeting_id: str) -> Path | None:
    """Tìm runs/<meeting>/<ts> mới nhất. None nếu chưa từng chạy."""
    runs_dir = PROJECT_ROOT / "runs" / meeting_id
    if not runs_dir.is_dir():
        return None
    children = sorted(
        [p for p in runs_dir.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    return children[0] if children else None


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _badge_of(item: dict[str, Any]) -> str:
    """Red <0.50 · yellow 0.50-0.75 · green ≥0.75 (taxonomy §5)."""
    conf = float(item.get("confidence", 0.0) or 0.0)
    if conf < 0.50:
        return "red"
    if conf < 0.75:
        return "yellow"
    return "green"


def _red_items(state: dict[str, Any]) -> list[str]:
    """Trả list id có badge đỏ (gate R6 — chặn export)."""
    out = []
    for it in state.get("items", []):
        if _badge_of(it) == "red":
            out.append(str(it.get("id", "?")))
    return out


# ──────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="meet2note API",
    version="0.4.0",
    description="Lớp mỏng đọc/ghi runs/ — không chứa logic pipeline (ADR-0005).",
)

# CORS chỉ React dev (AGENTS.md §2 + api-contract §4).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "PUT", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def get_health() -> dict[str, str]:
    """Health-check — không phụ thuộc meeting state."""
    return {"status": "ok"}


@app.get("/api/v1/review")
def get_review(meeting: str = Query(..., min_length=1)) -> JSONResponse:
    """Trả meeting_state.json cho React render (api-contract §1).

    404 nếu chưa có run (chưa `cli run`).
    """
    run_dir = _latest_run_dir(meeting)
    if run_dir is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "meeting not found"},
        )
    state_path = run_dir / "state.json"
    if not state_path.exists():
        return JSONResponse(
            status_code=404,
            content={"detail": "meeting state not found"},
        )
    state = _read_json(state_path)
    return JSONResponse(status_code=200, content=state)


@app.put("/api/v1/review")
def put_review(meeting: str, body: ReviewPutBody) -> JSONResponse:
    """Ghi confirmed_state.json + append review_log (api-contract §2).

    Body: {items, changes}. Mỗi change có action ∈ {agree, edit, remove}.
    """
    run_dir = _latest_run_dir(meeting)
    if run_dir is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "meeting not found"},
        )

    # 1. Ghi confirmed_state.json — GIỮ envelope meeting + known_limitations
    # từ state.json (export cần title/date/version; PUT body chỉ có items).
    confirmed_path = run_dir / "confirmed_state.json"
    state_path = run_dir / "state.json"
    base: dict[str, Any] = _read_json(state_path) if state_path.exists() else {}
    meeting_env = base.get("meeting", {"id": meeting})
    if not isinstance(meeting_env, dict):
        meeting_env = {"id": meeting}
    _write_json(
        confirmed_path,
        {
            "meeting": meeting_env,
            "brief": base.get("brief"),
            "items": body.items,
            "no_decision": base.get("no_decision", False),
            "known_limitations": base.get("known_limitations", []),
            "updated_at": _TS_ISO(),
        },
    )

    # 2. Append review_log.json
    log_path = run_dir / "review_log.json"
    if log_path.exists():
        log = _read_json(log_path)
    else:
        log = {"meeting_id": meeting, "entries": []}
    log.setdefault("entries", [])
    now_iso = _TS_ISO()
    for ch in body.changes:
        log["entries"].append({
            "item_id": ch.item_id,
            "action": ch.action,
            "old": ch.old,
            "new": ch.new,
            "reviewer": "host",
            "ts": now_iso,
        })
    _write_json(log_path, log)

    # 3. Tóm tắt stats nhanh (đếm theo badge từ items mới).
    badge_counter: dict[str, int] = {"red": 0, "yellow": 0, "green": 0}
    for it in body.items:
        badge_counter[_badge_of(it)] += 1
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "stats": {
                "by_badge": badge_counter,
                "items_total": len(body.items),
                "changes_count": len(body.changes),
            },
        },
    )


@app.post("/api/v1/export")
def post_export(meeting: str) -> JSONResponse:
    """Gate R6: chỉ export khi hết thẻ đỏ (api-contract §3).

    - Còn thẻ đỏ → 403 + `gate_red_items` (gate R6 enforcement).
    - Hết đỏ + có `confirmed_state.json` → 200 + `{"files": [...]}`.
    - Chưa confirm → 400 (export yêu cầu host đã review).
    - Không tìm thấy meeting / state.json → 404.
    """
    run_dir = _latest_run_dir(meeting)
    if run_dir is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "meeting not found"},
        )
    state_path = run_dir / "state.json"
    if not state_path.exists():
        return JSONResponse(
            status_code=404,
            content={"detail": "meeting state not found"},
        )
    state = _read_json(state_path)
    reds = _red_items(state)
    if reds:
        return JSONResponse(
            status_code=403,
            content={"error": "gate_red_items", "red_items": reds},
        )

    # Gate pass → gọi export_meeting (P3).
    try:
        result = export_meeting(meeting, PROJECT_ROOT / "runs")
    except FileNotFoundError as e:
        # Không có confirmed_state.json → host chưa PUT lần nào.
        return JSONResponse(
            status_code=400,
            content={"error": "not_confirmed", "detail": str(e)},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": str(e)},
        )

    return JSONResponse(
        status_code=200,
        content={
            "files": result["files"],
            "generated_at": result["generated_at"],
        },
    )


# ──────────────────────────────────────────────────────────────────────
# Transcript viewer + upload (P5)
# ──────────────────────────────────────────────────────────────────────


def _find_transcript_file(meeting_id: str) -> Path | None:
    """Tìm transcript: data/transcripts/ trước, data/uploads/ sau."""
    for base in ("transcripts", "uploads"):
        d = PROJECT_ROOT / "data" / base
        if not d.is_dir():
            continue
        for ext in (".txt", ".srt", ".docx"):
            for f in sorted(d.glob(f"{meeting_id}*{ext}")):
                return f
    return None


@app.get("/api/v1/transcript")
def get_transcript(meeting: str = Query(..., min_length=1)) -> JSONResponse:
    """Trả turns transcript để UI hiện context quanh evidence (P5).

    200: {meeting, source, turns:[{turn,t_start,t_end,speaker,text}], limitations}.
    404: không tìm thấy transcript.
    """
    from pipeline.ingest import parse_transcript

    path = _find_transcript_file(meeting)
    if path is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "transcript not found"},
        )
    turns, limitations = parse_transcript(path)
    return JSONResponse(
        status_code=200,
        content={
            "meeting": meeting,
            "source": path.name,
            "turns": turns,
            "limitations": limitations,
        },
    )


_MEETING_ID_RE = None  # lazy-compile dưới để tránh import re ở top


def _valid_meeting_id(mid: str) -> bool:
    import re

    global _MEETING_ID_RE
    if _MEETING_ID_RE is None:
        _MEETING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    return bool(_MEETING_ID_RE.match(mid or ""))


@app.post("/api/v1/meetings/upload")
async def upload_meeting(
    file: UploadFile = File(...),
    meeting_id: str = Form(""),
    title: str = Form("Cuộc họp upload"),
    date: str = Form(...),
    participants: str = Form("[]"),
    chunk_size: int = Form(40),
    overlap: int = Form(10),
) -> JSONResponse:
    """Upload transcript (.txt/.srt/.docx) + chạy pipeline ngay, trả state để review.

    - meeting_id trống → lấy từ tên file (bỏ đuôi, sanitize).
    - participants: JSON string list [{name, role?, aliases?}] (aliases thiếu → [name]).
    - date: YYYY-MM-DD (dùng để resolve ngày tương đối — R2).
    - File + meta lưu ở data/uploads/ (gitignored — transcript người dùng
      KHÔNG bao giờ commit). Chạy live LLM qua .env (thiếu key → 503).
    - 400: sai định dạng/ext; 422: parse transcript lỗi; 503: thiếu LLM;
      200: {meeting_id, state, out_dir, turns_count}.
    """
    import json as _json
    import re as _re

    from pipeline.service import run_pipeline

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in (".txt", ".srt", ".docx"):
        return JSONResponse(
            status_code=400,
            content={"detail": f"chỉ nhận .txt/.srt/.docx, got {filename!r}"},
        )
    mid = (meeting_id or "").strip() or _re.sub(r"\.[^.]+$", "", filename)
    mid = _re.sub(r"[^A-Za-z0-9_-]", "_", mid)[:64] or "uploaded"
    if not _valid_meeting_id(mid):
        return JSONResponse(
            status_code=400, content={"detail": f"meeting_id không hợp lệ: {mid!r}"}
        )
    if not _re.match(r"^\d{4}-\d{2}-\d{2}$", date or ""):
        return JSONResponse(
            status_code=400, content={"detail": "date phải YYYY-MM-DD"}
        )
    try:
        parts = _json.loads(participants or "[]")
        if not isinstance(parts, list):
            raise ValueError("participants phải là JSON array")
    except (ValueError, _json.JSONDecodeError) as e:
        return JSONResponse(status_code=400, content={"detail": f"participants lỗi: {e}"})
    norm_parts = []
    for p in parts:
        if not isinstance(p, dict) or not str(p.get("name", "")).strip():
            return JSONResponse(
                status_code=400,
                content={"detail": "mỗi participant cần {name}"},
            )
        name = str(p["name"]).strip()
        norm_parts.append({
            "name": name,
            "role": str(p.get("role", "") or "member").strip(),
            "aliases": list(p.get("aliases") or [name]),
        })

    uploads = PROJECT_ROOT / "data" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    transcript_path = uploads / f"{mid}{ext}"
    content = await file.read()
    if not content.strip():
        return JSONResponse(status_code=400, content={"detail": "file rỗng"})
    transcript_path.write_bytes(content)
    meta = {
        "id": mid,
        "title": title.strip() or mid,
        "date": date,
        "participants": norm_parts,
        "glossary": {},
    }
    (uploads / f"{mid}_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Brief live (fail → None, pipeline vẫn chạy).
    brief_raw = None
    try:
        from pipeline.extract import extract_brief as _brief_fn
        from pipeline.ingest import parse_transcript as _parse

        turns, _ = _parse(transcript_path)
        try:
            brief_raw = _brief_fn(meta, turns)
        except RuntimeError:
            brief_raw = None
        result = run_pipeline(
            meeting_id=mid,
            meta=meta,
            transcript_path=transcript_path,
            runs_dir=PROJECT_ROOT / "runs",
            chunk_size=max(1, chunk_size),
            overlap=max(0, overlap),
            brief_raw=brief_raw,
            pipeline_version="upload",
        )
    except FileNotFoundError as e:
        return JSONResponse(status_code=422, content={"detail": str(e)})
    except RuntimeError as e:
        # Thường là thiếu LLM config (extract gọi call_llm).
        return JSONResponse(
            status_code=503,
            content={"detail": f"LLM chưa sẵn sàng: {e}"},
        )

    state = result["state"]
    return JSONResponse(
        status_code=200,
        content={
            "meeting_id": mid,
            "state": json.loads(state.model_dump_json()),
            "turns_count": result["turns_count"],
            "out_dir": str(result["out_dir"].relative_to(PROJECT_ROOT)),
        },
    )


__all__ = ["app"]