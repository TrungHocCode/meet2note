"""
test_verify.py — Verify R1/R2/R5 + công thức confidence + badge + verify_state.

Phủ:
- normalize_for_match (lowercase, bỏ dấu câu, collapse whitespace)
- quote_match: ratio >= 0.85 (method='ratio'), substring (method='substring'), reject
- find_quote_in_turns: ±window, fallback scan toàn bộ
- canonicalize_owner: exact → explicit, alias → inferred, ngoài → TBD
- normalize_due: ISO → explicit, TBD → tbd, mơ hồ → TBD
- compute_confidence: công thức tính tay cho từng case
- badge_for: ngưỡng đỏ/vàng/xanh
- verify_state: integration end-to-end (TBD enforce, evidence match/mismatch, no_decision fallback)
"""

from __future__ import annotations

from typing import Any

import pytest

from pipeline.schema import (
    Meeting,
    Participant,
)
from pipeline.verify import (
    badge_for,
    canonicalize_owner,
    compute_confidence,
    find_quote_in_turns,
    normalize_due,
    normalize_for_match,
    quote_match,
    verify_state,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def participants() -> list[Participant]:
    return [
        Participant(name="Lan", role="PM", aliases=["chị Lan", "Lan"]),
        Participant(name="Nam", role="BA", aliases=["Nam", "em Nam"]),
        Participant(name="Hà", role="Dev", aliases=["em Hà", "Hà"]),
    ]


@pytest.fixture
def base_turns() -> list[dict[str, Any]]:
    return [
        {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
         "speaker": "Lan", "text": "Chào mọi người."},
        {"turn": 2, "t_start": "00:00:11", "t_end": "00:00:11",
         "speaker": "Nam", "text": "Em đề xuất phương án A, bên X rẻ hơn 20%."},
        {"turn": 3, "t_start": "00:00:30", "t_end": "00:00:30",
         "speaker": "Lan",
         "text": "A rủi ro vượt 30% nếu phát sinh. Vậy chốt B nhé, cả team đồng ý không?"},
        {"turn": 4, "t_start": "00:01:00", "t_end": "00:01:00",
         "speaker": "Nam", "text": "Dạ em đồng ý."},
    ]


def _meeting(meeting_id: str = "tc2") -> Meeting:
    return Meeting(
        id=meeting_id,
        title="Chọn vendor CRM",
        date="2026-10-12",
        participants=[
            Participant(name="Lan", role="PM", aliases=["chị Lan"]),
            Participant(name="Nam", role="BA", aliases=["em Nam"]),
            Participant(name="Hà", role="Dev", aliases=["em Hà"]),
        ],
        source_file="data/transcripts/tc2_atob.txt",
        pipeline_version="0.2.0",
    )


# ──────────────────────────────────────────────────────────────────────
# 1. Normalize
# ──────────────────────────────────────────────────────────────────────


def test_normalize_lowercase_strip_punct() -> None:
    assert normalize_for_match("Chào Mọi Người!") == "chào mọi người"
    assert normalize_for_match("Vậy chốt B nhé,") == "vậy chốt b nhé"
    assert normalize_for_match("(không ai phản đối)") == "không ai phản đối"


def test_normalize_collapse_whitespace() -> None:
    assert normalize_for_match("a  b\t c\n") == "a b c"


def test_normalize_unicode_vietnamese() -> None:
    assert normalize_for_match("KHÔNG") == "không"
    assert normalize_for_match("ĐỒNG Ý") == "đồng ý"


# ──────────────────────────────────────────────────────────────────────
# 2. Quote match — difflib ratio + substring fallback
# ──────────────────────────────────────────────────────────────────────


def test_quote_match_exact_ratio() -> None:
    matched, ratio, method = quote_match(
        "Vậy chốt B nhé, cả team đồng ý không?",
        "Vậy chốt B nhé, cả team đồng ý không?",
    )
    assert matched is True
    assert ratio == pytest.approx(1.0)
    assert method == "ratio"


def test_quote_match_near_exact_ratio() -> None:
    matched, ratio, method = quote_match(
        "vậy chốt b nhé cả team đồng ý không",
        "Vậy chốt B nhé, cả team đồng ý không?",
    )
    # Normalized giống nhau (cùng lowercase + bỏ punct) → ratio = 1.0
    assert matched is True
    assert ratio == pytest.approx(1.0)
    assert method == "ratio"


def test_quote_match_substring_method() -> None:
    """Quote là substring của turn dài (case tc2 evidence 00:45:30)."""
    matched, ratio, method = quote_match(
        "Vậy chốt B nhé, cả team đồng ý không?",
        "A rủi ro vượt 30% nếu phát sinh. "
        "Vậy chốt B nhé, cả team đồng ý không?",
    )
    assert matched is True
    assert method == "substring"
    assert ratio < 1.0  # vì len(turn) > len(quote)


def test_quote_match_substring_too_short_rejected() -> None:
    """Substring quá ngắn (< 10 chars) → không match, kể cả khi có trong turn."""
    matched, _, method = quote_match(
        "B nhé",
        "A rủi ro vượt 30%. Vậy chốt B nhé.",
    )
    assert matched is False
    assert method == "none"


def test_quote_match_substring_low_coverage_rejected() -> None:
    """Substring chiếm < 30% turn → fail (threshold hiện tại)."""
    # Quote 30 chars, turn 120+ chars → ~22% coverage → fail substring
    matched, _, method = quote_match(
        "Vậy chốt B nhé cả team đồng ý",  # 30 chars
        "A rủi ro vượt 30% nếu phát sinh. Vậy chốt B nhé, cả team đồng ý không? "
        "Còn câu hỏi nào khác không? Mình chuyển sang phần khác nhé. "
        "Ai có ý kiến gì thêm không?",  # ~150 chars → coverage ~18%
    )
    # ratio = 2*30/(30+150) = 0.33 < 0.85 → fail ratio
    # substring exists, len(q)=30 ≥ 10, but coverage=0.20 < 0.30 → fail substring
    assert matched is False
    assert method == "none"


def test_quote_match_completely_different() -> None:
    matched, _, method = quote_match(
        "Hoàn toàn khác",
        "Vậy chốt B nhé, cả team đồng ý không?",
    )
    assert matched is False
    assert method == "none"


def test_quote_match_empty_strings() -> None:
    assert quote_match("", "abc") == (False, 0.0, "none")
    assert quote_match("abc", "") == (False, 0.0, "none")


# ──────────────────────────────────────────────────────────────────────
# 3. find_quote_in_turns — ±window
# ──────────────────────────────────────────────────────────────────────


def test_find_quote_exact_turn() -> None:
    turns = [
        {"turn": 1, "text": "abc xyz"},
        {"turn": 2, "text": "Vậy chốt B nhé, cả team đồng ý không?"},
        {"turn": 3, "text": "qwe rty"},
    ]
    matched, _, idx, method = find_quote_in_turns(
        "Vậy chốt B nhé", turns, target_turn=2
    )
    assert matched is True
    assert idx == 1  # 0-based
    assert method in ("ratio", "substring")


def test_find_quote_within_window(base_turns) -> None:
    # Target turn sai (5), nhưng ±2 window bao turn 3 (idx 2)
    matched, _, idx, _ = find_quote_in_turns(
        "Vậy chốt B nhé, cả team đồng ý không",
        base_turns,
        target_turn=5,
    )
    assert matched is True
    assert idx == 2  # turn 3


def test_find_quote_outside_window_falls_back_to_full_scan(base_turns) -> None:
    # target_turn rất xa (100), ngoài range → scan toàn bộ
    matched, _, idx, _ = find_quote_in_turns(
        "Em đề xuất phương án A",
        base_turns,
        target_turn=100,
    )
    assert matched is True
    assert idx == 1  # turn 2


def test_find_quote_no_target_full_scan(base_turns) -> None:
    # target_turn=None → scan toàn bộ
    matched, _, idx, _ = find_quote_in_turns(
        "Dạ em đồng ý",
        base_turns,
        target_turn=None,
    )
    assert matched is True
    assert idx == 3  # turn 4


def test_find_quote_no_match() -> None:
    turns = [
        {"turn": 1, "text": "abc xyz"},
        {"turn": 2, "text": "qwe rty"},
    ]
    matched, ratio, _, _ = find_quote_in_turns(
        "Hoàn toàn không có", turns, target_turn=1
    )
    assert matched is False
    assert ratio < 0.85


# ──────────────────────────────────────────────────────────────────────
# 4. TBD enforcement
# ──────────────────────────────────────────────────────────────────────


def test_canonicalize_owner_explicit_match(participants) -> None:
    name, src = canonicalize_owner("Lan", participants)
    assert name == "Lan"
    assert src == "explicit"


def test_canonicalize_owner_inferred_via_alias(participants) -> None:
    name, src = canonicalize_owner("em Nam", participants)
    assert name == "Nam"
    assert src == "inferred"


def test_canonicalize_owner_already_tbd(participants) -> None:
    name, src = canonicalize_owner("TBD", participants)
    assert name == "TBD"
    assert src == "tbd"


def test_canonicalize_owner_unknown_person_to_tbd(participants) -> None:
    name, src = canonicalize_owner("Bob the Builder", participants)
    assert name == "TBD"
    assert src == "tbd"


def test_canonicalize_owner_empty_to_tbd(participants) -> None:
    name, src = canonicalize_owner("", participants)
    assert name == "TBD"
    assert src == "tbd"


def test_normalize_due_iso_explicit() -> None:
    d, src = normalize_due("2026-10-12")
    assert d == "2026-10-12"
    assert src == "explicit"


def test_normalize_due_tbd_keeps() -> None:
    d, src = normalize_due("TBD")
    assert d == "TBD"
    assert src == "tbd"


def test_normalize_due_vietnamese_mojiho_to_tbd() -> None:
    d, src = normalize_due("sớm nhé")
    assert d == "TBD"
    assert src == "tbd"


def test_normalize_due_asap_to_tbd() -> None:
    d, src = normalize_due("ASAP")
    assert d == "TBD"
    assert src == "tbd"


def test_normalize_due_empty_to_tbd() -> None:
    d, src = normalize_due("")
    assert d == "TBD"
    assert src == "tbd"


# ──────────────────────────────────────────────────────────────────────
# 5. Confidence formula (tính tay từng case)
# ──────────────────────────────────────────────────────────────────────


def test_conf_quote_matched_boost() -> None:
    """conf=0.7, quote khớp → +0.10 = 0.80."""
    final, reason, notes = compute_confidence(
        conf_llm=0.7,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "task", "owner": "Nam", "due": "2026-10-12",
                   "owner_source": "explicit", "due_source": "explicit"},
    )
    assert final == pytest.approx(0.80)
    assert "quote_matched +0.10" in notes


def test_conf_evidence_mismatch_penalty() -> None:
    """conf=0.7, mismatch → -0.30 = 0.40."""
    final, reason, notes = compute_confidence(
        conf_llm=0.7,
        quote_matched=False,
        evidence_mismatch=True,
        item_dict={"type": "task", "owner": "Nam", "due": "2026-10-12",
                   "owner_source": "explicit", "due_source": "explicit"},
    )
    assert final == pytest.approx(0.40)
    assert "evidence_mismatch -0.30" in notes


def test_conf_matched_and_mismatch_mutually_exclusive() -> None:
    """Nếu cả 2 cùng True → chỉ áp mismatch (ưu tiên an toàn)."""
    final, _, notes = compute_confidence(
        conf_llm=0.7,
        quote_matched=True,
        evidence_mismatch=True,  # cả 2 đều True
        item_dict={"type": "task", "owner": "Nam", "due": "2026-10-12",
                   "owner_source": "explicit", "due_source": "explicit"},
    )
    assert final == pytest.approx(0.40)  # chỉ áp -0.30
    assert any("mismatch" in n for n in notes)
    assert not any("quote_matched +0.10" in n for n in notes)


def test_conf_tbd_penalty_per_field() -> None:
    """2 TBD fields → -0.30. conf=0.8 + 0.10 - 0.30 = 0.60."""
    final, _, notes = compute_confidence(
        conf_llm=0.8,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "task", "owner": "TBD", "due": "TBD",
                   "owner_source": "tbd", "due_source": "tbd"},
    )
    assert final == pytest.approx(0.60)
    assert any("TBD" in n for n in notes)


def test_conf_tbd_only_owner() -> None:
    final, _, _ = compute_confidence(
        conf_llm=0.8,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "task", "owner": "TBD", "due": "2026-10-12",
                   "owner_source": "tbd", "due_source": "explicit"},
    )
    # 0.8 + 0.10 - 0.15 = 0.75
    assert final == pytest.approx(0.75)


def test_conf_tbd_only_due() -> None:
    final, _, _ = compute_confidence(
        conf_llm=0.8,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "task", "owner": "Nam", "due": "TBD",
                   "owner_source": "explicit", "due_source": "tbd"},
    )
    # 0.8 + 0.10 - 0.15 = 0.75
    assert final == pytest.approx(0.75)


def test_conf_inferred_penalty_per_field() -> None:
    """1 inferred → -0.10. conf=0.8 + 0.10 - 0.10 = 0.80."""
    final, _, notes = compute_confidence(
        conf_llm=0.8,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "task", "owner": "Nam", "due": "2026-10-12",
                   "owner_source": "inferred", "due_source": "explicit"},
    )
    assert final == pytest.approx(0.80)
    assert any("inferred" in n for n in notes)


def test_conf_two_inferred() -> None:
    final, _, _ = compute_confidence(
        conf_llm=0.8,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "task", "owner": "Nam", "due": "2026-10-12",
                   "owner_source": "inferred", "due_source": "inferred"},
    )
    # 0.8 + 0.10 - 0.20 = 0.70
    assert final == pytest.approx(0.70)


def test_conf_clamp_lower_bound() -> None:
    """conf - 0.30 - 0.30 = -0.10 → clamp 0."""
    final, _, _ = compute_confidence(
        conf_llm=0.5,
        quote_matched=False,
        evidence_mismatch=True,
        item_dict={"type": "task", "owner": "TBD", "due": "TBD",
                   "owner_source": "tbd", "due_source": "tbd"},
    )
    assert final == 0.0


def test_conf_clamp_upper_bound() -> None:
    """conf + 0.10 = 1.05 → clamp 1.0."""
    final, _, _ = compute_confidence(
        conf_llm=0.95,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "task", "owner": "Nam", "due": "2026-10-12",
                   "owner_source": "explicit", "due_source": "explicit"},
    )
    assert final == pytest.approx(1.0)


def test_conf_reason_contains_breakdown() -> None:
    _, reason, _ = compute_confidence(
        conf_llm=0.7,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "task", "owner": "TBD", "due": "2026-10-12",
                   "owner_source": "tbd", "due_source": "explicit"},
    )
    assert "conf_llm=0.70" in reason
    assert "quote_matched" in reason
    assert "TBD" in reason


# ──────────────────────────────────────────────────────────────────────
# 6. Badge threshold
# ──────────────────────────────────────────────────────────────────────


def test_badge_red_below_50() -> None:
    assert badge_for(0.0) == "red"
    assert badge_for(0.49) == "red"


def test_badge_yellow_50_to_75() -> None:
    assert badge_for(0.50) == "yellow"
    assert badge_for(0.74) == "yellow"


def test_badge_green_75_and_above() -> None:
    assert badge_for(0.75) == "green"
    assert badge_for(1.0) == "green"


# ──────────────────────────────────────────────────────────────────────
# 7. verify_state — integration
# ──────────────────────────────────────────────────────────────────────


def test_verify_state_tc2_happy_path() -> None:
    """Verify state với D0 (discarded) + D1 (final, substring match) + T1.

    Expected theo taxonomy §5:
    - D0: confidence ≈ 0.7 + 0.10 = 0.80 (quote match, no TBD)
    - D1: confidence ≈ 0.9 + 0.10 = 1.0 (substring match)
    - T1: confidence ≈ 0.85 + 0.10 = 0.95 (exact match)
    - no_decision = False (có D1 final)
    - stats: decision=2, task=1, items_total=3
    """
    raw_items = [
        {
            "id": "D0", "type": "decision", "content": "Đề xuất phương án A",
            "status": "discarded",
            "confidence": 0.7, "confidence_reason": "đề xuất ban đầu",
            "evidence": [{
                "quote": "Em đề xuất phương án A, bên X rẻ hơn 20%.",
                "timestamp": "00:00:42", "speaker": "Nam",
                "turn": 2, "role_in_discussion": "propose",
            }],
        },
        {
            "id": "D1", "type": "decision", "content": "Chốt phương án B",
            "status": "final", "decided_by": "Lan",
            "reason": "A rủi ro vượt 30%", "supersedes": ["D0"],
            "objections": [], "confidence": 0.9,
            "confidence_reason": "chốt rõ",
            "evidence": [{
                "quote": "Vậy chốt B nhé, cả team đồng ý không?",
                "timestamp": "00:45:30", "speaker": "Lan",
                "turn": 3, "role_in_discussion": "decide",
            }],
        },
        {
            "id": "T1", "type": "task",
            "what": "Gửi báo giá B cho khách",
            "owner": "Nam", "owner_source": "explicit",
            "due": "2026-10-12", "due_source": "explicit",
            "due_hint": None, "link_to_decision": "D1",
            "confidence": 0.85, "confidence_reason": "rõ",
            "evidence": [{
                "quote": "Dạ em gửi báo giá B cho khách trước 12/10.",
                "timestamp": "00:46:05", "speaker": "Nam",
                "turn": 4, "role_in_discussion": "confirm",
            }],
        },
    ]
    conf_map = {"D0": 0.7, "D1": 0.9, "T1": 0.85}

    state = verify_state(
        meeting=_meeting("tc2"),
        items_raw=raw_items,
        conf_llm_map=conf_map,
        turns=[
            {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
             "speaker": "Lan", "text": "Chào cả nhóm."},
            {"turn": 2, "t_start": "00:00:42", "t_end": "00:00:42",
             "speaker": "Nam", "text": "Em đề xuất phương án A, bên X rẻ hơn 20%."},
            {"turn": 3, "t_start": "00:45:30", "t_end": "00:45:30",
             "speaker": "Lan",
             "text": "A rủi ro vượt 30% nếu phát sinh. Vậy chốt B nhé, cả team đồng ý không?"},
            {"turn": 4, "t_start": "00:46:05", "t_end": "00:46:05",
             "speaker": "Nam", "text": "Dạ em gửi báo giá B cho khách trước 12/10."},
        ],
    )

    assert state.no_decision is False
    assert state.stats.by_type["decision"] == 2
    assert state.stats.by_type["task"] == 1
    assert state.stats.items_total == 3
    # Tất cả 3 items đều match → green badges
    assert state.stats.by_badge["green"] == 3
    assert state.stats.by_badge.get("red", 0) == 0

    # Verify confidence từng item
    by_id = {i.id: i for i in state.items}
    assert by_id["D0"].confidence == pytest.approx(0.80)  # 0.7 + 0.10
    assert by_id["D1"].confidence == pytest.approx(1.00)  # 0.9 + 0.10, clamped
    assert by_id["T1"].confidence == pytest.approx(0.95)  # 0.85 + 0.10


def test_verify_state_tbd_enforced_unknown_owner() -> None:
    """Owner ngoài participants → TBD + source=tbd."""
    raw_items = [{
        "id": "T1", "type": "task",
        "what": "Làm gì đó",
        "owner": "Bob the Builder",  # không có trong participants
        "owner_source": "explicit",   # LLM tự nhận explicit — verify sẽ sửa
        "due": "2026-10-15", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.7, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Bob làm gì đó nhé", "timestamp": "00:00:10",
            "speaker": "Lan", "turn": 1, "role_in_discussion": "info",
        }],
    }]
    state = verify_state(
        meeting=_meeting("tc_x"),
        items_raw=raw_items,
        conf_llm_map={"T1": 0.7},
        turns=[{"turn": 1, "t_start": "00:00:10", "t_end": "00:00:10",
                "speaker": "Lan", "text": "Bob làm gì đó nhé"}],
    )
    t1 = state.items[0]
    assert t1.owner == "TBD"
    assert t1.owner_source == "tbd"
    assert t1.due == "2026-10-15"  # ISO giữ nguyên
    assert t1.due_source == "explicit"
    # Confidence: 0.7 + 0.10 - 0.15 (TBD) = 0.65
    assert t1.confidence == pytest.approx(0.65)
    # Badge vàng (0.5-0.75)
    assert state.stats.by_badge["yellow"] == 1


def test_verify_state_tbd_enforced_vague_due_saves_hint() -> None:
    """due='sớm nhé' → TBD + due_hint='sớm nhé' + source=tbd."""
    raw_items = [{
        "id": "T1", "type": "task",
        "what": "Triển khai",
        "owner": "Nam", "owner_source": "explicit",
        "due": "sớm nhé", "due_source": "explicit",  # LLM đặt sai
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.7, "confidence_reason": "due unclear",
        "evidence": [{
            "quote": "Triển khai sớm nhé", "timestamp": "00:00:10",
            "speaker": "Nam", "turn": 1, "role_in_discussion": "info",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"T1": 0.7},
        turns=[{"turn": 1, "t_start": "00:00:10", "t_end": "00:00:10",
                "speaker": "Nam", "text": "Triển khai sớm nhé"}],
    )
    t1 = state.items[0]
    assert t1.due == "TBD"
    assert t1.due_source == "tbd"
    assert t1.due_hint == "sớm nhé"  # giữ chữ gốc (R2)


def test_verify_state_evidence_mismatch_flagged() -> None:
    """Quote không khớp transcript → evidence_mismatch + badge đỏ + limitation.

    Dùng conf_llm=0.7 để sau -0.30 = 0.4 → badge đỏ (<0.50).
    """
    raw_items = [{
        "id": "D1", "type": "decision",
        "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.7, "confidence_reason": "rõ",
        "evidence": [{
            "quote": "Câu hoàn toàn không có trong transcript xyzzy",
            "timestamp": "00:00:05", "speaker": "Lan",
            "turn": 1, "role_in_discussion": "decide",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"D1": 0.7},
        turns=[{"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
                "speaker": "Lan", "text": "Chào cả nhóm."}],
    )
    assert state.stats.by_badge["red"] == 1
    assert state.stats.by_badge.get("green", 0) == 0
    assert any("evidence_mismatch" in lim for lim in state.known_limitations)
    # Confidence: 0.7 - 0.30 = 0.4 → badge đỏ (<0.50), khoá export (R6)
    d1 = state.items[0]
    assert d1.confidence == pytest.approx(0.40)


def test_verify_state_no_decision_with_open_issue() -> None:
    """0 final decisions + 1 Open Issue có next_step → no_decision=True (R3)."""
    raw_items = [{
        "id": "O1", "type": "open_issue",
        "content": "Chưa chốt scope",
        "next_step": "Hẹn call team tuần sau để chốt",
        "next_step_owner": "Lan",
        "confidence": 0.6, "confidence_reason": "chưa rõ",
        "evidence": [{
            "quote": "Cần họp lại", "timestamp": "00:00:10",
            "speaker": "Nam", "turn": 1, "role_in_discussion": "info",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"O1": 0.6},
        turns=[{"turn": 1, "t_start": "00:00:10", "t_end": "00:00:10",
                "speaker": "Nam", "text": "Cần họp lại"}],
    )
    assert state.no_decision is True
    assert state.stats.by_type["open_issue"] == 1


def test_verify_state_no_decision_fallback_when_no_open_issue() -> None:
    """0 final + 0 Open Issue → tổng hợp O_SYS (system, conf 0.0) + no_decision=True.

    Gốc lệch #3: False cũ sai ngữ nghĩa (như thể đã chốt). O_SYS đỏ khóa export (R6)
    cho tới khi host xử lý — trung thực hơn.
    """
    raw_items = [{
        "id": "K1", "type": "knowledge",
        "content": "Vendor X không support tiếng Việt",
        "context": "rút ra từ cuộc họp",
        "tags": ["vendor"],
        "confidence": 0.7, "confidence_reason": "ok",
        "evidence": [],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"K1": 0.7},
        turns=[],
    )
    assert state.no_decision is True
    by_id = {i.id: i for i in state.items}
    assert "O_SYS" in by_id
    o_sys = by_id["O_SYS"]
    assert o_sys.system_generated is True
    assert o_sys.confidence == 0.0  # đỏ → khóa export (R6)
    assert o_sys.next_step  # next_step bắt buộc (R3)
    assert any("R3" in lim and "O_SYS" in lim for lim in state.known_limitations)


def test_verify_state_confidence_out_of_range_drops_item() -> None:
    """confidence=1.5 → bỏ ITEM (gate 1b), chunk/meeting sống tiếp, có limitation."""
    raw_items = [{
        "id": "D1", "type": "decision",
        "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 1.5, "confidence_reason": "quá tự tin",
        "evidence": [{
            "quote": "Chốt B nhé.", "timestamp": "00:00:30",
            "speaker": "Lan", "turn": 3, "role_in_discussion": "decide",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"D1": 1.5},
        turns=[{"turn": 3, "t_start": "00:00:30", "t_end": "00:00:30",
                "speaker": "Lan", "text": "Chốt B nhé."}],
    )
    assert all(i.id != "D1" for i in state.items)
    assert any("confidence" in lim for lim in state.known_limitations)


def test_verify_state_confidence_missing_drops_item() -> None:
    """Thiếu `confidence` → bỏ ITEM, không silent default (quyết định #7)."""
    raw_items = [{
        "id": "D1", "type": "decision",
        "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence_reason": "ok",
        "evidence": [{
            "quote": "Chốt B nhé.", "timestamp": "00:00:30",
            "speaker": "Lan", "turn": 3, "role_in_discussion": "decide",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={},
        turns=[{"turn": 3, "t_start": "00:00:30", "t_end": "00:00:30",
                "speaker": "Lan", "text": "Chốt B nhé."}],
    )
    assert all(i.id != "D1" for i in state.items)
    assert any("confidence" in lim for lim in state.known_limitations)


def test_verify_state_role_normalized_to_info() -> None:
    """role ngoài allowlist ('assign') → 'info' + limitation, item sống (accept-with-flag)."""
    raw_items = [{
        "id": "T1", "type": "task",
        "what": "Gửi báo giá",
        "owner": "Nam", "owner_source": "explicit",
        "due": "2026-10-12", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.8, "confidence_reason": "rõ",
        "evidence": [{
            "quote": "Nam gửi báo giá nhé", "timestamp": "00:00:10",
            "speaker": "Lan", "turn": 1, "role_in_discussion": "assign",
        }],
    }]
    state = verify_state(
        meeting=_meeting("tc_x"),
        items_raw=raw_items,
        conf_llm_map={"T1": 0.8},
        turns=[{"turn": 1, "t_start": "00:00:10", "t_end": "00:00:10",
                "speaker": "Lan", "text": "Nam gửi báo giá nhé"}],
    )
    assert len(state.items) == 2  # T1 + O_SYS (fixture không có final → R3 fallback)
    by_id = {i.id: i for i in state.items}
    assert by_id["T1"].evidence[0].role_in_discussion == "info"
    assert any("role ngoài allowlist" in lim for lim in state.known_limitations)


def test_verify_state_contradiction_two_finals_flagged() -> None:
    """2 Decision status=final → contradiction penalty (-0.20 mỗi final)."""
    raw_items = [
        {
            "id": "D1", "type": "decision",
            "content": "Chốt A",
            "status": "final", "decided_by": "Lan",
            "confidence": 0.8, "confidence_reason": "rõ",
            "evidence": [{
                "quote": "Chào.", "timestamp": "00:00:05",
                "speaker": "Lan", "turn": 1, "role_in_discussion": "decide",
            }],
        },
        {
            "id": "D2", "type": "decision",
            "content": "Chốt B",
            "status": "final", "decided_by": "Nam",
            "confidence": 0.8, "confidence_reason": "rõ",
            "evidence": [{
                "quote": "Đồng ý.", "timestamp": "00:00:11",
                "speaker": "Nam", "turn": 2, "role_in_discussion": "decide",
            }],
        },
    ]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"D1": 0.8, "D2": 0.8},
        turns=[
            {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
             "speaker": "Lan", "text": "Chào."},
            {"turn": 2, "t_start": "00:00:11", "t_end": "00:00:11",
             "speaker": "Nam", "text": "Đồng ý."},
        ],
    )
    # 2 final → contradiction → cả 2 đều -0.20
    by_id = {i.id: i for i in state.items}
    assert by_id["D1"].confidence == pytest.approx(0.70)  # 0.8 + 0.10 - 0.20
    assert by_id["D2"].confidence == pytest.approx(0.70)
    assert any("R4" in lim and "mâu thuẫn" in lim for lim in state.known_limitations)


def test_verify_state_missing_evidence_skipped() -> None:
    """Item không phải Knowledge mà thiếu evidence → bỏ + ghi limitation."""
    raw_items = [{
        "id": "D1", "type": "decision",
        "content": "Chốt X",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.8, "confidence_reason": "rõ",
        "evidence": [],  # R5: thiếu
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"D1": 0.8},
        turns=[],
    )
    assert state.stats.by_type.get("decision", 0) == 0
    assert any("thiếu evidence" in lim for lim in state.known_limitations)


def test_verify_state_pydantic_reject_logged() -> None:
    """Item structure không hợp lệ → log limitation + skip."""
    raw_items = [{
        "id": "D1", "type": "decision",
        "content": "Chốt X",
        "status": "approved",  # INVALID — không nằm trong Literal
        "decided_by": "Lan",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Chào.", "timestamp": "00:00:05",
            "speaker": "Lan", "turn": 1, "role_in_discussion": "decide",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"D1": 0.8},
        turns=[{"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
                "speaker": "Lan", "text": "Chào."}],
    )
    assert state.stats.by_type.get("decision", 0) == 0
    assert any("Pydantic reject" in lim for lim in state.known_limitations)


def test_verify_state_includes_ingest_limitations() -> None:
    """Limitations từ ingest phải carry forward vào state."""
    state = verify_state(
        meeting=_meeting(),
        items_raw=[],
        conf_llm_map={},
        turns=[],
        limitations=["txt line 5: malformed, skipped -> '...'"],
    )
    assert any("malformed" in lim for lim in state.known_limitations)


def test_verify_link_to_nonexistent_id_nulled() -> None:
    """link_to_decision trỏ ID ma (live tc1: link=D2) → null + limitation."""
    raw = [{
        "id": "T1", "type": "task",
        "what": "Làm gì đó",
        "owner": "Nam", "owner_source": "explicit",
        "due": "2026-10-16", "due_source": "explicit",
        "due_hint": None, "link_to_decision": "D2",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Nam làm gì đó nhé", "timestamp": "00:00:10",
            "speaker": "Lan", "turn": 1, "role_in_discussion": "info",
        }],
    }]
    state = verify_state(
        meeting=_meeting("tc_x"),
        items_raw=raw,
        conf_llm_map={"T1": 0.8},
        turns=[{"turn": 1, "t_start": "00:00:10", "t_end": "00:00:10",
                "speaker": "Lan", "text": "Nam làm gì đó nhé"}],
    )
    assert state.items[0].link_to_decision is None
    assert any("link_to_decision" in lim for lim in state.known_limitations)


# ──────────────────────────────────────────────────────────────────────
# Brief ref-check (taxonomy §8)
# ──────────────────────────────────────────────────────────────────────


def _brief_items() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = [{
        "id": "D1", "type": "decision",
        "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.9, "confidence_reason": "rõ",
        "evidence": [{
            "quote": "Vậy chốt B nhé.", "timestamp": "00:45:30",
            "speaker": "Lan", "turn": 65, "role_in_discussion": "decide",
        }],
    }]
    turns = [{"turn": 65, "t_start": "00:45:30", "t_end": "00:45:30",
              "speaker": "Lan", "text": "Vậy chốt B nhé."}]
    return raw, turns


def test_verify_brief_keeps_valid_refs_drops_ghost() -> None:
    """Outcome có ref tồn tại → giữ; ref ma → bỏ + limitation (nói≠chốt)."""
    raw, turns = _brief_items()
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw,
        conf_llm_map={"D1": 0.9},
        turns=turns,
        brief_raw={
            "problem": "Chọn vendor",
            "outcomes": [
                {"text": "Chốt B", "ref_ids": ["D1"]},
                {"text": "Ý tưởng suông", "ref_ids": ["DX"]},
            ],
        },
    )
    assert state.brief is not None
    assert [o.text for o in state.brief.outcomes] == ["Chốt B"]
    assert any("không trỏ tới ID" in lim for lim in state.known_limitations)


def test_verify_brief_none_when_missing() -> None:
    """Không có brief_raw → brief None, pipeline vẫn chạy."""
    raw, turns = _brief_items()
    state = verify_state(
        meeting=_meeting(), items_raw=raw,
        conf_llm_map={"D1": 0.9}, turns=turns,
    )
    assert state.brief is None


def test_verify_brief_dropped_when_problem_empty() -> None:
    """Problem trắng → schema reject → parse fail + brief None."""
    raw, turns = _brief_items()
    state = verify_state(
        meeting=_meeting(), items_raw=raw,
        conf_llm_map={"D1": 0.9}, turns=turns,
        brief_raw={"problem": "  ", "outcomes": []},
    )
    assert state.brief is None
    assert any("parse fail" in lim for lim in state.known_limitations)


# ──────────────────────────────────────────────────────────────────────
# Normalize thay vì drop (live brainstorm)
# ──────────────────────────────────────────────────────────────────────


def test_verify_requirement_bad_origin_becomes_unknown() -> None:
    """origin câu dài → 'unknown' + limitation, GIỮ item (đừng drop cả record)."""
    raw = [{
        "id": "R1", "type": "requirement",
        "content": "Cần báo trước 7 ngày",
        "raised_by": "Lan",
        "origin": "Discussion during evaluation of vendor support",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Cần báo trước 7 ngày", "timestamp": "00:00:10",
            "speaker": "Lan", "turn": 1, "role_in_discussion": "info",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw,
        conf_llm_map={"R1": 0.8},
        turns=[{"turn": 1, "t_start": "00:00:10", "t_end": "00:00:10",
                "speaker": "Lan", "text": "Cần báo trước 7 ngày"}],
    )
    assert len(state.items) == 2  # R1 + O_SYS fallback (fixture không có final)
    r1 = next(i for i in state.items if i.id == "R1")
    assert r1.origin == "unknown"
    assert any("origin" in lim for lim in state.known_limitations)


def test_verify_open_issue_missing_next_step_filled() -> None:
    """OpenIssue thiếu next_step → placeholder cho host + limitation, GIỮ item.

    (Họp mơ hồ hay thiếu next_step — bỏ cả item thì mất record "chưa chốt".)
    """
    raw = [{
        "id": "O1", "type": "open_issue",
        "content": "Chưa chốt hướng tích hợp",
        "confidence": 0.6, "confidence_reason": "mơ hồ",
        "evidence": [{
            "quote": "Chưa chốt hướng", "timestamp": "00:00:10",
            "speaker": "Lan", "turn": 1, "role_in_discussion": "info",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw,
        conf_llm_map={"O1": 0.6},
        turns=[{"turn": 1, "t_start": "00:00:10", "t_end": "00:00:10",
                "speaker": "Lan", "text": "Chưa chốt hướng"}],
    )
    assert len(state.items) == 1
    assert state.items[0].next_step == "Host xác định bước tiếp theo"
    assert any("next_step" in lim for lim in state.known_limitations)