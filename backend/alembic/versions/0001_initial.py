"""0001 initial — 5 bảng P6a: users, meetings, runs, exports, refresh_tokens."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _jsonb():
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("date", sa.String(10), nullable=False, server_default=""),
        sa.Column("participants", _jsonb(), nullable=False, server_default="[]"),
        sa.Column("transcript_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("transcript_sha", sa.String(64), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default="upload"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(64),
                  sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("ts", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="done"),
        sa.Column("stats", _jsonb(), nullable=False, server_default="{}"),
        sa.Column("badges", _jsonb(), nullable=False, server_default="{}"),
        sa.Column("no_decision", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("state_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("confirmed_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("llm_log_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("exports")
    op.drop_table("runs")
    op.drop_table("meetings")
    op.drop_table("users")
