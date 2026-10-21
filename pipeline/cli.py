"""
cli.py — Pipeline CLI: `run` + `eval` (eval skeleton P1 — full ở P4).

Cách chạy (theo AGENTS.md §3 + runbook/local-dev.md §2):
    python -m pipeline.cli run --meeting tc2
        → ingest → extract → resolve → verify → runs/<meeting_id>/<ts>/state.json + llm_log.jsonl

    python -m pipeline.cli run --meeting tc2 --llm-fixture <path> --resolve-fixture <path>
        → mock cả extract & resolve (test/demo không cần key).

    python -m pipeline.cli eval
        → chạy 5 ca → eval/report.md (P4).

Thiết kế:
- Pipeline độc lập (ADR-0005). Chạy được không cần server.
- P2: thêm resolve (trọng tái xuyên chunk + entity-link) giữa extract và verify.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .ingest import parse_transcript

load_dotenv()  # nạp .env (Ollama/hosted key) — file này gitignored

if hasattr(sys.stdout, "reconfigure"):
    # Console Windows mặc định cp1252 → crash khi in tiếng Việt.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Pipeline version — bump theo phase (P0=0.1.0 → P1=0.2.0 → P2=0.3.0 → P4=0.4.0).
PIPELINE_VERSION = "0.4.0"

# Đường dẫn mặc định — resolve tương đối với project root (cwd khi `python -m`).
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _load_meta(meta_id: str, data_dir: Path) -> dict[str, Any]:
    p = data_dir / "meta" / f"{meta_id}_meta.json"
    if not p.exists():
        raise FileNotFoundError(f"meta not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _find_transcript(meta_id: str, data_dir: Path) -> Path:
    """Tìm file transcript (.txt / .srt / .docx) bắt đầu bằng `<meta_id>`."""
    transcripts = data_dir / "transcripts"
    if not transcripts.exists():
        raise FileNotFoundError(f"transcripts dir not found: {transcripts}")
    for ext in (".txt", ".srt", ".docx"):
        # sorted() để chọn deterministic nếu có nhiều file trùng prefix
        for f in sorted(transcripts.glob(f"{meta_id}*{ext}")):
            return f
    raise FileNotFoundError(
        f"transcript for {meta_id} not found in {transcripts} "
        f"(looked for {meta_id}*.txt, {meta_id}*.srt and {meta_id}*.docx)"
    )


def _make_fixture_llm(fixture_path: Path):
    """Tạo mock LLM callable từ file JSON.

    File JSON: list các response (1 phần tử = dùng cho mọi chunk; nhiều = dùng tuần tự).
    Mỗi response là chuỗi JSON — sẽ được trả về verbatim cho từng chunk request.

    Dùng để:
    - Chạy end-to-end pipeline mà không cần .env (gate test, demo).
    - Test extract với input shape biết trước (deterministic).
    """
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(
            f"fixture phải là JSON array của các response. Got: {type(data).__name__}"
        )
    responses = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in data]
    if not responses:
        raise ValueError("fixture rỗng — cần ≥1 response")

    call_idx = {"n": 0}

    def llm_fn(messages):
        idx = call_idx["n"]
        if idx < len(responses):
            content = responses[idx]
            call_idx["n"] = idx + 1
            return content
        # Hết response trong fixture → lặp lại response cuối (đủ cho 1-chunk transcripts)
        return responses[-1]

    return llm_fn


# ──────────────────────────────────────────────────────────────────────
# `run` command
# ──────────────────────────────────────────────────────────────────────


def cmd_run(args: argparse.Namespace) -> int:
    meeting_id = args.meeting
    root = Path(args.root).resolve() if args.root else DEFAULT_PROJECT_ROOT
    data_dir = (root / args.data_dir).resolve() if not Path(args.data_dir).is_absolute() \
        else Path(args.data_dir)
    runs_dir = (root / args.runs_dir).resolve() if not Path(args.runs_dir).is_absolute() \
        else Path(args.runs_dir)

    print(f"[cli] meeting={meeting_id}")
    print(f"[cli] root={root}")

    # Load meta + transcript (báo lỗi thân thiện thay vì để Python traceback)
    try:
        meta = _load_meta(meeting_id, data_dir)
    except FileNotFoundError as e:
        print(f"[cli] {e}")
        print(f"[cli] Tip: kiểm tra {data_dir}/meta/{meeting_id}_meta.json có tồn tại không.")
        return 2

    try:
        transcript_path = _find_transcript(meeting_id, data_dir)
    except FileNotFoundError as e:
        print(f"[cli] {e}")
        return 2
    print(f"[cli] transcript={transcript_path}")

    # Ingest trước (cần turns cho brief) — service dùng lại turns này.
    # (service.run_pipeline dùng chung với API upload — ADR-0005.)
    from .service import run_pipeline

    turns, ingest_limitations = parse_transcript(transcript_path)
    print(f"[cli] ingest: {len(turns)} turns, {len(ingest_limitations)} limitations")

    # Quyết định LLM extract: live (call_llm) hay fixture mock
    extract_llm_fn = None
    if args.llm_fixture:
        fixture_path = Path(args.llm_fixture)
        if not fixture_path.is_absolute():
            fixture_path = (root / args.llm_fixture).resolve()
        if not fixture_path.exists():
            print(f"[cli] llm_fixture not found: {fixture_path}")
            return 2
        print(f"[cli] using LLM fixture (mock) for extract: {fixture_path}")
        extract_llm_fn = _make_fixture_llm(fixture_path)

    # Quyết định LLM resolve: mock qua --resolve-fixture, hoặc None → deterministic
    resolve_llm_fn = None
    if args.resolve_fixture:
        fix_path = Path(args.resolve_fixture)
        if not fix_path.is_absolute():
            fix_path = (root / args.resolve_fixture).resolve()
        if not fix_path.exists():
            print(f"[cli] resolve_fixture not found: {fix_path}")
            return 2
        print(f"[cli] using LLM fixture (mock) for resolve: {fix_path}")
        resolve_llm_fn = _make_fixture_llm(fix_path)

    # Brief — 1 call toàn transcript (taxonomy §8). Live: luôn gọi.
    # Fixture: chỉ gọi khi có --brief-fixture (tránh ăn response của extract).
    from .extract import extract_brief

    brief_raw: dict[str, Any] | None = None
    if args.llm_fixture:
        if args.brief_fixture:
            bp = Path(args.brief_fixture)
            if not bp.is_absolute():
                bp = (root / args.brief_fixture).resolve()
            if bp.exists():
                print(f"[cli] using LLM fixture (mock) for brief: {bp}")
                brief_raw = _make_fixture_llm(bp)([])
            else:
                print(f"[cli] brief_fixture not found: {bp} — bỏ brief")
        else:
            print("[cli] brief: skipped (fixture mode, thiếu --brief-fixture)")
    else:
        try:
            brief_raw = extract_brief(meta, turns)
            print(f"[cli] brief: {'ok' if brief_raw else 'LLM fail → verify bỏ'}")
        except RuntimeError as e:
            print(f"[cli] brief FAILED (không chặn pipeline): {e}")

    # Chạy pipeline qua service dùng chung với API (ADR-0005).
    try:
        result = run_pipeline(
            meeting_id=meeting_id,
            meta=meta,
            transcript_path=transcript_path,
            runs_dir=runs_dir,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            extract_llm_fn=extract_llm_fn,
            resolve_llm_fn=resolve_llm_fn,
            brief_raw=brief_raw,
            pipeline_version=PIPELINE_VERSION,
            turns=turns,
            ingest_limitations=ingest_limitations,
        )
    except RuntimeError as e:
        # Thiếu config LLM → in hướng dẫn, không crash im lặng
        print(f"[cli] extract FAILED: {e}")
        print("[cli] Tip: copy .env.example → .env và điền OPENAI_BASE_URL + MODEL_NAME.")
        print("[cli]     Hoặc dùng --llm-fixture <path.json> để chạy mock end-to-end.")
        print("[cli]     Test vẫn pass nhờ mock LLM (xem tests/test_extract.py).")
        return 2

    state = result["state"]
    out_dir = result["out_dir"]
    extraction = result["extraction"]
    resolution = result["resolution"]
    print(
        f"[cli] extract: {len(extraction['items'])} items, "
        f"{len(extraction['chunk_items'])} chunks, "
        f"{len(extraction['known_limitations'])} chunk failures"
    )
    print(
        f"[cli] resolve: {len(resolution['items'])} items, "
        f"{len(resolution['known_limitations'])} arbitration notes"
    )

    # Tóm tắt output
    state_path = out_dir / "state.json"
    print(f"[cli] saved state: {state_path}")
    print(f"[cli] stats: {state.stats}")
    print(f"[cli] no_decision={state.no_decision}")
    if state.known_limitations:
        print(f"[cli] known_limitations ({len(state.known_limitations)}):")
        for lim in state.known_limitations[:5]:
            print(f"        - {lim}")
        if len(state.known_limitations) > 5:
            print(f"        ... và {len(state.known_limitations) - 5} nữa")
    return 0


# ──────────────────────────────────────────────────────────────────────
# `eval` command (P4: eval/runner.py — 5 ca + golden)
# ──────────────────────────────────────────────────────────────────────


def cmd_eval(args: argparse.Namespace) -> int:
    from eval.runner import main as eval_main

    argv = []
    if getattr(args, "live", False):
        argv.append("--live")
    if getattr(args, "cases", None):
        argv += ["--cases", args.cases]
    argv += ["--chunk-size", str(getattr(args, "chunk_size", 40))]
    argv += ["--overlap", str(getattr(args, "overlap", 10))]
    argv += ["--out", getattr(args, "out", "eval/results.json")]
    return eval_main(argv)


# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="meet2note pipeline CLI (P2: ingest → extract → resolve → verify).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="chạy pipeline cho 1 meeting")
    p_run.add_argument("--meeting", required=True, help="meeting id (vd: tc2)")
    p_run.add_argument(
        "--root",
        default=None,
        help="project root (mặc định: thư mục chứa pipeline/)",
    )
    p_run.add_argument(
        "--data-dir",
        default="data",
        help="đường dẫn tới data/ (relative tới root, hoặc absolute)",
    )
    p_run.add_argument(
        "--runs-dir",
        default="runs",
        help="đường dẫn tới runs/ (relative tới root, hoặc absolute)",
    )
    p_run.add_argument(
        "--llm-fixture",
        default=None,
        help=(
            "đường dẫn tới JSON fixture cảu LLM response cho extract "
            "(mock — không cần .env). Ví dụ: data/fixtures/tc2_llm.json"
        ),
    )
    p_run.add_argument(
        "--resolve-fixture",
        default=None,
        help=(
            "đường dẫn tới JSON fixture của LLM pass-2 resolve (mock — không cần .env). "
            "Mặc định None → resolve chạy deterministic (đủ cho CI)."
        ),
    )
    p_run.add_argument(
        "--brief-fixture",
        default=None,
        help=(
            "đường dẫn tới JSON fixture của meeting brief (mock). "
            "Mặc định None → fixture mode bỏ brief; live mode luôn gọi LLM."
        ),
    )
    p_run.add_argument(
        "--chunk-size",
        type=int,
        default=80,
        help="số turns/chunk (default 80 — giảm xuống cho model context nhỏ)",
    )
    p_run.add_argument(
        "--overlap",
        type=int,
        default=10,
        help="số turns overlap giữa 2 chunk (default 10)",
    )

    p_eval = sub.add_parser("eval", help="chạy 5 ca → eval/results.json (P4)")
    p_eval.add_argument("--live", action="store_true", help="dùng LLM thật thay vì fixture")
    p_eval.add_argument(
        "--cases", default="tc1,tc2,tc3,tc4,tc5",
        help="comma-separated case ids (default M2 fixture set; thêm tc6 cho M3)",
    )
    p_eval.add_argument("--chunk-size", type=int, default=40)
    p_eval.add_argument("--overlap", type=int, default=10)
    p_eval.add_argument("--out", default="eval/results.json")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "eval":
        return cmd_eval(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())