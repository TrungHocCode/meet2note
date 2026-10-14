"""
pipeline/service.py — Orchestrator chạy pipeline dùng chung cho CLI và API.

Tách từ `cli.cmd_run` để `backend/api.py` (upload) gọi cùng 1 đường
(ADR-0005: API là adapter mỏng, không duplicate logic pipeline).
CLI chỉ còn: parse args + fixture wiring + in tiến trình.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .extract import extract
from .ingest import parse_transcript
from .resolve import resolve
from .schema import Meeting, Participant
from .verify import verify_state


def run_pipeline(
    *,
    meeting_id: str,
    meta: dict[str, Any],
    transcript_path: str | Path,
    runs_dir: str | Path,
    chunk_size: int = 80,
    overlap: int = 10,
    extract_llm_fn: Callable[..., str] | None = None,
    resolve_llm_fn: Callable[..., str] | None = None,
    brief_raw: dict[str, Any] | None = None,
    pipeline_version: str = "0.0.0",
    log_llm: bool = True,
    turns: list[dict[str, Any]] | None = None,
    ingest_limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Chạy ingest → extract → resolve → verify → lưu state.json.

    Args:
        meeting_id: id meeting (dùng cho runs/<id>/<ts>/).
        meta: dict metadata (id, title, date, participants, glossary).
        transcript_path: file .txt/.srt (đã tồn tại, đã validate).
        runs_dir: thư mục runs/.
        extract_llm_fn / resolve_llm_fn: None → live LLM qua .env.
        brief_raw: brief đã trích (caller tự gọi extract_brief hoặc fixture).
        pipeline_version: ghi vào envelope.
        log_llm: ghi llm_log.jsonl (tắt trong test cho nhẹ).

    Returns:
        {"state": MeetingState, "out_dir": Path, "turns_count": int,
         "extract": {...}, "resolution": {...}}.

    Raises:
        FileNotFoundError: transcript không tồn tại.
        RuntimeError: LLM chưa cấu hình (từ extract — caller dịch ra
            message/HTTP status phù hợp).
    """
    transcript_path = Path(transcript_path)
    if not transcript_path.exists():
        raise FileNotFoundError(f"transcript not found: {transcript_path}")
    runs_dir = Path(runs_dir)

    if turns is None:
        turns, ingest_limitations = parse_transcript(transcript_path)
    else:
        ingest_limitations = list(ingest_limitations or [])

    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = runs_dir / meeting_id / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = (out_dir / "llm_log.jsonl") if log_llm else None

    extraction = extract(
        meta, turns,
        log_path=log_path,
        llm_fn=extract_llm_fn,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    meeting = Meeting(
        id=meta["id"],
        title=meta.get("title", meeting_id),
        date=meta["date"],
        participants=[Participant(**p) for p in meta.get("participants", [])],
        source_file=str(transcript_path),
        pipeline_version=pipeline_version,
    )

    resolution = resolve(meta, extraction["chunk_items"], llm_fn=resolve_llm_fn)

    state = verify_state(
        meeting=meeting,
        items_raw=resolution["items"],
        conf_llm_map=extraction["conf_llm_map"],
        turns=turns,
        limitations=list(ingest_limitations)
        + extraction["known_limitations"]
        + resolution["known_limitations"],
        brief_raw=brief_raw,
    )

    (out_dir / "state.json").write_text(
        state.model_dump_json(indent=2), encoding="utf-8"
    )
    return {
        "state": state,
        "out_dir": out_dir,
        "turns_count": len(turns),
        "extraction": extraction,
        "resolution": resolution,
    }


__all__ = ["run_pipeline"]
