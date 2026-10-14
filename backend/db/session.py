"""Session factory — DATABASE_URL đổi được qua env/flag (P6a).

- Production/local: Postgres (`DATABASE_URL=postgresql+psycopg://...`).
- Test: SQLite file hoặc memory (`sqlite:///...`) qua `db_url` param.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def default_url() -> str:
    """Đọc env MỖI lần gọi (để test monkeypatch DATABASE_URL có tác dụng)."""
    return os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://meet2note:meet2note@localhost:5434/meet2note"
    )


# Giữ tên cũ cho code đã dùng (giá trị tại import — KHÔNG dùng cho logic mới).
DEFAULT_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://meet2note:meet2note@localhost:5434/meet2note"
)


def make_engine(db_url: str | None = None):
    """Tạo engine. SQLite memory cần StaticPool để giữ 1 connection."""
    url = db_url or default_url()
    if url.startswith("sqlite"):
        from sqlalchemy import event
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

        # SQLite tắt FK mặc định → bật để ondelete=CASCADE hoạt động như Postgres.
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _rec):  # noqa: ANN001,ANN202
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(db_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(db_url), expire_on_commit=False)


@contextmanager
def session_scope(db_url: str | None = None) -> Iterator[Session]:
    """Context manager: commit khi xong, rollback khi lỗi."""
    factory = make_session_factory(db_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
