"""
backend/db_cli.py — Ops cho DB (P6a). Chạy độc lập, không cần server.

    python -m backend.db_cli create-admin --email a@x.com --password secret123
    python -m backend.db_cli migrate            # alembic upgrade head
    python -m backend.db_cli sync-db --owner a@x.com [--db-url ...]

sync-db quét runs/<meeting>/<ts>/state.json (+ meta/transcript tương ứng)
và upsert vào meetings/runs (gặp lại thì update, không duplicate).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.models import Base, Meeting, Run, User  # noqa: E402
from backend.db.security import hash_password  # noqa: E402
from backend.db.session import make_engine, session_scope  # noqa: E402


def _badge_counts(items: list[dict]) -> dict[str, int]:
    out = {"red": 0, "yellow": 0, "green": 0}
    for it in items:
        try:
            c = float(it.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            c = 0.0
        out["red" if c < 0.50 else "yellow" if c < 0.75 else "green"] += 1
    return out


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_transcript(root: Path, meeting_id: str) -> tuple[Path | None, str]:
    for base, source in (("transcripts", "fixture"), ("uploads", "upload")):
        d = root / "data" / base
        if not d.is_dir():
            continue
        for ext in (".txt", ".srt", ".docx"):
            for f in sorted(d.glob(f"{meeting_id}*{ext}")):
                return f, source
    return None, "unknown"


def _find_meta(root: Path, meeting_id: str) -> dict | None:
    for base in ("meta", "uploads"):
        d = root / "data" / base
        if base == "meta":
            p = d / f"{meeting_id}_meta.json"
        else:
            p = d / f"{meeting_id}_meta.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def cmd_create_admin(args: argparse.Namespace) -> int:
    email = args.email or os.environ.get("ADMIN_EMAIL", "")
    password = args.password or os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        print("thieu email/password (flag hoac ADMIN_EMAIL/ADMIN_PASSWORD)")
        return 2
    with session_scope(args.db_url) as s:
        existing = s.query(User).filter_by(email=email).one_or_none()
        if existing is not None:
            print(f"admin da ton tai: {email} (id={existing.id})")
            return 0
        user = User(email=email, password_hash=hash_password(password))
        s.add(user)
        s.flush()
        print(f"created admin: {email} (id={user.id})")
    return 0


def cmd_sync_db(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else ROOT
    runs_base = root / "runs"
    if not runs_base.is_dir():
        print(f"khong co runs/ o {runs_base}")
        return 2
    with session_scope(args.db_url) as s:
        owner = s.query(User).filter_by(email=args.owner_email).one_or_none()
        if owner is None:
            print(f"chua co user {args.owner_email} - chay create-admin truoc")
            return 2
        n_meetings = n_runs = 0
        for meet_dir in sorted(runs_base.iterdir()):
            if not meet_dir.is_dir():
                continue
            mid = meet_dir.name
            for ts_dir in sorted(d for d in meet_dir.iterdir() if d.is_dir()):
                state_path = ts_dir / "state.json"
                if not state_path.exists():
                    continue
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except ValueError as e:
                    print(f"bo qua {state_path}: JSON loi")
                    continue
                menv = state.get("meeting", {}) or {}
                meta = _find_meta(root, mid) or {}
                tpath, source = _find_transcript(root, mid)
                meeting = s.query(Meeting).filter_by(id=mid).one_or_none()
                if meeting is None:
                    meeting = Meeting(id=mid, owner_id=owner.id)
                    s.add(meeting)
                    n_meetings += 1
                meeting.owner_id = owner.id
                meeting.title = meta.get("title") or menv.get("title") or mid
                meeting.date = meta.get("date") or menv.get("date") or ""
                meeting.participants = (
                    meta.get("participants") or menv.get("participants") or []
                )
                meeting.transcript_path = (
                    str(tpath.relative_to(root)) if tpath else ""
                )
                meeting.transcript_sha = _sha_file(tpath) if tpath else ""
                meeting.source = source
                run = (
                    s.query(Run)
                    .filter_by(meeting_id=mid, ts=ts_dir.name)
                    .one_or_none()
                )
                items = state.get("items", []) or []
                stats = state.get("stats", {}) or {}
                by_type = (stats.get("by_type", {}) or {}) if isinstance(stats, dict) else {}
                if run is None:
                    run = Run(meeting_id=mid, ts=ts_dir.name)
                    s.add(run)
                    n_runs += 1
                run.status = "done"
                run.stats = {"by_type": by_type, "items_total": len(items)}
                run.badges = _badge_counts(items)
                run.no_decision = bool(state.get("no_decision", False))
                run.state_path = str(state_path.relative_to(root))
                confirmed = ts_dir / "confirmed_state.json"
                run.confirmed_path = (
                    str(confirmed.relative_to(root)) if confirmed.exists() else ""
                )
                llm_log = ts_dir / "llm_log.jsonl"
                run.llm_log_path = (
                    str(llm_log.relative_to(root)) if llm_log.exists() else ""
                )
    print(
        f"sync xong: {n_meetings} meetings moi, {n_runs} runs moi "
        f"(owner={args.owner_email})"
    )
    return 0


def cmd_migrate(_args: argparse.Namespace) -> int:
    """alembic upgrade head (dùng backend/alembic.ini)."""
    ini = ROOT / "backend" / "alembic.ini"
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"],
        cwd=str(ROOT),
    )
    return r.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="db_cli", description="Ops DB meet2note (P6a)")
    parser.add_argument("--db-url", default=None, help="ghi đè DATABASE_URL (test)")
    parser.add_argument("--root", default=None, help="project root (mặc định: repo này)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("create-admin", help="tạo admin (idempotent)")
    p_new.add_argument("--email", default=None)
    p_new.add_argument("--password", default=None)

    sub.add_parser("migrate", help="alembic upgrade head")

    p_sync = sub.add_parser("sync-db", help="quét runs/ upsert vào DB")
    p_sync.add_argument("--owner-email", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "create-admin":
        return cmd_create_admin(args)
    if args.cmd == "migrate":
        return cmd_migrate(args)
    if args.cmd == "sync-db":
        return cmd_sync_db(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
