"""
test_m3_knowledge_task.py — M3-D: Task ↔ Knowledge reclassify bằng code.

Triết lý: "LLM đề xuất, code kiểm chứng, con người chốt."

Test case:
1. LLM đặt Task "Quy ước discount >10% phải qua Lan" (không owner, không due)
   → M3-D phải reclassify thành Knowledge.
2. LLM đặt Knowledge "Gửi báo giá trước thứ 6" + có owner/due cụ thể
   → M3-D gợi ý chuyển thành Task qua limitation (KHÔNG tự đổi để giữ audit).

Kỳ vọng FAIL trên code M2 cũ (chưa có _reclassify_knowledge_task).
Kỳ vọng PASS trên code M3 mới.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.resolve import (
    _reclassify_knowledge_task,
    resolve,
    KNOWLEDGE_RE,
    ACTION_VERB_RE,
)


def _meta() -> dict:
    return {
        "id": "tc_know", "date": "2026-10-13",
        "participants": [
            {"name": "Lan", "role": "PM", "aliases": []},
            {"name": "Nam", "role": "BA", "aliases": []},
        ],
        "glossary": {},
    }


def test_m3_d_reclassify_quy_uoc_task_to_knowledge() -> None:
    """Task 'Quy ước discount >10% phải qua Lan' (no owner/due) → Knowledge."""
    items = [{
        "id": "K1", "type": "task",
        "what": "Quy ước discount >10% phải qua Lan duyệt",
        "owner": "TBD", "owner_source": "tbd",
        "due": "TBD", "due_source": "tbd",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.85, "confidence_reason": "quy ước",
        "evidence": [{
            "quote": "Quy ước discount >10% phải qua Lan duyệt.",
            "timestamp": "00:17:26", "speaker": "Lan",
            "turn": 1, "role_in_discussion": "info",
        }],
    }]
    limitations: list[str] = []
    _reclassify_knowledge_task(items, limitations)
    # M3-D: type → knowledge
    assert items[0]["type"] == "knowledge", (
        f"M3-D phải reclassify Task→Knowledge; got {items[0]['type']!r}"
    )
    # Limitation ghi vết
    assert any("M3-D" in lim and "task→knowledge" in lim for lim in limitations)


def test_m3_d_reclassify_lan_sau_task_to_knowledge() -> None:
    """Task 'Lần sau về vendor mới phải qua team review' (no owner/due) → Knowledge."""
    items = [{
        "id": "K2", "type": "task",
        "what": "Lần sau về vendor mới phải qua team review",
        "owner": "TBD", "owner_source": "tbd",
        "due": "TBD", "due_source": "tbd",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.8, "confidence_reason": "kinh nghiệm",
        "evidence": [{
            "quote": "Lần sau về vendor mới phải qua team review.",
            "timestamp": "00:18:02", "speaker": "Lan",
            "turn": 1, "role_in_discussion": "info",
        }],
    }]
    limitations: list[str] = []
    _reclassify_knowledge_task(items, limitations)
    assert items[0]["type"] == "knowledge"
    assert any("M3-D" in lim for lim in limitations)


def test_m3_d_no_reclassify_task_with_concrete_owner_due() -> None:
    """Task 'Gửi báo giá' + owner/due cụ thể → giữ nguyên Task (KHÔNG reclassify)."""
    items = [{
        "id": "T1", "type": "task",
        "what": "Gửi báo giá",
        "owner": "Nam", "owner_source": "explicit",
        "due": "2026-10-16", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.9, "confidence_reason": "rõ",
        "evidence": [{
            "quote": "Em gửi báo giá trước thứ 6.",
            "timestamp": "00:00:30", "speaker": "Nam",
            "turn": 1, "role_in_discussion": "info",
        }],
    }]
    limitations: list[str] = []
    _reclassify_knowledge_task(items, limitations)
    # Type giữ nguyên (Task)
    assert items[0]["type"] == "task"
    assert not any("M3-D" in lim for lim in limitations)


def test_m3_d_suggests_knowledge_to_task_via_limitation() -> None:
    """Knowledge 'Gửi báo giá' có động từ hành động + owner/due → gợi ý Task.

    KHÔNG tự đổi type (giữ audit) — chỉ ghi limitation cho host cân nhắc.
    """
    items = [{
        "id": "K1", "type": "knowledge",
        "content": "Gửi báo giá trước thứ 6",
        "context": "thông thường",
        "tags": [],
        "confidence": 0.9, "confidence_reason": "rõ",
        "evidence": [{
            "quote": "Em gửi báo giá trước thứ 6 nhé.",
            "timestamp": "00:00:30", "speaker": "Nam",
            "turn": 1, "role_in_discussion": "info",
        }],
        # Pretend LLM cũng set owner/due (mặc dù schema Knowledge không có)
        "owner": "Nam", "due": "2026-10-16",
    }]
    limitations: list[str] = []
    _reclassify_knowledge_task(items, limitations)
    # Type KHÔNG đổi (giữ audit)
    assert items[0]["type"] == "knowledge"
    # Nhưng limitation gợi ý
    assert any("M3-D gợi ý" in lim and "K1" in lim for lim in limitations)


def test_m3_d_knowledge_patterns_match() -> None:
    """Test các pattern KNOWLEDGE_RE cốt lõi đều match đúng."""
    patterns = [
        "quy ước discount",
        "lần sau về vendor",
        "kinh nghiệm dự án cũ",
        "nguyên tắc làm việc",
        "lưu ý chung",
        "policy team",
        "bài học rút ra",
        "sau này nhớ",
    ]
    for p in patterns:
        assert KNOWLEDGE_RE.search(p), f"Pattern not matched: {p!r}"


def test_m3_d_action_patterns_match() -> None:
    """Test các động từ hành động ACTION_VERB_RE cốt lõi đều match."""
    for v in ["gửi báo giá", "làm lead", "triển khai", "review",
              "kiểm tra", "fix bug", "setup môi trường", "draft đề xuất",
              "test plan"]:
        assert ACTION_VERB_RE.search(v), f"Action verb not matched: {v!r}"


def test_m3_d_via_resolve_pipeline() -> None:
    """Tích hợp: reclassify chạy trong resolve() — output có type=knowledge."""
    items_chunk = [{
        "id": "K1", "type": "task",
        "what": "Quy ước discount >10% phải qua Lan",
        "owner": "TBD", "owner_source": "tbd",
        "due": "TBD", "due_source": "tbd",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.85, "confidence_reason": "quy ước",
        "evidence": [{
            "quote": "Quy ước discount >10% phải qua Lan duyệt.",
            "timestamp": "00:00:30", "speaker": "Lan",
            "turn": 1, "role_in_discussion": "info",
        }],
    }]
    out = resolve(_meta(), [items_chunk])
    k1 = [x for x in out["items"] if x["id"] == "K1"][0]
    assert k1["type"] == "knowledge", (
        f"M3-D qua resolve(): got type={k1['type']!r}, expected 'knowledge'"
    )