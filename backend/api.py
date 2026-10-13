"""
backend/api.py — FastAPI layer mỏng (ADR-0005) cho P2 review workflow + P3 export.

Đọc/ghi trực tiếp `runs/<meeting>/<ts>/state.json` + `review_log.json`.
KHÔNG chứa logic pipeline — chỉ adapter theo `docs/spec/api-contract.md`.
Export gọi `pipeline.export.export_meeting` (P3) — không tự render.

Endpoints (theo spec §1-§3):
- GET  /health
- GET  /api/v1/review?meeting=tc2              → 200 state.json | 404
- PUT  /api/v1/review?meeting=tc2              → ghi confirmed_state.json + append review_log
- POST /api/v1/export?meeting=tc2              → 403 gate_red_items | 200 files | 404

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

from fastapi import FastAPI, HTTPException, Query
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


__all__ = ["app"]