"""
test_m3_hedge.py — M3-B: Hedge lexicon → cấm final + task hedge → TBD.

Triết lý: câu chốt content/quote chứa hedge marker (`có lẽ`, `xem xét`,
`sớm nhé`, `tính sau`, ...) thì KHÔNG phải chốt thật → cấm final.

Test case:
- Decision có content "Có lẽ chốt A" → M3-B phải hạ final→proposal.
- Decision có quote decide chứa "xem xét thêm" → M3-B hạ final→proposal.
- Task có evidence "có lẽ tính sau" → M3-B ép owner/due=TBD + due_hint.

Kỳ vọng FAIL trên code M2 cũ (chưa có _apply_hedge_gate).
Kỳ vọng PASS trên code M3 mới.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.resolve import resolve
from pipeline.schema import TBD_SENTINEL


def _meta() -> dict:
    return {
        "id": "tc_hedge", "date": "2026-10-13",
        "participants": [
            {"name": "Lan", "role": "PM", "aliases": []},
            {"name": "Nam", "role": "BA", "aliases": []},
        ],
        "glossary": {},
    }


def _turns_with_hedge() -> list[dict]:
    """Mini transcript với nhiều hedge markers."""
    return [
        {"turn": 1, "t_start": "00:00:05", "speaker": "Lan",
         "text": "Chào team, brainstorm phương án A nhé."},
        {"turn": 2, "t_start": "00:00:11", "speaker": "Nam",
         "text": "Em nghĩ có lẽ chốt A thì hợp lý."},
        {"turn": 3, "t_start": "00:00:20", "speaker": "Lan",
         "text": "Ừ có lẽ vậy, mình xem xét thêm nhé."},
        {"turn": 4, "t_start": "00:00:30", "speaker": "Nam",
         "text": "Em sẽ triển khai nhé chị."},
        {"turn": 5, "t_start": "00:00:40", "speaker": "Lan",
         "text": "Ok sớm nhé mọi người."},
    ]


def test_m3_hedge_decision_with_hedge_content_demoted() -> None:
    """Decision content chứa 'có lẽ' → M3-B hạ final→proposal."""
    d_hedge = {
        "id": "D1", "type": "decision",
        "content": "Có lẽ chốt phương án A",
        "status": "final", "decided_by": "Lan",
        "reason": "có hedge", "supersedes": [],
        "objections": [], "confidence": 0.7,
        "confidence_reason": "có hedge",
        "evidence": [{
            "quote": "Em nghĩ có lẽ chốt A thì hợp lý.",
            "timestamp": "00:00:11", "speaker": "Nam",
            "turn": 2, "role_in_discussion": "decide",
        }],
    }
    out = resolve(_meta(), [[d_hedge]], turns=_turns_with_hedge())
    d1 = [x for x in out["items"] if x["id"] == "D1"][0]
    assert d1["status"] == "proposal", (
        f"M3-B hedge phải hạ final→proposal; got status={d1['status']!r}"
    )
    assert any("M3-B hedge" in lim and "D1" in lim
               for lim in out["known_limitations"]), (
        f"M3-B phải ghi limitation cho D1; got: {out['known_limitations']}"
    )


def test_m3_hedge_decision_with_hedge_quote_demoted() -> None:
    """Decision quote decide chứa 'xem xét' → M3-B hạ final→proposal."""
    d = {
        "id": "D1", "type": "decision",
        "content": "Chốt phương án A",
        "status": "final", "decided_by": "Lan",
        "reason": "clean", "supersedes": [],
        "objections": [], "confidence": 0.85,
        "confidence_reason": "ok",
        "evidence": [{
            "quote": "Ok chốt A, mình xem xét thêm tuần sau.",
            "timestamp": "00:00:20", "speaker": "Lan",
            "turn": 3, "role_in_discussion": "decide",
        }],
    }
    out = resolve(_meta(), [[d]], turns=_turns_with_hedge())
    d1 = [x for x in out["items"] if x["id"] == "D1"][0]
    assert d1["status"] == "proposal"
    assert any("M3-B hedge" in lim for lim in out["known_limitations"])


def test_m3_hedge_task_evidence_blocked() -> None:
    """Task có evidence chứa hedge → M3-B ép owner/due=TBD + due_hint."""
    t = {
        "id": "T1", "type": "task",
        "what": "Triển khai A",
        "owner": "Nam", "owner_source": "explicit",
        "due": "2026-10-31", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.7, "confidence_reason": "hedge trong câu",
        "evidence": [{
            # Câu chứa hedge "sớm nhé" — turn 5 trong mini transcript
            "quote": "Ok sớm nhé mọi người.",
            "timestamp": "00:00:40", "speaker": "Lan",
            "turn": 5, "role_in_discussion": "propose",
        }],
    }
    out = resolve(_meta(), [[t]], turns=_turns_with_hedge())
    t1 = [x for x in out["items"] if x["id"] == "T1"][0]
    assert t1["owner"] == TBD_SENTINEL, (
        f"M3-B hedge phải ép owner=TBD; got {t1['owner']!r}"
    )
    assert t1["due"] == TBD_SENTINEL
    assert t1["due_hint"], "due_hint phải giữ chữ gốc (R2)"
    assert any("M3-B hedge" in lim and "T1" in lim
               for lim in out["known_limitations"])


def test_m3_hedge_decision_without_hedge_kept_final() -> None:
    """Decision KHÔNG có hedge → giữ nguyên final (gate pass)."""
    d_clean = {
        "id": "D1", "type": "decision",
        "content": "Chốt phương án A",
        "status": "final", "decided_by": "Lan",
        "reason": "rõ ràng", "supersedes": [],
        "objections": [], "confidence": 0.9,
        "confidence_reason": "ok",
        "evidence": [
            {"quote": "Em đề xuất chốt A ạ.",
             "timestamp": "00:00:05", "speaker": "Lan",
             "turn": 1, "role_in_discussion": "propose"},
            {"quote": "Ok chốt A.",
             "timestamp": "00:00:10", "speaker": "Lan",
             "turn": 1, "role_in_discussion": "decide"},
        ],
    }
    turns_clean = [
        {"turn": 1, "t_start": "00:00:05", "speaker": "Lan",
         "text": "Em đề xuất chốt A ạ. Ok chốt A."},
    ]
    out = resolve(_meta(), [[d_clean]], turns=turns_clean)
    d1 = [x for x in out["items"] if x["id"] == "D1"][0]
    assert d1["status"] == "final"
    assert not any("M3-B hedge" in lim for lim in out["known_limitations"])