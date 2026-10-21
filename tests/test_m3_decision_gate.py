"""
test_m3_decision_gate.py — M3-A: Decision Gate 3 điều kiện (chống false decision).

Triết lý: "LLM đề xuất, code kiểm chứng, con người chốt."

Test case: transcript mini 12 turns.
- Turn 5: "chốt luôn Stripe đi" (Lan đề xuất, nhưng KHÔNG phải chốt thật)
- Turn 6: "khoan, chưa có dữ liệu" (bị bác ngay)
- Turn 8: "để tuần sau tính" (rút lại)

Mock LLM cố tình trả final Stripe (để test gate phải hạ).

Kỳ vọng:
- M2 cũ: D1.final=Stripe, gate không hoạt động → test FAIL.
- M3 mới: D1.final→proposal (gate phải catch), no false final xanh Stripe.

Kỳ vọng FAIL trên code M2 (chưa có _apply_decision_gate) → D1 vẫn final.
Kỳ vọng PASS trên code M3 → D1 hạ proposal + limitation M3-A.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.resolve import resolve
from pipeline.schema import Participant


@pytest.fixture
def tc3_stripe_meta() -> dict:
    return {
        "id": "tc3",
        "title": "Brainstorm thanh toán (mini cho M3-A)",
        "date": "2026-10-13",
        "participants": [
            {"name": "Lan", "role": "PM", "aliases": ["chị Lan"]},
            {"name": "Hà", "role": "Dev", "aliases": ["em Hà"]},
        ],
        "glossary": {},
    }


def _make_stripe_decision() -> dict:
    """Final giả 'Chốt Stripe' — M3-A gate phải hạ vì bị bác/rút trong 5 turns."""
    return {
        "id": "D1", "type": "decision",
        "content": "Chốt Stripe",
        "status": "final", "decided_by": "Lan",
        "reason": "nói chơi để brainstorm",
        "supersedes": [],
        "objections": [],
        "confidence": 0.4, "confidence_reason": "chốt giả bị rút",
        "evidence": [{
            "quote": "Hay mình chốt luôn Stripe đi cho nhanh nhỉ?",
            "timestamp": "00:00:30", "speaker": "Lan",
            "turn": 5, "role_in_discussion": "decide",
        }],
    }


def _make_turns() -> list[dict]:
    """Mini transcript 12 turns: chốt Stripe bị bác + rút trong 5 turns sau."""
    return [
        {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
         "speaker": "Lan", "text": "Chào cả nhóm, brainstorm phương án thanh toán nhé."},
        {"turn": 2, "t_start": "00:00:11", "t_end": "00:00:11",
         "speaker": "Hà", "text": "Em có research về 2 vendor Stripe và VNPay ạ."},
        {"turn": 3, "t_start": "00:00:20", "t_end": "00:00:20",
         "speaker": "Lan", "text": "Ok, mình nghe trình bày đã nhé."},
        {"turn": 4, "t_start": "00:00:25", "t_end": "00:00:25",
         "speaker": "Hà", "text": "Stripe fee 2.9% + 30k, VNPay 1.8% ạ."},
        {"turn": 5, "t_start": "00:00:30", "t_end": "00:00:30",
         "speaker": "Lan",
         "text": "Hay mình chốt luôn Stripe đi cho nhanh nhỉ?"},
        {"turn": 6, "t_start": "00:00:42", "t_end": "00:00:42",
         "speaker": "Hà",
         "text": "Khoan chị, em chưa có số liệu, chốt bây giờ rủi ro lắm ạ."},
        {"turn": 7, "t_start": "00:00:50", "t_end": "00:00:50",
         "speaker": "Lan", "text": "Ừ nhỉ, chị nói vậy thôi chứ chưa đủ dữ liệu."},
        {"turn": 8, "t_start": "00:00:55", "t_end": "00:00:55",
         "speaker": "Lan", "text": "Thôi chưa chốt nhé, để tuần sau tính."},
        {"turn": 9, "t_start": "00:01:10", "t_end": "00:01:10",
         "speaker": "Hà", "text": "Dạ em đồng ý ạ."},
        {"turn": 10, "t_start": "00:01:25", "t_end": "00:01:25",
         "speaker": "Lan", "text": "Chốt là chưa chốt nhé, cần thêm dữ liệu."},
        {"turn": 11, "t_start": "00:01:40", "t_end": "00:01:40",
         "speaker": "Hà", "text": "Dạ em hiểu."},
        {"turn": 12, "t_start": "00:01:55", "t_end": "00:01:55",
         "speaker": "Lan", "text": "Mình hẹn họp lại nhé."},
    ]


def test_m3_decision_gate_demotes_retracted_stripe(tc3_stripe_meta) -> None:
    """Chốt Stripe bị bác/rút trong 5 turn → M3-A gate phải hạ final→proposal.

    Kỳ vọng PASS trên M3 (sau khi apply gate), FAIL trên M2 (gate chưa có).
    """
    out = resolve(tc3_stripe_meta, [[_make_stripe_decision()]],
                  turns=_make_turns())
    d1 = [x for x in out["items"] if x["id"] == "D1"][0]
    # M3-A: hạ final→proposal vì bị bác trong 5 turns sau
    assert d1["status"] == "proposal", (
        f"M3-A gate phải hạ Stripe final→proposal; got status={d1['status']!r}"
    )
    # Limitation ghi vết
    assert any("M3-A gate" in lim and "D1" in lim
               for lim in out["known_limitations"]), (
        f"M3-A gate phải ghi limitation cho D1; "
        f"got: {out['known_limitations']}"
    )


def test_m3_decision_gate_keeps_valid_final(tc3_stripe_meta) -> None:
    """Final có decide + decided_by hợp lệ + KHÔNG bị rút → giữ nguyên final."""
    d_valid = {
        "id": "D1", "type": "decision",
        "content": "Chốt VNPay cho phase 1",
        "status": "final", "decided_by": "Lan",
        "reason": "80% KH nội địa", "supersedes": [],
        "objections": [], "confidence": 0.85,
        "confidence_reason": "chốt rõ, đồng thuận cả team",
        "evidence": [
            {"quote": "Em nghiêng về VNPay vì 80% KH nội địa ạ.",
             "timestamp": "00:02:18", "speaker": "Nam",
             "turn": 13, "role_in_discussion": "propose"},
            {"quote": "Chốt dùng VNPay cho phase lập trình.",
             "timestamp": "00:03:06", "speaker": "Lan",
             "turn": 16, "role_in_discussion": "decide"},
        ],
    }
    out = resolve(tc3_stripe_meta, [[d_valid]], turns=_make_turns())
    d1 = [x for x in out["items"] if x["id"] == "D1"][0]
    # M3-A: gate pass → giữ final (không hạ)
    assert d1["status"] == "final"
    # Không có limitation M3-A cho D1
    assert not any("M3-A gate" in lim and "D1" in lim
                   for lim in out["known_limitations"])


def test_m3_decision_gate_via_run_pipeline_passes_turns(
    tc3_stripe_meta, tmp_path: Path
) -> None:
    """run_pipeline phải truyền turns vào resolve() để M3-A retract check chạy."""
    import json
    from pipeline.service import run_pipeline

    turns = _make_turns()
    transcript_file = tmp_path / "tc3.txt"
    lines = [
        f"[{t['t_start']}] {t['speaker']}: {t['text']}" for t in turns
    ]
    transcript_file.write_text("\n".join(lines), encoding="utf-8")

    mock_response = json.dumps(
        {"items": [_make_stripe_decision()]}, ensure_ascii=False
    )
    res = run_pipeline(
        meeting_id="tc3",
        meta=tc3_stripe_meta,
        transcript_path=transcript_file,
        runs_dir=tmp_path / "runs",
        extract_llm_fn=lambda _msgs: mock_response,
        log_llm=False,
    )
    state = res["state"]
    d1 = [it for it in state.items if it.id == "D1"][0]
    assert d1.status == "proposal", (
        f"run_pipeline phải truyền turns vào resolve() để hạ D1→proposal; got {d1.status!r}"
    )
    assert any("M3-A gate" in lim for lim in state.known_limitations)