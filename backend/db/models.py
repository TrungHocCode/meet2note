"""backend.db — SQLAlchemy models (P6a). Metadata vào DB, file ở yên trên disk."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Tài khoản đăng nhập (P6b dùng cho JWT; P6a chỉ seed + gắn owner)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    meetings: Mapped[list["Meeting"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )


class Meeting(Base):
    """1 cuộc họp = 1 transcript. Items chi tiết nằm trong state.json (không duplicate)."""

    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    date: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    participants: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=list)
    transcript_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    transcript_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    owner: Mapped[User] = relationship(back_populates="meetings")
    runs: Mapped[list["Run"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", passive_deletes=True
    )


class Run(Base):
    """1 lần chạy pipeline (1 meeting có nhiều runs theo thời gian)."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ts: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="done")
    stats: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=dict)
    badges: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=dict)
    no_decision: Mapped[bool] = mapped_column(default=False, nullable=False)
    state_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    confirmed_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    llm_log_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    meeting: Mapped[Meeting] = relationship(back_populates="runs")
    exports: Mapped[list["Export"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class Export(Base):
    """File đã xuất (để tải về + audit)."""

    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # minutes | csv
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="exports")


class RefreshToken(Base):
    """Phiên đăng nhập (chỉ lưu hash, không lưu token thô)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
