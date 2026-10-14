"""Tests P6a — models, hashing, sync-db.

- Unit (mặc định): SQLite file tạm — nhanh, không cần Docker.
- Integration Postgres: chỉ chạy khi có TEST_DATABASE_URL
  (vd TEST_DATABASE_URL=postgresql+psycopg://meet2note:meet2note@localhost:5434/meet2note).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.db.models import Base, Export, Meeting, RefreshToken, Run, User
from backend.db.security import hash_password, verify_password
from backend.db.session import make_session_factory


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def session(sqlite_url: str):
    from sqlalchemy import create_engine

    engine = create_engine(sqlite_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(sqlite_url)
    s = factory()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _needs_pg():
    return pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="cần TEST_DATABASE_URL (docker compose up -d db)",
    )


# ── Models ──


def test_user_meeting_run_cascade(session) -> None:
    u = User(email="a@x.com", password_hash=hash_password("secret123"))
    session.add(u)
    session.flush()
    m = Meeting(
        id="tcX", owner_id=u.id, title="T", date="2026-10-13",
        participants=[], transcript_path="data/tcX.txt",
        transcript_sha="abc", source="fixture",
    )
    session.add(m)
    session.flush()
    r = Run(
        meeting_id="tcX", ts="20240101-000000", status="done",
        stats={"items_total": 1}, badges={"red": 0, "yellow": 0, "green": 1},
        no_decision=False, state_path="runs/tcX/x/state.json",
    )
    session.add(r)
    session.flush()
    e = Export(run_id=r.id, kind="minutes", path="runs/tcX/x/minutes.md")
    session.add(e)
    session.flush()

    assert session.query(Meeting).filter_by(id="tcX").one().owner_id == u.id
    assert session.query(Run).filter_by(meeting_id="tcX").count() == 1

    # Xoá user → cascade meetings → runs → exports
    session.delete(u)
    session.flush()
    assert session.query(Meeting).filter_by(id="tcX").count() == 0
    assert session.query(Run).filter_by(meeting_id="tcX").count() == 0
    assert session.query(Export).count() == 0


def test_email_unique(session) -> None:
    from sqlalchemy.exc import IntegrityError

    session.add(User(email="dup@x.com", password_hash=hash_password("secret123")))
    session.flush()
    session.add(User(email="dup@x.com", password_hash=hash_password("secret123")))
    with pytest.raises(IntegrityError):
        session.flush()


def test_password_hash_verify() -> None:
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True
    assert verify_password("sai", h) is False
    with pytest.raises(ValueError):
        hash_password("ngan")


def test_refresh_token_fields(session) -> None:
    from datetime import datetime, timedelta, timezone

    u = User(email="t@x.com", password_hash=hash_password("secret123"))
    session.add(u)
    session.flush()
    rt = RefreshToken(
        user_id=u.id, token_hash="h" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(rt)
    session.flush()
    assert rt.revoked is False


# ── sync-db ──


def _make_runs_tree(root: Path) -> None:
    run_dir = root / "runs" / "tcS" / "20240101-120000"
    run_dir.mkdir(parents=True)
    state = {
        "meeting": {
            "id": "tcS", "title": "Sync Test", "date": "2026-10-13",
            "participants": [{"name": "Lan", "role": "PM", "aliases": ["Lan"]}],
            "source_file": "x.txt", "pipeline_version": "t",
        },
        "items": [
            {"id": "D1", "type": "decision", "content": "Chốt X",
             "status": "final", "decided_by": "Lan",
             "confidence": 0.9, "confidence_reason": "ok", "evidence": []},
        ],
        "no_decision": False,
        "stats": {"by_type": {"decision": 1}, "items_total": 1},
        "known_limitations": [],
    }
    (run_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    (root / "data" / "transcripts").mkdir(parents=True)
    (root / "data" / "transcripts" / "tcS.txt").write_text(
        "[00:00:05] Lan: Chào.\n", encoding="utf-8"
    )


def test_sync_db_inserts_and_idempotent(tmp_path: Path) -> None:
    from backend import db_cli

    _make_runs_tree(tmp_path)
    db_url = f"sqlite:///{tmp_path / 'sync.db'}"
    from backend.db.models import Base as _Base
    from sqlalchemy import create_engine

    create_engine(db_url).connect().close()
    eng = create_engine(db_url)
    _Base.metadata.create_all(eng)

    from backend.db.security import hash_password as _hp
    from backend.db.session import session_scope
    from backend.db.models import User as _User

    with session_scope(db_url) as s:
        s.add(_User(email="owner@x.com", password_hash=_hp("secret123")))

    import argparse

    args = argparse.Namespace(
        root=str(tmp_path), db_url=db_url, owner_email="owner@x.com",
        cmd="sync-db",
    )
    assert db_cli.cmd_sync_db(args) == 0
    # Chạy lại → không duplicate (upsert theo (meeting_id, ts))
    assert db_cli.cmd_sync_db(args) == 0

    with session_scope(db_url) as s:
        from backend.db.models import Meeting as _M, Run as _R

        assert s.query(_M).filter_by(id="tcS").one().title == "Sync Test"
        assert s.query(_R).filter_by(meeting_id="tcS").count() == 1


def test_sync_db_requires_owner(tmp_path: Path) -> None:
    from backend import db_cli

    _make_runs_tree(tmp_path)
    db_url = f"sqlite:///{tmp_path / 'sync2.db'}"
    from sqlalchemy import create_engine

    from backend.db.models import Base as _Base

    create_engine(db_url)
    _Base.metadata.create_all(create_engine(db_url))

    import argparse

    args = argparse.Namespace(
        root=str(tmp_path), db_url=db_url, owner_email="nobody@x.com",
        cmd="sync-db",
    )
    assert db_cli.cmd_sync_db(args) == 2


# ── Postgres integration ──


@_needs_pg()
def test_pg_migration_and_crud() -> None:
    """Alembic + CRUD thật trên Postgres (docker)."""
    from sqlalchemy import create_engine

    url = os.environ["TEST_DATABASE_URL"]
    eng = create_engine(url)
    with eng.connect() as conn:
        tables = {r[0] for r in conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        )}
    for t in ("users", "meetings", "runs", "exports", "refresh_tokens"):
        assert t in tables, f"thiếu bảng {t} — chạy migrate chưa?"

    from backend.db.session import session_scope
    from backend.db.models import User as _U

    with session_scope(url) as s:
        u = _U(email="pgtest@x.com", password_hash=hash_password("secret123"))
        s.add(u)
        s.flush()
        assert u.id
        s.delete(u)
