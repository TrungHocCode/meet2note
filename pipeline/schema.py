"""
schema.py — Pydantic v2 single source of truth cho meet2note.

Mọi model trong project (pipeline, API, eval, golden) đều tham chiếu từ đây.
Đổi field = sửa prompt + UI + golden cùng lúc (theo AGENTS.md §5).

Nguồn hợp đồng: `docs/spec/taxonomy.md`, `docs/spec/io-formats.md`,
ADR-0003 (Pydantic là hợp đồng duy nhất).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

# ──────────────────────────────────────────────────────────────────────
# 1. Kiểu dùng chung
# ──────────────────────────────────────────────────────────────────────

# Timestamp HH:MM:SS theo io-formats §1.3 — chuẩn hoá, bỏ phần mmm.
TimeStamp = Annotated[
    str,
    StringConstraints(pattern=r"^\d{2}:\d{2}:\d{2}$", strip_whitespace=True),
]

# Date ISO YYYY-MM-DD — đầu vào deterministic cho entity-link ngày (R2).
IsoDate = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"),
]

# "TBD" sentinel cho owner/due không có trong transcript (R1) — trung thực, cấm bịa.
TBD_SENTINEL = "TBD"

SourceType = Literal["explicit", "inferred", "tbd"]
RoleInDiscussion = Literal["propose", "object", "decide", "confirm", "info"]
DecisionStatus = Literal["final", "discarded", "proposal"]
Severity = Literal["high", "medium", "low"]
Origin = Literal["customer", "internal", "partner"]
ItemType = Literal[
    "decision", "task", "blocker", "requirement", "open_issue", "knowledge"
]


# ──────────────────────────────────────────────────────────────────────
# 2. Evidence dùng chung (bắt buộc cho mọi item trừ Knowledge)
# ──────────────────────────────────────────────────────────────────────


class Evidence(BaseModel):
    """Bằng chứng trích từ transcript — quote NGUYÊN VĂN (cấm viết lại)."""

    model_config = ConfigDict(extra="forbid")

    quote: str = Field(
        ...,
        min_length=1,
        description="Trích nguyên văn từ transcript (R5 — fuzzy match >=85%).",
    )
    timestamp: TimeStamp = Field(
        ..., description="HH:MM:SS theo io-formats §1.3."
    )
    speaker: str = Field(
        ...,
        description="Tên sau khi chuẩn hoá theo participants (alias OK, ngoài = sai).",
    )
    turn: int = Field(..., ge=1, description="Số thứ tự lượt thoại, 1-indexed.")
    role_in_discussion: RoleInDiscussion = Field(
        ..., description="Vai trò của lượt thoại trong thảo luận."
    )


# ──────────────────────────────────────────────────────────────────────
# 3. Sáu loại Item (theo taxonomy §3)
# ──────────────────────────────────────────────────────────────────────


class Decision(BaseModel):
    """Quyết định: final duy nhất mỗi vấn đề, đề xuất cũ giữ trong `supersedes`."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="ID item (vd: D1, D0).")
    type: Literal["decision"] = "decision"
    content: str = Field(..., min_length=1)
    status: DecisionStatus
    decided_by: str | None = Field(
        default=None,
        description="Người chốt — null khi status=proposal/discarded.",
    )
    reason: str | None = Field(default=None, description="Lý do chốt (vd: 'rủi ro 30%').")
    supersedes: list[str] = Field(
        default_factory=list, description="ID các decision cũ bị thay thế (R4)."
    )
    objections: list[str] = Field(
        default_factory=list,
        description="Lưu phản đối — KHÔNG xoá tranh luận (R7).",
    )
    unresolved_reversal: bool = Field(
        default=False,
        description=(
            "R4 (P2): True khi phát hiện A→B→A hoặc 2 final cùng chủ đề khác "
            "content — resolve KHÔNG tự chọn (audit + Open Issue cho host)."
        ),
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_reason: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(
        ..., min_length=1, description="≥1 evidence — bắt buộc (R5)."
    )

    @field_validator("decided_by")
    @classmethod
    def _final_requires_decided_by(cls, v: str | None, info: Any) -> str | None:
        """R7 (audit): status='final' bắt buộc có decided_by (người chốt).

        proposal / discarded có thể null (chưa chốt / đã bị thay).
        """
        status = info.data.get("status")
        if status == "final" and not (v and v.strip()):
            raise ValueError(
                "Decision.status='final' yêu cầu decided_by (R7 — audit)."
            )
        return v


class Task(BaseModel):
    """Công việc: what / owner / due + liên kết decision."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    type: Literal["task"] = "task"
    what: str = Field(..., min_length=1)
    owner: str = Field(..., min_length=1, description="Tên owner hoặc 'TBD' (R1).")
    owner_source: SourceType
    due: IsoDate | Literal["TBD"] = Field(
        ..., description="ISO YYYY-MM-DD hoặc 'TBD' (R2)."
    )
    due_source: SourceType
    due_hint: str | None = Field(
        default=None,
        description="Chữ gốc mơ hồ giữ lại khi due=TBD (vd: 'sớm nhé').",
    )
    link_to_decision: str | None = Field(
        default=None, description="ID decision mà task này phục vụ."
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_reason: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(..., min_length=1)


class Blocker(BaseModel):
    """Vướng mắc / rủi ro — cần ai đó gỡ."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    type: Literal["blocker"] = "blocker"
    content: str = Field(..., min_length=1)
    needs_action_from: str = Field(
        ..., min_length=1, description="Người cần hành động hoặc 'TBD'."
    )
    severity: Severity
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_reason: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(..., min_length=1)


class Requirement(BaseModel):
    """Yêu cầu / phản hồi (kể cả từ KH)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    type: Literal["requirement"] = "requirement"
    content: str = Field(..., min_length=1)
    raised_by: str = Field(..., min_length=1)
    origin: Origin
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_reason: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(..., min_length=1)


class OpenIssue(BaseModel):
    """Chưa chốt — next_step bắt buộc (R3 khi no_decision)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    type: Literal["open_issue"] = "open_issue"
    content: str = Field(..., min_length=1)
    next_step: str = Field(..., min_length=1, description="BẮT BUỘC.")
    next_step_owner: str | None = Field(
        default=None, description="Người thực hiện next_step hoặc null/TBD."
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_reason: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Bắt buộc ≥1 trừ khi system_generated (R5 + R3-fallback).",
    )
    system_generated: bool = Field(
        default=False,
        description="True = verify.py tự tổng hợp khi LLM trắng final "
        "(R3-fallback). Item này luôn confidence thấp (đỏ) để host xử lý.",
    )

    @model_validator(mode="after")
    def _evidence_required_unless_system(self) -> "OpenIssue":
        """R5: OpenIssue từ LLM phải có evidence; system-fallback được miễn
        (nó không trích từ transcript nên không thể có quote)."""
        if not self.system_generated and not self.evidence:
            raise ValueError(
                "R5: open_issue (LLM) phải có ≥1 evidence."
            )
        return self


class Knowledge(BaseModel):
    """Tri thức / quy ước rút ra — không phải việc phải làm."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    type: Literal["knowledge"] = "knowledge"
    content: str = Field(..., min_length=1)
    context: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_reason: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Knowledge KHÔNG bắt buộc evidence (taxonomy §2/§5).",
    )


# Discriminated union theo field `type` — single field, snake_case string.
Item = Annotated[
    Union[Decision, Task, Blocker, Requirement, OpenIssue, Knowledge],
    Field(discriminator="type"),
]
ItemTypeAdapter = TypeAdapter(Item)


# ──────────────────────────────────────────────────────────────────────
# 4. Envelope — Meeting + MeetingState
# ──────────────────────────────────────────────────────────────────────


class Participant(BaseModel):
    """Thành viên họp — name + role + biến thể đại từ (em/anh/chị)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    aliases: list[str] = Field(
        default_factory=list,
        description="Biến thể gọi tên: 'em Nam', 'anh Lan', ...",
    )


class Meeting(BaseModel):
    """Metadata cuộc họp — entity-link deterministic từ `date` (R2)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    date: IsoDate = Field(..., description="YYYY-MM-DD, deterministic anchor.")
    participants: list[Participant] = Field(default_factory=list)
    source_file: str = Field(..., min_length=1)
    pipeline_version: str = Field(..., min_length=1)


class Stats(BaseModel):
    """Thống kê meeting — model tường minh thay dict phẳng (ADR: type-safe,
    API/P2 đọc trực tiếp không cần parse prefix `by_badge_*`)."""

    model_config = ConfigDict(extra="forbid")

    by_type: dict[str, int] = Field(default_factory=dict)
    items_total: int = Field(default=0, ge=0)
    by_badge: dict[str, int] = Field(default_factory=dict)


class MeetingState(BaseModel):
    """Output envelope: meeting + items + stats + known_limitations.

    Theo taxonomy §1 + io-formats §2.
    """

    model_config = ConfigDict(extra="forbid")

    meeting: Meeting
    items: list[Item] = Field(default_factory=list)
    no_decision: bool = Field(
        default=False,
        description="R3: True khi họp không chốt được gì.",
    )
    stats: Stats = Field(
        default_factory=Stats,
        description="Đếm theo type, tổng items, đếm theo confidence badge.",
    )
    known_limitations: list[str] = Field(
        default_factory=list,
        description="Hạn chế đã biết — trung thực, không che giấu (AGENTS.md §5).",
    )

    @field_validator("no_decision")
    @classmethod
    def _r3_no_decision_needs_open_issue(cls, v: bool, info: Any) -> bool:
        """R3: no_decision=true phải có ≥1 Open Issue có next_step.

        Validator nhẹ — kiểm tra sau khi `items` đã bind.
        """
        if not v:
            return v
        # info.data chỉ chứa field trước `no_decision`; items có thể chưa có.
        # Pydantic v2 chạy validator theo thứ tự khai báo; `items` khai trước
        # `no_decision` → đã có sẵn trong info.data.
        items = info.data.get("items") or []
        if not any(
            isinstance(i, OpenIssue) and i.next_step for i in items
        ):
            raise ValueError(
                "R3: no_decision=true yêu cầu ≥1 Open Issue có next_step."
            )
        return v


__all__ = [
    # common types
    "TimeStamp",
    "IsoDate",
    "TBD_SENTINEL",
    "SourceType",
    "RoleInDiscussion",
    "DecisionStatus",
    "Severity",
    "Origin",
    "ItemType",
    # models
    "Decision",
    "Task",
    "Blocker",
    "Requirement",
    "OpenIssue",
    "Knowledge",
    "Evidence",
    "Participant",
    "Meeting",
    "Stats",
    "MeetingState",
    # union
    "Item",
    "ItemTypeAdapter",
]