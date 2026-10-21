"""
test_m3_evidence_chain.py — M3-C: Evidence-chain penalty cho Decision final.

Triết lý: "LLM đề xuất, code kiểm chứng, con người chốt."

Final chỉ có 1 evidence role=decide + không có propose/object/confirm
trong evidence chain = "diễn biến đơn lẻ" → KHÔNG xóa (giữ audit), nhưng
-0.20 confidence + limitation `single-evidence-final` (đỏ/vàng, host soi).

Regression R5 (nâng cấp): M2 chỉ +0.10 cho quote khớp — không có penalty
cho chuỗi diễn biến. M3-C fix đúng failure mode.

Kỳ vọng PASS trên code M3 mới, FAIL trên code M2 cũ (M2 không có penalty).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.verify import (
    compute_confidence,
    verify_state,
    _check_evidence_chain_for_final,
)
from pipeline.schema import Meeting, Participant


def _meeting() -> Meeting:
    return Meeting(
        id="tcM3", title="X", date="2026-10-13",
        participants=[
            Participant(name="Lan", role="PM", aliases=["chị Lan"]),
            Participant(name="Nam", role="BA", aliases=["em Nam"]),
            Participant(name="Hà", role="Dev", aliases=["em Hà"]),
        ],
        source_file="x.txt", pipeline_version="t",
    )


def test_m3_check_evidence_chain_marks_single_evidence_final() -> None:
    """Final chỉ có 1 decide evidence, không propose/object/confirm → single-evidence-final=True."""
    d = {
        "id": "D1", "type": "decision", "content": "Chốt A",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.9, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Chốt A nhé.", "timestamp": "00:00:30",
            "speaker": "Lan", "turn": 1,
            "role_in_discussion": "decide",
        }],
    }
    single, hedge, detail = _check_evidence_chain_for_final(d)
    assert single is True, (
        f"M3-C phải detect single-evidence-final; got single={single}"
    )
    assert hedge is False
    assert "single-evidence-final" in detail


def test_m3_check_evidence_chain_passes_with_chain() -> None:
    """Final có propose+confirm (≥2 role) → single-evidence-final=False."""
    d = {
        "id": "D1", "type": "decision", "content": "Chốt A",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.9, "confidence_reason": "ok",
        "evidence": [
            {"quote": "Em đề xuất A ạ.", "timestamp": "00:00:10",
             "speaker": "Nam", "turn": 1,
             "role_in_discussion": "propose"},
            {"quote": "Chốt A nhé.", "timestamp": "00:00:30",
             "speaker": "Lan", "turn": 2,
             "role_in_discussion": "decide"},
            {"quote": "Dạ em đồng ý.", "timestamp": "00:00:35",
             "speaker": "Nam", "turn": 3,
             "role_in_discussion": "confirm"},
        ],
    }
    single, hedge, detail = _check_evidence_chain_for_final(d)
    assert single is False, f"3 evidence roles → not single; got single={single}"
    assert hedge is False
    assert detail == ""


def test_m3_compute_confidence_single_evidence_final_penalty() -> None:
    """compute_confidence: single_evidence_final=True → -0.20 trên base."""
    final, reason, notes = compute_confidence(
        conf_llm=0.9,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "decision", "status": "final",
                   "decided_by": "Lan"},
        single_evidence_final=True,
    )
    # 0.9 + 0.10 - 0.20 = 0.80
    assert final == 0.80, f"got {final}, expected 0.80"
    assert any("single-evidence-final" in n for n in notes)


def test_m3_compute_confidence_hedge_final_penalty() -> None:
    """compute_confidence: hedge_final=True → -0.15."""
    final, _, notes = compute_confidence(
        conf_llm=0.85,
        quote_matched=True,
        evidence_mismatch=False,
        item_dict={"type": "decision", "status": "final"},
        hedge_final=True,
    )
    # 0.85 + 0.10 - 0.15 = 0.80
    assert final == 0.80
    assert any("hedge-final" in n for n in notes)


def test_m3_verify_state_keeps_single_evidence_final_with_penalty() -> None:
    """Regression R5 nâng cấp: single-evidence-final KHÔNG bị xóa, nhưng penalty -0.20.

    Test M3: final giữ item, confidence giảm, limitation ghi.
    Test M2: final confidence không có penalty.
    """
    raw_items = [{
        "id": "D1", "type": "decision",
        "content": "Chốt A", "status": "final",
        "decided_by": "Lan", "reason": "chốt",
        "supersedes": [], "objections": [],
        "confidence": 0.9, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Chốt A nhé.", "timestamp": "00:00:30",
            "speaker": "Lan", "turn": 1,
            "role_in_discussion": "decide",
        }],
    }]
    state = verify_state(
        meeting=_meeting(),
        items_raw=raw_items,
        conf_llm_map={"D1": 0.9},
        turns=[{"turn": 1, "t_start": "00:00:30", "t_end": "00:00:30",
                "speaker": "Lan", "text": "Chốt A nhé."}],
    )
    # Item KHÔNG bị xóa (giữ audit)
    assert any(i.id == "D1" for i in state.items)
    d1 = next(i for i in state.items if i.id == "D1")
    # Penalty: 0.9 + 0.10 - 0.20 = 0.80 (vàng, không xanh)
    assert d1.confidence == 0.80, (
        f"M3-C single-evidence-final penalty: got {d1.confidence}, expected 0.80"
    )
    # Limitation ghi rõ
    assert any("M3-C" in lim and "single-evidence-final" in lim
               for lim in state.known_limitations), (
        f"verify phải ghi M3-C limitation; got: {state.known_limitations}"
    )