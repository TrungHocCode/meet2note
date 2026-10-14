"""
test_resolve.py — P2: trọng tài xuyên chunk + entity-link deterministic.

Phủ (theo P2 yêu cầu):
- Merge trùng khít (cùng id + cùng evidence) → 1, ghi merged_ids.
- Same-id conflict: majority chunks thắng; tie → latest evidence role=decide thắng
  (case P1: D1.final @05:46 (chunk 0) thua @45:30 (chunk 1+2)).
- Nối supersedes xuyên chunk: proposal chunk đầu + final chunk cuối khác id.
- A→B→A / 2 final cùng chủ đề → flag unresolved_reversal + Open Issue.
- Entity-link due: thứ N/tuần sau/ngày N/M/cuối tháng → ISO từ meeting.date.
- parse_relative_date độc lập + regression.
- LLM pass-2 optional (mock qua llm_fn) — test chạy được không phụ thuộc key.
- extract cập nhật: trả thêm `chunk_items` per-chunk (intra-chunk dedup).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from pipeline.extract import extract
from pipeline.resolve import (
    parse_relative_date,
    resolve,
)
from pipeline.schema import TBD_SENTINEL


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def tc2_meta() -> dict[str, Any]:
    return {
        "id": "tc2",
        "title": "Chọn vendor CRM",
        "date": "2026-10-12",
        "participants": [
            {"name": "Lan", "role": "PM", "aliases": ["chị Lan"]},
            {"name": "Nam", "role": "BA", "aliases": ["em Nam"]},
            {"name": "Hà", "role": "Dev", "aliases": ["em Hà"]},
        ],
        "glossary": {},
    }


# Helper: tạo 1 item Decision giả định
def _d(
    iid: str,
    content: str,
    status: str,
    *,
    decided_by: str | None = None,
    ts: str = "00:00:00",
    speaker: str = "Lan",
    turn: int = 1,
    role: str = "decide",
    reason: str | None = None,
    supersedes: list[str] | None = None,
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "id": iid,
        "type": "decision",
        "content": content,
        "status": status,
        "decided_by": decided_by,
        "reason": reason,
        "supersedes": supersedes or [],
        "objections": [],
        "confidence": confidence,
        "confidence_reason": "ok",
        "evidence": [{
            "quote": content,
            "timestamp": ts,
            "speaker": speaker,
            "turn": turn,
            "role_in_discussion": role,
        }],
    }


def _o(
    iid: str,
    content: str,
    *,
    ts: str = "00:00:00",
    speaker: str = "Lan",
    turn: int = 1,
    role: str = "info",
) -> dict[str, Any]:
    return {
        "id": iid,
        "type": "open_issue",
        "content": content,
        "next_step": "Host xử lý",
        "next_step_owner": "TBD",
        "confidence": 0.5,
        "confidence_reason": "ok",
        "evidence": [{
            "quote": content,
            "timestamp": ts,
            "speaker": speaker,
            "turn": turn,
            "role_in_discussion": role,
        }],
    }


# ──────────────────────────────────────────────────────────────────────
# 1. Merge trùng khít (cùng id + cùng evidence) → 1
# ──────────────────────────────────────────────────────────────────────


def test_resolve_merge_exact_duplicates_across_chunks() -> None:
    """Cùng id + cùng evidence ở 2 chunks → gộp 1, ghi merged_ids / limitation."""
    d1 = _d("D1", "Chốt B", "final",
            decided_by="Lan", ts="00:45:30", speaker="Lan",
            turn=65, reason="rủi ro 30%")
    chunk_items = [
        [d1],  # chunk 0
        [d1],  # chunk 1 — cùng evidence (giống hệt)
    ]
    out = resolve({"id": "tc2", "date": "2026-10-12", "participants": []},
                  chunk_items)
    assert len(out["items"]) == 1
    assert out["items"][0]["id"] == "D1"
    # Ghi limitation để audit
    assert any("merge" in lim and "D1" in lim for lim in out["known_limitations"])


# ──────────────────────────────────────────────────────────────────────
# 2. Same-id conflict — case P1 thật: D1 chunk 0 (@05:46) thua D1 chunk 1+2 (@45:30)
# ──────────────────────────────────────────────────────────────────────


def test_resolve_same_id_conflict_latest_decide_wins(tc2_meta) -> None:
    """P1 BUG — bug: D1 được trích ở chunk 0 với evidence @05:45 (đoán sớm)
    và ở chunk 1+2 với evidence @45:30 (đúng câu chốt cuối).

    Hòa majority (1 vs 1)? Không — 2 bản ở chunk 1+2 cùng evidence signature
    → majority = chunk 1+2 (2 votes) thắng chunk 0 (1 vote).

    Quy tắc dự phòng: cùng majority → role=decide + ts muộn nhất thắng.
    Ở đây cả 3 bản đều có role=decide, ts @05:46 vs @45:30+@45:30 → @45:30 thắng.
    Bản thua ghi limitations (audit, KHÔNG xoá).
    """
    d1_chunk0 = _d("D1", "Chọn phương án B: bên Y với gói premium có SLA 99.9% và support tiếng Việt",
                   "final", decided_by="Lan",
                   ts="00:05:46", speaker="Lan", turn=29, role="decide",
                   reason="Giá cao hơn A nhưng giảm rủi ro")
    d1_chunk1 = _d("D1", "Chốt phương án B (vendor Y, gói premium, SLA 99.9%, support tiếng Việt)",
                   "final", decided_by="Lan",
                   ts="00:45:30", speaker="Lan", turn=65, role="decide",
                   reason="A rủi ro vượt 30%")
    d1_chunk2 = _d("D1", "Chốt phương án B (vendor Y, gói premium, SLA 99.9%, support tiếng Việt)",
                   "final", decided_by="Lan",
                   ts="00:45:30", speaker="Lan", turn=65, role="decide",
                   reason="A rủi ro vượt 30%")
    chunk_items = [[d1_chunk0], [d1_chunk1], [d1_chunk2]]
    out = resolve(tc2_meta, chunk_items)
    # Sau resolve: chỉ 1 bản D1, là bản @45:30 (winner)
    d1_items = [i for i in out["items"] if i["id"] == "D1"]
    assert len(d1_items) == 1
    winner = d1_items[0]
    assert winner["evidence"][0]["timestamp"] == "00:45:30"
    assert winner["evidence"][0]["turn"] == 65
    # Bản thua (@05:46) ghi limitation
    assert any("same-id conflict" in lim and "D1" in lim for lim in out["known_limitations"])


def test_resolve_same_id_conflict_majority_wins_over_lone_opponent() -> None:
    """2 chunks cùng evidence thắng 1 chunk khác evidence (majority 2:1)."""
    base_item = {
        "id": "D1", "type": "decision", "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "reason": "rủi ro 30%", "supersedes": [],
        "objections": [], "confidence": 0.9,
        "confidence_reason": "ok",
    }
    d1_chunk0 = {
        **base_item,
        "evidence": [{"quote": "Chốt B nhé.", "timestamp": "00:05:46",
                      "speaker": "Lan", "turn": 29, "role_in_discussion": "decide"}],
    }
    d1_chunk1 = {
        **base_item,
        "evidence": [{"quote": "Vậy chốt B nhé, cả team đồng ý không?",
                      "timestamp": "00:45:30", "speaker": "Lan",
                      "turn": 65, "role_in_discussion": "decide"}],
    }
    d1_chunk2 = {  # cùng evidence với chunk 1 → majority 2:1 thắng
        **base_item,
        "evidence": [{"quote": "Vậy chốt B nhé, cả team đồng ý không?",
                      "timestamp": "00:45:30", "speaker": "Lan",
                      "turn": 65, "role_in_discussion": "decide"}],
    }
    chunk_items = [[d1_chunk0], [d1_chunk1], [d1_chunk2]]
    out = resolve({"id": "tc2", "date": "2026-10-12", "participants": []},
                  chunk_items)
    d1_items = [i for i in out["items"] if i["id"] == "D1"]
    assert len(d1_items) == 1
    assert d1_items[0]["evidence"][0]["timestamp"] == "00:45:30"


# ──────────────────────────────────────────────────────────────────────
# 3. Nối supersedes xuyên chunk
# ──────────────────────────────────────────────────────────────────────


def test_resolve_link_supersedes_xuyen_chunk() -> None:
    """Proposal A ở chunk 0 + Final B ở chunk 1 khác id → link supersedes."""
    d0 = _d("D0", "Đề xuất phương án A (bên X)",
            "discarded", ts="00:08:04", speaker="Nam", turn=39,
            role="propose")
    d1 = _d("D1", "Chốt phương án B (vendor Y gói premium SLA 99.9%)",
            "final", decided_by="Lan",
            ts="00:45:30", speaker="Lan", turn=65, role="decide",
            reason="A rủi ro 30%")
    # d1 không có supersedes — resolve phải tự link
    assert d1["supersedes"] == []
    chunk_items = [[d0], [d1]]
    out = resolve({"id": "tc2", "date": "2026-10-12", "participants": []},
                  chunk_items)
    d1_after = [i for i in out["items"] if i["id"] == "D1"][0]
    assert "D0" in d1_after["supersedes"]
    assert any("link_supersedes" in lim and "D1" in lim and "D0" in lim
               for lim in out["known_limitations"])


# ──────────────────────────────────────────────────────────────────────
# 4. A→B→A / 2 final cùng chủ đề khác content → unresolved_reversal
# ──────────────────────────────────────────────────────────────────────


def test_resolve_unresolved_reversal_two_finals() -> None:
    """2 final cùng chủ đề khác content → flag unresolved_reversal + O_REV."""
    d_a = _d("D_A", "Chốt dùng Spring Boot cho module thanh toán",
             "final", decided_by="Lan",
             ts="00:08:34", speaker="Lan", turn=37, role="decide")
    d_b = _d("D_B", "Chốt dùng FastAPI cho module thanh toán Python",
             "final", decided_by="Lan",
             ts="00:13:54", speaker="Lan", turn=53, role="decide")
    chunk_items = [[d_a], [d_b]]
    out = resolve({"id": "tc5", "date": "2026-10-14", "participants": []},
                  chunk_items)
    # Cả 2 flag unresolved_reversal
    finals = [i for i in out["items"] if i["type"] == "decision"]
    assert all(f.get("unresolved_reversal") is True for f in finals)
    # Open Issue cho host
    oi = [i for i in out["items"] if i["type"] == "open_issue"]
    assert len(oi) >= 1
    assert any("O_REV" in i["id"] for i in oi)
    assert any(i["system_generated"] is True for i in oi)
    # Limitation ghi rõ
    assert any("unresolved_reversal" in lim for lim in out["known_limitations"])


def test_resolve_unresolved_reversal_a_to_b_to_a() -> None:
    """Evidence theo thứ tự A → B → A → cùng id Decision 'final' với evidence
    khác content qua các turn → flag unresolved_reversal.

    Case A→B→A thật (tc5): cùng Decision 'Tech Stack' thay đổi 3 lần.
    Heuristic R1: ≥ 3 decide evidence + KHÔNG có cặp nào chia sẻ token chính
    → reversal.
    """
    # 1 Decision duy nhất có evidence chain: A (@08:34) → B (@13:54) → A (@15:46)
    d_tech = {
        "id": "D_TECH", "type": "decision",
        "content": "Chốt tech stack module thanh toán",
        "status": "final", "decided_by": "Lan",
        "reason": "thay đổi nhiều lần", "supersedes": [],
        "objections": [], "confidence": 0.5,
        "confidence_reason": "đảo chiều",
        "evidence": [
            {"quote": "CHỐT Spring Boot nhé.", "timestamp": "00:08:34",
             "speaker": "Lan", "turn": 37, "role_in_discussion": "decide"},
            {"quote": "CHUYỂN sang FastAPI nhé.", "timestamp": "00:13:54",
             "speaker": "Lan", "turn": 53, "role_in_discussion": "decide"},
            {"quote": "Vũ quay lại Spring Boot.", "timestamp": "00:15:46",
             "speaker": "Lan", "turn": 61, "role_in_discussion": "decide"},
        ],
    }
    chunk_items = [[d_tech]]
    out = resolve({"id": "tc5", "date": "2026-10-14", "participants": []},
                  chunk_items)
    # Có ít nhất 1 final → unresolved_reversal flag
    finals = [i for i in out["items"] if i["type"] == "decision"]
    assert any(f.get("unresolved_reversal") is True for f in finals)
    # Có Open Issue cho host
    assert any(i["type"] == "open_issue" for i in out["items"])


def test_resolve_unresolved_reversal_no_false_positive_on_two_decides() -> None:
    """2 decide evidence cho CÙNG chủ đề (Jaccard cao) → KHÔNG flag reversal.

    Case tc4: D1 'Dùng VNPay' có 2 evidence quyết định cùng chiều → heuristic
    R1 phải bỏ qua (không phải A→B→A).
    """
    d1 = {
        "id": "D1", "type": "decision",
        "content": "Dùng VNPay cho phase 1",
        "status": "final", "decided_by": "Lan",
        "reason": "KH nội địa", "supersedes": [],
        "objections": [], "confidence": 0.85,
        "confidence_reason": "chốt rõ",
        "evidence": [
            {"quote": "Mình hướng về VNPay nhé.", "timestamp": "00:02:42",
             "speaker": "Lan", "turn": 17, "role_in_discussion": "decide"},
            {"quote": "Chốt dùng VNPay cho phase lập trình.", "timestamp": "00:03:06",
             "speaker": "Lan", "turn": 19, "role_in_discussion": "decide"},
        ],
    }
    chunk_items = [[d1]]
    out = resolve({"id": "tc4", "date": "2026-10-15", "participants": []},
                  chunk_items)
    finals = [i for i in out["items"] if i["type"] == "decision"]
    # KHÔNG flag reversal — 2 decide quotes có Jaccard ≥ 0.3 (cùng chủ đề)
    assert not any(f.get("unresolved_reversal") is True for f in finals)
    # Không tạo O_REV cho false positive
    assert not any(i["id"].startswith("O_REV") for i in out["items"])


# ──────────────────────────────────────────────────────────────────────
# 5. parse_relative_date — độc lập + regression
# ──────────────────────────────────────────────────────────────────────


def test_parse_thu2_returns_monday() -> None:
    # 2026-10-12 là Monday
    iso, src = parse_relative_date("thứ 2", "2026-10-12")
    assert iso == "2026-10-19"  # tuần sau (không phải hôm nay)
    assert src == "inferred"


def test_parse_thu6_returns_friday() -> None:
    # 2026-10-15 là Thursday → thứ 6 tuần này = 2026-10-16
    iso, src = parse_relative_date("thứ 6 tuần này", "2026-10-15")
    assert iso == "2026-10-16"
    assert src == "inferred"


def test_parse_tuan_sau_returns_next_monday() -> None:
    # 2026-10-13 (Tue) → tuần sau = Monday tuần sau = 2026-10-19
    iso, src = parse_relative_date("tuần sau", "2026-10-13")
    assert iso == "2026-10-19"
    assert src == "inferred"


def test_parse_cuoi_thang_returns_last_day() -> None:
    iso, src = parse_relative_date("cuối tháng", "2026-10-13")
    assert iso == "2026-10-31"
    assert src == "inferred"


def test_parse_ngay_d_m_returns_iso() -> None:
    iso, src = parse_relative_date("ngày 5/11", "2026-10-13")
    assert iso == "2026-11-05"
    assert src == "inferred"


def test_parse_sau_n_ngay() -> None:
    iso, src = parse_relative_date("sau 5 ngày", "2026-10-13")
    assert iso == "2026-10-18"
    assert src == "inferred"


def test_parse_unrecognized_returns_none() -> None:
    iso, src = parse_relative_date("xyz không hiểu", "2026-10-13")
    assert iso is None
    assert src == "tbd"


def test_parse_empty_returns_none() -> None:
    iso, src = parse_relative_date("", "2026-10-13")
    assert iso is None
    assert src == "tbd"


# ──────────────────────────────────────────────────────────────────────
# 6. Entity-link due chạy trong resolve
# ──────────────────────────────────────────────────────────────────────


def test_resolve_entity_link_due_thu6_tuan_nay() -> None:
    """Task có due='thứ 6 tuần này' + meeting.date=2026-10-15 (Thu)
    → resolve đổi thành due='2026-10-16', source='inferred'."""
    t1 = {
        "id": "T1", "type": "task",
        "what": "Lead integration",
        "owner": "Hà", "owner_source": "explicit",
        "due": "thứ 6 tuần này", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.85, "confidence_reason": "rõ",
        "evidence": [{
            "quote": "Deadline thứ 6 tuần này nhé.",
            "timestamp": "00:03:54", "speaker": "Lan",
            "turn": 1, "role_in_discussion": "info",
        }],
    }
    chunk_items = [[t1]]
    out = resolve({"id": "tc4", "date": "2026-10-15",
                   "participants": [
                       {"name": "Hà", "role": "Dev", "aliases": ["em Hà"]},
                   ]},
                  chunk_items)
    t1_out = out["items"][0]
    assert t1_out["due"] == "2026-10-16"
    assert t1_out["due_source"] == "inferred"


def test_resolve_entity_link_due_cuoi_thang() -> None:
    """Task có due='cuối tháng' + meeting.date=2026-10-13 → 2026-10-31."""
    t1 = {
        "id": "T1", "type": "task",
        "what": "Test plan", "owner": "Nam",
        "owner_source": "explicit",
        "due": "cuối tháng", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.85, "confidence_reason": "rõ",
        "evidence": [],
    }
    chunk_items = [[t1]]
    out = resolve({"id": "tc4", "date": "2026-10-13",
                   "participants": []}, chunk_items)
    assert out["items"][0]["due"] == "2026-10-31"


def test_resolve_entity_link_due_som_nhe_kept_as_tbd() -> None:
    """Task có due='sớm nhé' → giữ TBD + due_hint='sớm nhé' (R2)."""
    t1 = {
        "id": "T1", "type": "task",
        "what": "Triển khai", "owner": "Nam",
        "owner_source": "explicit",
        "due": "sớm nhé", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.85, "confidence_reason": "ok",
        "evidence": [],
    }
    chunk_items = [[t1]]
    out = resolve({"id": "tc3", "date": "2026-10-13",
                   "participants": []}, chunk_items)
    t1_out = out["items"][0]
    assert t1_out["due"] == TBD_SENTINEL
    assert t1_out["due_hint"] == "sớm nhé"
    assert t1_out["due_source"] == "tbd"


# ──────────────────────────────────────────────────────────────────────
# 7. extract() cập nhật — trả thêm chunk_items per-chunk
# ──────────────────────────────────────────────────────────────────────


def test_extract_returns_chunk_items_per_chunk(tc2_meta) -> None:
    """extract() trả `chunk_items: list[list[dict]]` per-chunk (P2).

    chunk_items[i] có thể có cùng item id với chunk_items[j] khác
    (cross-chunk dedup DO resolve xử, không phải extract).
    """
    turns = [{"turn": i, "t_start": f"00:00:{i:02d}",
              "t_end": f"00:00:{i:02d}", "speaker": "Lan",
              "text": f"Turn {i}"} for i in range(1, 51)]

    def llm_fn(messages):
        return json.dumps({"items": [{
            "id": "D1", "type": "decision", "content": "x",
            "status": "final", "decided_by": "Lan",
            "confidence": 0.8, "confidence_reason": "ok",
            "evidence": [{
                "quote": "Turn 10", "timestamp": "00:00:10",
                "speaker": "Lan", "turn": 10,
                "role_in_discussion": "decide",
            }],
        }]})

    result = extract(tc2_meta, turns, llm_fn=llm_fn, chunk_size=20, overlap=5)
    assert "chunk_items" in result
    # 50 turns / chunk_size=20 / step=15 → 4 chunks
    assert len(result["chunk_items"]) >= 2
    # Mỗi chunk có list (có thể empty nếu LLM invalid)
    assert all(isinstance(c, list) for c in result["chunk_items"])
    # items (backward compat) đã dedup xuyên chunk → 1.
    # chunk_items giữ per-chunk (intra-chunk dedup) → 1 mỗi chunk, tổng ≥ 1.
    assert len(result["items"]) == 1
    assert sum(len(c) for c in result["chunk_items"]) >= 1


def test_extract_intra_chunk_dedup_keeps_first(tc2_meta) -> None:
    """Trong 1 chunk, item trùng id → giữ bản đầu (khác cross-chunk P1)."""
    turns = [{"turn": i, "t_start": f"00:00:{i:02d}",
              "t_end": f"00:00:{i:02d}", "speaker": "Lan",
              "text": f"Turn {i}"} for i in range(1, 6)]
    item_first = {
        "id": "D1", "type": "decision", "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Turn 1", "timestamp": "00:00:01",
            "speaker": "Lan", "turn": 1, "role_in_discussion": "decide",
        }],
    }
    item_dup = {**item_first, "content": "Chốt B lần 2"}

    def llm_fn(messages):
        return json.dumps({"items": [item_first, item_dup]})

    result = extract(tc2_meta, turns, llm_fn=llm_fn)
    # items: 1 (dedup)
    assert len(result["items"]) == 1
    assert result["items"][0]["content"] == "Chốt B"
    # chunk_items: 1 chunk, 1 item
    assert len(result["chunk_items"]) == 1
    assert len(result["chunk_items"][0]) == 1


# ──────────────────────────────────────────────────────────────────────
# 8. LLM pass-2 (optional) — không ảnh hưởng khi thiếu
# ──────────────────────────────────────────────────────────────────────


def test_resolve_works_without_llm_fn() -> None:
    """resolve() không cần llm_fn — deterministic đủ cho CI."""
    d1 = _d("D1", "Chốt phương án B vendor Y gói premium SLA 99.9%",
            "final", decided_by="Lan",
            ts="00:45:30", speaker="Lan", turn=65, role="decide")
    d0 = _d("D0", "Đề xuất phương án A vendor X rẻ hơn",
            "discarded", ts="00:08:04", speaker="Nam",
            turn=39, role="propose")
    chunk_items = [[d0], [d1]]
    out = resolve({"id": "tc2", "date": "2026-10-12", "participants": []},
                  chunk_items)
    # Không có LLM fail / không crash
    assert "items" in out
    assert "known_limitations" in out


def test_resolve_with_mock_llm_pass2_applies_role() -> None:
    """LLM pass-2 mock trả hints role_in_discussion → resolve áp dụng."""
    d1 = {
        "id": "D1", "type": "decision", "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "reason": "rủi ro 30%", "supersedes": [],
        "objections": [], "confidence": 0.9,
        "confidence_reason": "ok",
        "evidence": [{
            "quote": "Chốt B nhé.", "timestamp": "00:00:30",
            "speaker": "Lan", "turn": 1,
            "role_in_discussion": "info",  # resolve / verify đã normalize về "info"
        }],
    }
    chunk_items = [[d1]]

    # Mock LLM pass-2: trả hint sửa role_in_discussion từ info → decide
    def mock_llm(messages):
        return json.dumps({"items": [{
            "id": "D1", "type": "decision",
            "evidence": [{
                "quote": "Chốt B nhé.", "timestamp": "00:00:30",
                "speaker": "Lan", "turn": 1,
                "role_in_discussion": "decide",
            }],
        }]})

    out = resolve({"id": "tc2", "date": "2026-10-12", "participants": []},
                  chunk_items, llm_fn=mock_llm)
    d1_out = out["items"][0]
    assert d1_out["evidence"][0]["role_in_discussion"] == "decide"


# ──────────────────────────────────────────────────────────────────────
# 9. Integration — extract + resolve → verify flow (tc2 happy path)
# ──────────────────────────────────────────────────────────────────────


def test_resolve_then_verify_tc2_d1_evidence_45_30(monkeypatch, tmp_path) -> None:
    """Smoke: dùng fixture tc2_llm.json → extract → resolve → D1 evidence @45:30.

    Fixture có 1 chunk (D0, D1, T1, T3) → resolve deterministic không cần cross-chunk,
    D1 giữ nguyên @45:30. Verify áp công thức confidence cuối.
    """
    from pathlib import Path
    from pipeline.cli import _make_fixture_llm
    from pipeline.verify import verify_state
    from pipeline.schema import Meeting, Participant

    fixture_path = Path("data/fixtures/tc2_llm.json")
    if not fixture_path.exists():
        pytest.skip(f"fixture chưa có: {fixture_path}")
    llm_fn = _make_fixture_llm(fixture_path)

    turns = [
        {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
         "speaker": "Lan", "text": "Chào cả nhóm."},
        {"turn": 39, "t_start": "00:08:04", "t_end": "00:08:04",
         "speaker": "Nam",
         "text": "Em đề xuất phương án A, bên X rẻ hơn 20%."},
        {"turn": 65, "t_start": "00:45:30", "t_end": "00:45:30",
         "speaker": "Lan",
         "text": "A rủi ro vượt 30% nếu phát sinh. Vậy chốt B nhé, cả team đồng ý không?"},
        {"turn": 71, "t_start": "00:46:32", "t_end": "00:46:32",
         "speaker": "Hà",
         "text": "Em sẽ chuẩn bị sandbox test Y để bàn giao team dev sau khi ký hợp đồng ạ."},
    ]
    meta = {
        "id": "tc2", "title": "Chọn vendor CRM", "date": "2026-10-12",
        "participants": [
            {"name": "Lan", "role": "PM", "aliases": ["chị Lan"]},
            {"name": "Nam", "role": "BA", "aliases": ["em Nam"]},
            {"name": "Hà", "role": "Dev", "aliases": ["em Hà"]},
        ],
        "glossary": {},
    }
    extraction = extract(meta, turns, llm_fn=llm_fn)
    resolution = resolve(meta, extraction["chunk_items"])

    meeting = Meeting(
        id=meta["id"], title=meta["title"], date=meta["date"],
        participants=[Participant(**p) for p in meta["participants"]],
        source_file="data/transcripts/tc2_atob.txt",
        pipeline_version="0.3.0",
    )
    state = verify_state(
        meeting=meeting,
        items_raw=resolution["items"],
        conf_llm_map=extraction["conf_llm_map"],
        turns=turns,
        limitations=extraction["known_limitations"]
        + resolution["known_limitations"],
    )
    by_id = {i.id: i for i in state.items}
    assert "D1" in by_id
    d1 = by_id["D1"]
    assert d1.status == "final"
    # Evidence cuối cùng (substring match) → quote_match pass
    # ts @45:30 giữ nguyên
    assert any(ev.timestamp == "00:45:30" for ev in d1.evidence)
    # no_decision=False vì có final
    assert state.no_decision is False


# ──────────────────────────────────────────────────────────────────────
# 10. No-op khi input rỗng
# ──────────────────────────────────────────────────────────────────────


def test_resolve_empty_chunk_items() -> None:
    out = resolve({"id": "tc_empty", "date": "2026-10-13", "participants": []},
                  [])
    assert out["items"] == []
    assert out["known_limitations"] == []


def test_resolve_skips_empty_chunks() -> None:
    d1 = _d("D1", "Chốt phương án B", "final", decided_by="Lan",
            ts="00:45:30", speaker="Lan", turn=65, role="decide")
    chunk_items = [[], [d1], []]
    out = resolve({"id": "tc2", "date": "2026-10-12", "participants": []},
                  chunk_items)
    assert len(out["items"]) == 1
    assert out["items"][0]["id"] == "D1"


# ──────────────────────────────────────────────────────────────────────
# P4: deterministic due override + past-date + merge khác id (live tc4)
# ──────────────────────────────────────────────────────────────────────


def _t(task_id: str, what: str, owner: str, due: str,
       hint: str | None = None) -> dict[str, Any]:
    return {
        "id": task_id, "type": "task",
        "what": what, "owner": owner, "owner_source": "explicit",
        "due": due, "due_source": "explicit",
        "due_hint": hint, "link_to_decision": None,
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [],
    }


def test_resolve_iso_due_overridden_by_hint() -> None:
    """due ISO sai của model + hint tương đối → recompute deterministic thắng.

    Live tc4: T2 due=2026-10-29 + hint 'thứ 4 tuần sau' (meeting 2026-10-15)
    → override 2026-10-21 + limitation.
    """
    t = _t("T2", "Test edge cases", "Hà", "2026-10-29", "thứ 4 tuần sau")
    out = resolve({"id": "tc4", "date": "2026-10-15", "participants": []}, [[t]])
    assert out["items"][0]["due"] == "2026-10-21"
    assert out["items"][0]["due_hint"] == "thứ 4 tuần sau"
    assert any("deterministic 2026-10-21" in lim for lim in out["known_limitations"])


def test_resolve_iso_due_kept_when_matches_hint() -> None:
    """due ISO khớp recompute → giữ nguyên, không limitation thừa."""
    t = _t("T1", "Lead integration", "Hà", "2026-10-16", "thứ 6 tuần này")
    out = resolve({"id": "tc4", "date": "2026-10-15", "participants": []}, [[t]])
    assert out["items"][0]["due"] == "2026-10-16"
    assert not any("deterministic" in lim for lim in out["known_limitations"])


def test_resolve_past_due_becomes_tbd() -> None:
    """due ISO trước meeting.date, không hint recompute được → TBD + limitation."""
    t = _t("T7", "Update docs", "Hà", "2026-10-12", None)
    out = resolve({"id": "tc4", "date": "2026-10-15", "participants": []}, [[t]])
    assert out["items"][0]["due"] == TBD_SENTINEL
    assert any("trước meeting.date" in lim for lim in out["known_limitations"])


def test_resolve_merge_duplicate_tasks_different_ids() -> None:
    """Cùng owner + cùng due + overlap what → gộp, giữ bản đầu (live tc4 T1/T6)."""
    a = _t("T1", "Viết test plan cho flow refund", "Nam", "2026-10-31", "cuối tháng")
    b = _t("T6", "Test plan cuối tháng", "Nam", "2026-10-31", "cuối tháng")
    out = resolve({"id": "tc4", "date": "2026-10-15", "participants": []}, [[a, b]])
    ids = [i["id"] for i in out["items"]]
    assert ids == ["T1"]
    assert any("trùng T1" in lim for lim in out["known_limitations"])


def test_resolve_no_merge_distinct_tasks() -> None:
    """Khác owner hoặc khác due → KHÔNG gộp (bảo vệ tc1: 5 task riêng biệt)."""
    a = _t("T1", "Research vendor pricing", "Nam", "2026-10-16")
    b = _t("T2", "Setup môi trường dev", "Hà", "2026-10-19")
    out = resolve({"id": "tc1", "date": "2026-10-13", "participants": []}, [[a, b]])
    assert sorted(i["id"] for i in out["items"]) == ["T1", "T2"]


def test_resolve_id_collision_splits_tasks() -> None:
    """Cùng id T2 nhưng task KHÁC nhau ở 2 chunk → tách + rename (live tc4).

    Model tái dùng T1..T8 mỗi chunk. Khác nội dung = collision, không phải conflict.
    """
    a = _t("T2", "Xây dựng test plan cho thanh toán chi tiết", "Nam", "2026-10-31")
    b = _t("T2", "Phụ trách test plan edge cases cho flow refund mới", "Hà", "2026-10-24")
    out = resolve({"id": "tc4", "date": "2026-10-15", "participants": []}, [[a], [b]])
    ids = sorted(i["id"] for i in out["items"])
    assert ids == ["T2", "T2_2"]
    assert any("id collision" in lim for lim in out["known_limitations"])


def test_resolve_short_text_no_split() -> None:
    """What quá ngắn không đủ phân biệt → trọng tài như cũ (không tách bừa)."""
    a = _t("T7", "Ghi vào docs", "Hà", "2026-10-12")
    b = _t("T7", "Note checklist", "Nam", "2026-10-12")
    out = resolve({"id": "tc4", "date": "2026-10-15", "participants": []}, [[a], [b]])
    assert len([i for i in out["items"] if i["type"] == "task"]) == 1
    assert not any("id collision" in lim for lim in out["known_limitations"])


def test_resolve_merge_recap_loses_to_real_decide() -> None:
    """Cùng nội dung, bản note-lại (recap) bị hạ → bản chốt thật thắng.

    Live tc1: D0/Nam @04:36 "Em note lại: chốt..." bị hạ thành proposal,
    D1/Lan @04:24 giữ final (không cần merge vì khác id khác vai trò).
    """
    note = _fin("D0", "Chốt dùng FastAPI và JWT cho hệ thống", "Nam", "00:04:36", "decide")
    note["evidence"][0]["quote"] = "Em note lại: chốt dùng FastAPI nhé."
    real = _fin("D1", "Chốt dùng FastAPI và JWT mới", "Lan", "00:04:24", "decide")
    real["evidence"][0]["quote"] = "Vậy mình chốt FastAPI nhé."
    out = resolve({"id": "tc1", "date": "2026-10-13", "participants": []},
                  [[note], [real]])
    by_id = {i["id"]: i for i in out["items"]}
    assert by_id["D0"]["status"] == "proposal"  # recap → hạ, dù role=decide
    assert by_id["D1"]["status"] == "final"
    assert any("demote" in lim for lim in out["known_limitations"])


def test_resolve_merge_unions_hint_from_dropped() -> None:
    """Gộp: bản giữ thiếu due_hint thì lấy từ bản thua (live tc4 T1/T6)."""
    a = _t("T1", "Viết test plan cho flow refund", "Nam", "2026-10-31", None)
    b = _t("T6", "Test plan cuối tháng", "Nam", "2026-10-31", "cuối tháng")
    out = resolve({"id": "tc4", "date": "2026-10-15", "participants": []}, [[a, b]])
    ids = [i["id"] for i in out["items"]]
    assert ids == ["T1"]
    assert out["items"][0]["due_hint"] == "cuối tháng"


# ──────────────────────────────────────────────────────────────────────
# Demote final thiếu decide + merge finals cùng nội dung (live tc1)
# ──────────────────────────────────────────────────────────────────────


def _fin(fid: str, content: str, by: str, ts: str, role: str) -> dict[str, Any]:
    return {
        "id": fid, "type": "decision", "content": content,
        "status": "final", "decided_by": by,
        "confidence": 0.9, "confidence_reason": "ok",
        "evidence": [{
            "quote": content[:20], "timestamp": ts,
            "speaker": by, "turn": 1, "role_in_discussion": role,
        }],
    }


def test_resolve_demote_final_without_decide() -> None:
    """Final mà evidence toàn confirm/info (ghi chú lại) → proposal + limitation."""
    note = _fin("D0", "Chốt dùng FastAPI", "Nam", "00:04:36", "confirm")
    out = resolve({"id": "tc1", "date": "2026-10-13", "participants": []}, [[note]])
    assert out["items"][0]["status"] == "proposal"
    assert any("demote" in lim for lim in out["known_limitations"])


def test_resolve_keep_final_with_decide() -> None:
    """Final có evidence decide → giữ nguyên."""
    d = _fin("D1", "Chốt phương án B", "Lan", "00:52:10", "decide")
    out = resolve({"id": "tc2", "date": "2026-10-12", "participants": []}, [[d]])
    assert out["items"][0]["status"] == "final"


def test_resolve_merge_same_content_finals() -> None:
    """2 finals cùng nội dung khác id → gộp (winner decide muộn nhất)."""
    a = _fin("D0", "Chọn vendor Y gói premium", "Lan", "00:52:10", "decide")
    b = _fin("D1", "Chọn vendor Y gói premium SLA cao", "Lan", "00:52:34", "decide")
    out = resolve({"id": "tc2", "date": "2026-10-12", "participants": []}, [[a], [b]])
    ids = [i["id"] for i in out["items"]]
    assert len(ids) == 1 and ids[0] == "D1"  # decide muộn nhất thắng
    assert any("cùng nội dung" in lim for lim in out["known_limitations"])


def test_resolve_no_merge_different_content_finals() -> None:
    """Finals khác nội dung → giữ cả hai để reversal detection xử (R4)."""
    a = _fin("D_A", "Chốt dùng Spring Boot vì ecosystem", "Lan", "00:09:02", "decide")
    b = _fin("D_B", "Chuyển sang FastAPI vì team quen Python", "Lan", "00:14:22", "decide")
    out = resolve({"id": "tc5", "date": "2026-10-14", "participants": []}, [[a], [b]])
    assert sorted(i["id"] for i in out["items"]) == ["D_A", "D_B"]