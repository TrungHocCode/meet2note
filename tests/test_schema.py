"""
test_schema.py — Validate Pydantic v2 schema (taxonomy + R3 no_decision gate).

Mục tiêu: đảm bảo schema reject:
- evidence thiếu (Knowledge loại trừ)
- status sai
- no_decision=true không có Open Issue có next_step (R3)
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from pipeline.schema import (
    BriefOutcome,
    Decision,
    DecisionStatus,
    Evidence,
    Item,
    ItemTypeAdapter,
    Knowledge,
    Meeting,
    MeetingBrief,
    MeetingState,
    OpenIssue,
    Participant,
    Requirement,
    RoleInDiscussion,
    Stats,
    Task,
    TBD_SENTINEL,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def base_evidence() -> dict[str, Any]:
    return {
        "quote": "Vậy chốt B nhé, cả team đồng ý không?",
        "timestamp": "00:45:30",
        "speaker": "Lan",
        "turn": 7,
        "role_in_discussion": "decide",
    }


@pytest.fixture
def task_data(base_evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "T1",
        "what": "Gửi báo giá B cho khách",
        "owner": "Nam",
        "owner_source": "explicit",
        "due": "2026-10-12",
        "due_source": "explicit",
        "due_hint": None,
        "link_to_decision": "D1",
        "confidence": 0.9,
        "confidence_reason": "owner + due + link đều rõ trong transcript",
        "evidence": [base_evidence],
    }


# ──────────────────────────────────────────────────────────────────────
# Happy paths
# ──────────────────────────────────────────────────────────────────────


def test_decision_final_valid(base_evidence: dict[str, Any]) -> None:
    d = Decision(
        id="D1",
        content="Chốt phương án B",
        status="final",
        decided_by="Lan",
        reason="A rủi ro vượt 30%",
        supersedes=["D0"],
        objections=["em thấy A vẫn rẻ hơn ạ — Nam, 00:09:38"],
        confidence=0.85,
        confidence_reason="final rõ, supersedes đúng, evidence chốt cuối",
        evidence=[base_evidence],
    )
    assert d.type == "decision"
    assert d.status == "final"
    assert d.supersedes == ["D0"]
    assert len(d.objections) == 1


def test_task_full_owner_due(task_data: dict[str, Any]) -> None:
    t = Task(**task_data)
    assert t.type == "task"
    assert t.due == "2026-10-12"
    assert t.owner == "Nam"


def test_task_tbd_owner_and_due(base_evidence: dict[str, Any]) -> None:
    """R1: owner thiếu → TBD; R2: due mơ hồ → TBD + due_hint."""
    t = Task(
        id="T2",
        what="Anh em triển khai nhé",
        owner=TBD_SENTINEL,
        owner_source="tbd",
        due=TBD_SENTINEL,
        due_source="tbd",
        due_hint="sớm nhé",
        link_to_decision=None,
        confidence=0.3,
        confidence_reason="không rõ owner, due chỉ là 'sớm nhé'",
        evidence=[base_evidence],
    )
    assert t.owner == TBD_SENTINEL
    assert t.due == TBD_SENTINEL
    assert t.due_hint == "sớm nhé"


def test_open_issue_requires_next_step(base_evidence: dict[str, Any]) -> None:
    oi = OpenIssue(
        id="O1",
        content="Cần xác nhận scope mới từ KH",
        next_step="Hẹn call với KH để chốt scope trong tuần này",
        next_step_owner="Lan",
        confidence=0.7,
        confidence_reason="next_step cụ thể",
        evidence=[base_evidence],
    )
    assert oi.type == "open_issue"
    assert oi.next_step


def test_knowledge_no_evidence_required() -> None:
    """Knowledge KHÔNG bắt buộc evidence (taxonomy §2/§5)."""
    k = Knowledge(
        id="K1",
        content="Vendor X không support tiếng Việt — lưu ý cho dự án tương lai",
        context="Rút ra từ thảo luận chọn vendor",
        tags=["vendor", "lesson-learned"],
        confidence=0.8,
        confidence_reason="thông tin khẳng định rõ trong transcript",
        evidence=[],
    )
    assert k.type == "knowledge"
    assert k.evidence == []


def test_evidence_timestamp_validation() -> None:
    e = Evidence(
        quote="abc",
        timestamp="00:01:02",
        speaker="Nam",
        turn=1,
        role_in_discussion="info",
    )
    assert e.timestamp == "00:01:02"
    with pytest.raises(ValidationError):
        Evidence(
            quote="abc",
            timestamp="00:01:02.500",  # không khớp pattern HH:MM:SS
            speaker="Nam",
            turn=1,
            role_in_discussion="info",
        )


def test_meeting_envelope() -> None:
    m = Meeting(
        id="tc2",
        title="Chọn vendor CRM",
        date="2026-10-12",
        participants=[
            Participant(name="Lan", role="PM", aliases=["chị Lan"]),
            Participant(name="Nam", role="BA", aliases=["Nam"]),
        ],
        source_file="data/transcripts/tc2_atob.txt",
        pipeline_version="0.1.0",
    )
    assert m.date == "2026-10-12"
    assert len(m.participants) == 2


def test_item_discriminator_selects_decision(base_evidence: dict[str, Any]) -> None:
    """Discriminated union theo field `type`."""
    payload = {
        "id": "D1",
        "type": "decision",
        "content": "Chốt B",
        "status": "final",
        "decided_by": "Lan",
        "supersedes": [],
        "confidence": 0.8,
        "confidence_reason": "ok",
        "evidence": [base_evidence],
    }
    parsed = ItemTypeAdapter.validate_python(payload)
    assert isinstance(parsed, Decision)
    assert parsed.type == "decision"


def test_item_discriminator_selects_task(task_data: dict[str, Any]) -> None:
    payload = {**task_data, "type": "task"}
    parsed = ItemTypeAdapter.validate_python(payload)
    assert isinstance(parsed, Task)


# ──────────────────────────────────────────────────────────────────────
# Reject paths
# ──────────────────────────────────────────────────────────────────────


def test_decision_rejects_bad_status(base_evidence: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as exc:
        Decision(
            id="D1",
            content="x",
            status="approved",  # type: ignore[arg-type]
            confidence=0.5,
            confidence_reason="x",
            evidence=[base_evidence],
        )
    assert "status" in str(exc.value).lower()


def test_decision_requires_evidence() -> None:
    with pytest.raises(ValidationError) as exc:
        Decision(
            id="D1",
            content="Chốt B",
            decided_by="Lan",
            confidence=0.8,
            confidence_reason="ok",
            evidence=[],  # R5 — phải ≥1
        )
    assert "evidence" in str(exc.value).lower()


def test_task_requires_evidence() -> None:
    with pytest.raises(ValidationError) as exc:
        Task(
            id="T1",
            what="x",
            owner="Nam",
            owner_source="explicit",
            due="2026-10-12",
            due_source="explicit",
            confidence=0.8,
            confidence_reason="ok",
            evidence=[],
        )
    assert "evidence" in str(exc.value).lower()


def test_task_rejects_invalid_role(base_evidence: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Evidence(
            quote="x",
            timestamp="00:00:05",
            speaker="Nam",
            turn=1,
            role_in_discussion="yell",  # type: ignore[arg-type]
        )


def test_requirement_requires_origin(base_evidence: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Requirement(
            id="R1",
            content="KH muốn dashboard custom",
            raised_by="Kh",
            origin="external",  # type: ignore[arg-type]
            confidence=0.6,
            confidence_reason="x",
            evidence=[base_evidence],
        )


# ──────────────────────────────────────────────────────────────────────
# R3 — no_decision phải có ≥1 Open Issue có next_step
# ──────────────────────────────────────────────────────────────────────


def test_decision_final_requires_decided_by(base_evidence: dict[str, Any]) -> None:
    """R7: status='final' mà không có decided_by → reject."""
    with pytest.raises(ValidationError) as exc:
        Decision(
            id="D1",
            content="Chốt B",
            status="final",
            decided_by=None,  # thiếu người chốt
            confidence=0.8,
            confidence_reason="ok",
            evidence=[base_evidence],
        )
    assert "decided_by" in str(exc.value).lower()


def test_decision_discarded_no_decided_by_ok(base_evidence: dict[str, Any]) -> None:
    """status='discarded' KHÔNG yêu cầu decided_by (bị thay thế, không còn ai chốt)."""
    d = Decision(
        id="D0",
        content="Đề xuất A",
        status="discarded",
        decided_by=None,
        confidence=0.7,
        confidence_reason="đã bị D1 thay thế",
        evidence=[base_evidence],
    )
    assert d.decided_by is None


def test_meeting_state_r3_no_decision_needs_open_issue(
    base_evidence: dict[str, Any],
) -> None:
    """no_decision=true nhưng không có Open Issue → reject (R3)."""
    meeting = Meeting(
        id="tc3",
        title="Brainstorm vòng vo",
        date="2026-10-13",
        participants=[],
        source_file="data/transcripts/tc3_vague.txt",
        pipeline_version="0.1.0",
    )
    with pytest.raises(ValidationError) as exc:
        MeetingState(
            meeting=meeting,
            items=[],
            no_decision=True,
            stats={},
            known_limitations=[],
        )
    assert "no_decision" in str(exc.value).lower() or "r3" in str(exc.value).lower()


def test_meeting_state_r3_ok_with_open_issue(
    base_evidence: dict[str, Any],
) -> None:
    """no_decision=true + ≥1 Open Issue có next_step → OK."""
    meeting = Meeting(
        id="tc3",
        title="Brainstorm vòng vo",
        date="2026-10-13",
        participants=[],
        source_file="data/transcripts/tc3_vague.txt",
        pipeline_version="0.1.0",
    )
    oi = OpenIssue(
        id="O1",
        content="Chưa chốt scope",
        next_step="Hẹn call team tuần sau để chốt",
        next_step_owner="Lan",
        confidence=0.5,
        confidence_reason="chưa rõ ý kiến",
        evidence=[base_evidence],
    )
    state = MeetingState(
        meeting=meeting,
        items=[oi],
        no_decision=True,
        stats=Stats(by_type={"open_issue": 1}, items_total=1),
        known_limitations=[],
    )
    assert state.no_decision is True


def test_open_issue_system_generated_allows_empty_evidence() -> None:
    """O_SYS (system_generated) được miễn evidence (R5 + R3-fallback)."""
    oi = OpenIssue(
        id="O_SYS",
        content="Không xác định được trạng thái",
        next_step="Host kiểm tra lại",
        confidence=0.0,
        confidence_reason="system fallback",
        evidence=[],
        system_generated=True,
    )
    assert oi.system_generated is True


def test_open_issue_llm_requires_evidence() -> None:
    """OpenIssue từ LLM thiếu evidence → reject (R5)."""
    with pytest.raises(ValidationError):
        OpenIssue(
            id="O1",
            content="Chưa chốt",
            next_step="Hẹn lại",
            confidence=0.5,
            confidence_reason="mơ hồ",
            evidence=[],
        )


def test_decision_status_literal_values() -> None:
    """Kiểm tra DecisionStatus đúng 3 giá trị."""
    adapter = TypeAdapter(DecisionStatus)
    for v in ("final", "discarded", "proposal"):
        assert adapter.validate_python(v) == v
    with pytest.raises(ValidationError):
        adapter.validate_python("done")


def test_role_in_discussion_literal_values() -> None:
    adapter = TypeAdapter(RoleInDiscussion)
    for v in ("propose", "object", "decide", "confirm", "info"):
        assert adapter.validate_python(v) == v
    with pytest.raises(ValidationError):
        adapter.validate_python("nope")


def test_meeting_brief_valid() -> None:
    """Brief hợp lệ: problem + outcomes có ref_ids."""
    b = MeetingBrief(
        problem="Chọn vendor tích hợp CRM",
        outcomes=[BriefOutcome(text="Chốt B", ref_ids=["D1"])],
    )
    assert b.problem and b.outcomes[0].ref_ids == ["D1"]


def test_meeting_brief_problem_required() -> None:
    """problem rỗng → reject (brief vô nghĩa)."""
    with pytest.raises(ValidationError):
        MeetingBrief(problem="  ", outcomes=[])