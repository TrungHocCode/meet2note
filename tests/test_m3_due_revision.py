"""
test_m3_due_revision.py — M3-CR-DUE-REV: Deadline sửa giữa họp.

Triết lý: "LLM đề xuất, code kiểm chứng, con người chốt."

CR-giả định (PLAN_M3 §3.3): deadline sửa giữa họp → lấy lần chốt CUỐI,
giữ vết cũ→mới trong `due_hint`. Module độc lập, có cờ bật/tắt để thay khi
CR thật được chỉ định.

Test case:
1. Task lead integration có evidence thứ tự:
   - Turn 20: "thứ 6 (16-10)"
   - Turn 60: "dời sang thứ 2 (19-10)"
   - Turn 90: "dời sang thứ 2 tuần sau (21-10)"

Kỳ vọng:
- M2 cũ: due giữ nguyên 16-10, due_hint giữ "thứ 6".
- M3 mới: due=21-10 (lần cuối), due_hint có vết "16/10 → 21/10 (revised turn 90)".
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.resolve import (
    _apply_due_revision,
    _apply_owner_revision,
    resolve,
)


def _meta() -> dict:
    return {
        "id": "tc_cr", "date": "2026-10-14",
        "participants": [
            {"name": "Lan", "role": "PM", "aliases": []},
            {"name": "Hà", "role": "Dev", "aliases": []},
        ],
        "glossary": {},
    }


def _task_with_revision() -> dict:
    """Task lead integration có evidence thứ tự: 16-10 → 19-10 → 21-10."""
    return {
        "id": "T1", "type": "task",
        "what": "Lead integration",
        "owner": "Hà", "owner_source": "explicit",
        "due": "2026-10-16", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.9, "confidence_reason": "có sửa due",
        "evidence": [
            {"quote": "Deadline lead integration thứ 6 tuần này 16/10 nhé.",
             "timestamp": "00:00:30", "speaker": "Lan",
             "turn": 20, "role_in_discussion": "decide"},
            {"quote": "Mình bàn việc dời deadline lead integration sang 19/10 nhé.",
             "timestamp": "00:01:30", "speaker": "Lan",
             "turn": 60, "role_in_discussion": "propose"},
            {"quote": "Em đồng ý dời sang 19/10.",
             "timestamp": "00:01:45", "speaker": "Hà",
             "turn": 65, "role_in_discussion": "confirm"},
            {"quote": "Lead integration thì dời sang thứ 2 tuần sau 21/10 nhé.",
             "timestamp": "00:02:30", "speaker": "Lan",
             "turn": 90, "role_in_discussion": "decide"},
        ],
    }


def test_m3_due_revision_keeps_last_decision() -> None:
    """Deadline sửa 16→19→21 → due cuối = 21/10, due_hint có vết cũ→mới."""
    items = [_task_with_revision()]
    limitations: list[str] = []
    _apply_due_revision(items, _meta(), limitations)
    t1 = items[0]
    # M3-CR-DUE-REV: due = 21/10 (lần cuối turn 90)
    assert t1["due"] == "2026-10-21", (
        f"M3-CR-DUE-REV: expected due=2026-10-21, got {t1['due']!r}"
    )
    # due_hint chứa vết cũ→mới + revision turn
    assert t1["due_hint"], "due_hint phải giữ vết"
    assert "2026-10-16" in t1["due_hint"] or "16/10" in t1["due_hint"], (
        f"due_hint phải chứa due cũ; got {t1['due_hint']!r}"
    )
    assert "2026-10-21" in t1["due_hint"] or "21/10" in t1["due_hint"]
    assert "revised" in t1["due_hint"].lower() or "90" in t1["due_hint"]
    # Limitation ghi vết
    assert any("CR-DUE-REV" in lim and "T1" in lim for lim in limitations), (
        f"M3 phải ghi CR-DUE-REV limitation; got: {limitations}"
    )


def test_m3_due_revision_no_change_when_single_evidence() -> None:
    """Task chỉ có 1 evidence → CR không có gì để sửa, due giữ nguyên."""
    items = [{
        "id": "T1", "type": "task",
        "what": "Lead integration",
        "owner": "Hà", "owner_source": "explicit",
        "due": "2026-10-16", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.9, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Deadline lead integration thứ 6 tuần này 16/10 nhé.",
            "timestamp": "00:00:30", "speaker": "Lan",
            "turn": 20, "role_in_discussion": "decide",
        }],
    }]
    limitations: list[str] = []
    _apply_due_revision(items, _meta(), limitations)
    # due không đổi
    assert items[0]["due"] == "2026-10-16"
    # Không có limitation
    assert not any("CR-DUE-REV" in lim for lim in limitations)


def test_m3_due_revision_no_change_when_no_due_revision() -> None:
    """Task có evidence nhưng không có câu sửa due → giữ nguyên."""
    items = [{
        "id": "T1", "type": "task",
        "what": "Lead integration",
        "owner": "Hà", "owner_source": "explicit",
        "due": "2026-10-16", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.9, "confidence_reason": "ok",
        "evidence": [
            {"quote": "Deadline lead integration thứ 6 tuần này 16/10 nhé.",
             "timestamp": "00:00:30", "speaker": "Lan",
             "turn": 20, "role_in_discussion": "decide"},
            {"quote": "Dạ em đồng ý nhận task.",
             "timestamp": "00:00:35", "speaker": "Hà",
             "turn": 21, "role_in_discussion": "confirm"},
        ],
    }]
    limitations: list[str] = []
    _apply_due_revision(items, _meta(), limitations)
    assert items[0]["due"] == "2026-10-16"
    assert not any("CR-DUE-REV" in lim for lim in limitations)


def test_m3_due_revision_via_resolve_pipeline() -> None:
    """Tích hợp: CR chạy trong resolve() — output đúng due=21/10."""
    out = resolve(_meta(), [[_task_with_revision()]])
    t1 = [x for x in out["items"] if x["id"] == "T1"][0]
    assert t1["due"] == "2026-10-21", (
        f"M3-CR qua pipeline: due={t1['due']!r}, expected 2026-10-21"
    )
    assert "revised" in (t1["due_hint"] or "").lower() or "90" in (t1["due_hint"] or "")


def test_m3_due_revision_skips_non_task() -> None:
    """CR chỉ áp dụng cho type=task; Decision/Knowledge KHÔNG bị ảnh hưởng."""
    items = [
        {
            "id": "D1", "type": "decision",
            "content": "Chốt A",
            "status": "final", "decided_by": "Lan",
            "confidence": 0.9, "confidence_reason": "ok",
            "evidence": [{
                "quote": "Dời deadline A sang 21/10 nhé.",
                "timestamp": "00:01:00", "speaker": "Lan",
                "turn": 50, "role_in_discussion": "decide",
            }],
        },
        {
            "id": "K1", "type": "knowledge",
            "content": "Quy ước A",
            "tags": [],
            "confidence": 0.8, "confidence_reason": "ok",
            "evidence": [{
                "quote": "Dời sang 21/10 nhé.",
                "timestamp": "00:00:30", "speaker": "Lan",
                "turn": 50, "role_in_discussion": "info",
            }],
        },
    ]
    limitations: list[str] = []
    _apply_due_revision(items, _meta(), limitations)
    # Decision/Knowledge không bị đụng
    assert items[0]["type"] == "decision"
    assert items[1]["type"] == "knowledge"
    # Không có CR-DUE-REV limitation cho non-task
    assert not any("CR-DUE-REV" in lim for lim in limitations)


def test_m3_owner_revision_keeps_last_owner() -> None:
    """CR-OWNER-REV: đổi owner giữa họp (Hà → Lan) → lấy người cuối + ghi vết."""
    items = [{
        "id": "T1", "type": "task",
        "what": "Review hợp đồng thanh toán",
        "owner": "Hà", "owner_source": "explicit",
        "due": "2026-10-16", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.9, "confidence_reason": "giao rõ",
        "evidence": [
            {"quote": "Hà review hợp đồng thanh toán trước thứ 6 nhé.",
             "timestamp": "00:01:00", "speaker": "Lan",
             "turn": 15, "role_in_discussion": "decide"},
            {"quote": "Phần hợp đồng này chuyển cho Lan phụ trách luôn nhé.",
             "timestamp": "00:05:00", "speaker": "Hà",
             "turn": 45, "role_in_discussion": "decide"},
        ],
    }]
    limitations: list[str] = []
    _apply_owner_revision(items, _meta(), limitations)
    assert items[0]["owner"] == "Lan"
    assert "owner revised Hà→Lan" in items[0]["confidence_reason"]
    assert any("CR-OWNER-REV" in lim and "Hà → Lan" in lim for lim in limitations)