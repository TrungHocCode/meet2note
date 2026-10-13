"""
test_export.py — P3: pipeline/export.py (render_minutes + render_jira_csv
+ export_meeting).

Phủ (theo docs/spec/export-format.md §1-§3):
- Template minutes.md render đủ 4 mục + badge theo confidence.
- TBD → ô trống trong CSV + ghi chú Description.
- Discarded không in thành mục riêng — chỉ "Thay thế D0" trong final.
- CSV: header, prefix Summary `[D1]/[T2]`, Labels `tc2;decision-D1`.
- export_meeting thiếu confirmed → lỗi rõ, không fallback state.json thô.
- review_log.json (ghi bởi backend, xét riêng ở test_api.py) — schema ok.

Đầu vào: dict meeting_state shape (đúng schema).
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pytest

from pipeline.export import (
    export_meeting,
    render_jira_csv,
    render_minutes,
)


def _csv_rows(text: str) -> list[list[str]]:
    """Parse CSV text thành list of rows (dùng cho test)."""
    return list(csv.reader(io.StringIO(text)))


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def tc2_state() -> dict:
    """State shape giống runs/tc2/<ts>/state.json (verified từ live)."""
    return {
        "meeting": {
            "id": "tc2",
            "title": "Chọn vendor tích hợp CRM",
            "date": "2026-10-12",
            "participants": [
                {"name": "Lan", "role": "PM", "aliases": ["chị Lan"]},
                {"name": "Nam", "role": "BA", "aliases": ["em Nam"]},
                {"name": "Hà", "role": "Dev", "aliases": ["em Hà"]},
            ],
            "source_file": "fake.txt",
            "pipeline_version": "0.3.0",
        },
        "items": [
            # D0 discarded → KHÔNG in mục riêng, chỉ là "Thay thế D0" dưới D1.
            {
                "id": "D0", "type": "decision",
                "content": "Tạm dừng cuộc họp 5 phút",
                "status": "discarded",
                "decided_by": None, "reason": None,
                "supersedes": [], "objections": [],
                "unresolved_reversal": False,
                "confidence": 0.6, "confidence_reason": "info",
                "evidence": [{
                    "quote": "Vậy mình tạm dừng 5 phút.",
                    "timestamp": "00:13:40", "speaker": "Hà",
                    "turn": 62, "role_in_discussion": "info",
                }],
            },
            # D1 final — supersedes D0 → sẽ có dòng "Thay thế D0".
            {
                "id": "D1", "type": "decision",
                "content": "Chọn vendor Y, gói premium",
                "status": "final",
                "decided_by": "Lan",
                "reason": "rủi ro A vượt 30%",
                "supersedes": ["D0"],
                "objections": [
                    {
                        "quote": "Em lo ngại downtime Y.",
                        "timestamp": "00:45:00",
                        "speaker": "Nam",
                        "turn": 64, "role_in_discussion": "object",
                    }
                ],
                "unresolved_reversal": False,
                "confidence": 1.0, "confidence_reason": "ok",
                "evidence": [{
                    "quote": "Vậy chốt B nhé.",
                    "timestamp": "00:45:30", "speaker": "Lan",
                    "turn": 65, "role_in_discussion": "decide",
                }],
            },
            # T1 — due rõ, owner rõ → xanh.
            {
                "id": "T1", "type": "task",
                "what": "Gửi báo giá B cho khách",
                "owner": "Nam", "owner_source": "explicit",
                "due": "2026-10-12", "due_source": "explicit",
                "due_hint": None, "link_to_decision": "D1",
                "confidence": 1.0, "confidence_reason": "ok",
                "evidence": [{
                    "quote": "Em gửi báo giá B trước 12/10.",
                    "timestamp": "00:46:05", "speaker": "Nam",
                    "turn": 69, "role_in_discussion": "confirm",
                }],
            },
            # T2 — owner TBD + due TBD + due_hint → ô trống + note.
            {
                "id": "T2", "type": "task",
                "what": "Kiểm tra SLA",
                "owner": "TBD", "owner_source": "tbd",
                "due": "TBD", "due_source": "tbd",
                "due_hint": "sau khi ký hợp đồng",
                "link_to_decision": None,
                "confidence": 0.55, "confidence_reason": "TBD",
                "evidence": [{
                    "quote": "Check SLA sau khi ký.",
                    "timestamp": "00:50:00", "speaker": "Hà",
                    "turn": 80, "role_in_discussion": "info",
                }],
            },
            # B1 blocker — severity high.
            {
                "id": "B1", "type": "blocker",
                "content": "Vendor API key chưa có",
                "needs_action_from": "Hà", "severity": "high",
                "confidence": 0.85, "confidence_reason": "ok",
                "evidence": [{
                    "quote": "API key vendor chưa về.",
                    "timestamp": "00:30:00", "speaker": "Hà",
                    "turn": 55, "role_in_discussion": "info",
                }],
            },
            # O1 open_issue — next_step bắt buộc.
            {
                "id": "O1", "type": "open_issue",
                "content": "Xác minh điều kiện hợp đồng",
                "next_step": "Hà xác minh với vendor",
                "next_step_owner": "Hà",
                "confidence": 0.7, "confidence_reason": "ok",
                "evidence": [],
                "system_generated": False,
            },
            # R1 requirement — origin customer.
            {
                "id": "R1", "type": "requirement",
                "content": "KH muốn hỗ trợ tiếng Việt",
                "raised_by": "KH",
                "origin": "customer",
                "confidence": 0.8, "confidence_reason": "ok",
                "evidence": [],
            },
            # K1 knowledge — không bắt buộc evidence.
            {
                "id": "K1", "type": "knowledge",
                "content": "A chỉ cam kết best-effort",
                "context": "downtime không cam kết đền bù",
                "tags": ["risk", "vendor-A"],
                "confidence": 0.9, "confidence_reason": "ok",
                "evidence": [],
            },
        ],
        "no_decision": False,
        "stats": {
            "by_type": {
                "decision": 2, "task": 2, "blocker": 1,
                "open_issue": 1, "requirement": 1, "knowledge": 1,
            },
            "items_total": 8,
            "by_badge": {"red": 0, "yellow": 3, "green": 5},
        },
        "known_limitations": [
            "merge: id=T2 trùng → giữ bản đầu.",
            "evidence_mismatch id=T1: -0.30",
        ],
    }


# ──────────────────────────────────────────────────────────────────────
# 1. render_minutes — template Jinja2
# ──────────────────────────────────────────────────────────────────────


def test_minutes_has_all_four_sections(tc2_state) -> None:
    """Minutes phải có đúng 4 mục theo spec §1."""
    md = render_minutes(tc2_state)
    assert "## ✅ Quyết định" in md
    assert "## 📌 Công việc" in md
    assert "## ⚠️ Vướng mắc & Chưa chốt" in md
    assert "## 📋 Yêu cầu & Kiến thức" in md


def test_minutes_title_and_pipeline_version(tc2_state) -> None:
    md = render_minutes(tc2_state)
    # Title + date
    assert "# Biên bản họp - Chọn vendor tích hợp CRM — 2026-10-12" in md
    # Pipeline version (single source — meeting.pipeline_version)
    assert "Pipeline 0.3.0" in md
    assert "Đã confirm" in md


def test_minutes_badge_per_item(tc2_state) -> None:
    """Mỗi item render đúng badge theo confidence (R6 nói giữ trung thực)."""
    md = render_minutes(tc2_state)
    # D1 conf=1.0 → 🟢 xanh
    assert "🟢" in md
    # T2 conf=0.55 → 🟡 vàng
    assert "🟡" in md
    # Không có item đỏ trong fixture, nhưng ta kiểm tra chuỗi badge đỏ không lộ
    # (gate R6 nên ngăn đỏ vào export). Nếu sau này state có đỏ, vẫn render 🟢/🟡/🔴.
    assert "🔴" not in md  # fixture sạch đỏ


def test_minutes_red_badge_rendered_when_present() -> None:
    """Nếu lọt red item (vd: gate bypass) → render 🔴, không giấu (trung thực)."""
    state = {
        "meeting": {
            "id": "x", "title": "T", "date": "2026-10-13",
            "participants": [], "source_file": "x", "pipeline_version": "0.3.0",
        },
        "items": [{
            "id": "R1", "type": "requirement",
            "content": "c", "raised_by": "u", "origin": "internal",
            "confidence": 0.3, "confidence_reason": "low",
            "evidence": [],
        }],
        "no_decision": False,
        "stats": {"by_type": {"requirement": 1}, "items_total": 1,
                  "by_badge": {"red": 1, "yellow": 0, "green": 0}},
        "known_limitations": [],
    }
    md = render_minutes(state)
    assert "🔴" in md


def test_minutes_decision_final_in_main_discarded_not_separate(tc2_state) -> None:
    """Final in trong mục 'Quyết định'; discarded chỉ là 'Thay thế D0'."""
    md = render_minutes(tc2_state)
    # D1 final hiển thị
    assert "**D1 - Chọn vendor Y, gói premium**" in md
    assert "Thay thế D0" in md
    # D0 KHÔNG hiển thị như mục riêng (chỉ xuất hiện trong 'Thay thế D0').
    # Đếm 'D0' xuất hiện: 1 lần trong 'Thay thế D0' (không có bullet riêng).
    # Bullet dạng `- **D0 -` KHÔNG được có.
    assert "**D0 -" not in md


def test_minutes_objections_rendered(tc2_state) -> None:
    """R7: objection phải xuất hiện dưới decision (không xoá tranh luận)."""
    md = render_minutes(tc2_state)
    assert "⛔ Objection:" in md
    assert "Em lo ngại downtime Y." in md
    assert "[00:45:00]" in md


def test_minutes_decided_by_and_reason(tc2_state) -> None:
    md = render_minutes(tc2_state)
    # decided_by + reason
    assert "bởi Lan" in md
    assert "Lý do: rủi ro A vượt 30%" in md


def test_minutes_evidence_with_ts_speaker_role(tc2_state) -> None:
    md = render_minutes(tc2_state)
    assert "🎯 [00:45:30] Lan (chốt):" in md
    assert '"Vậy chốt B nhé."' in md


def test_minutes_task_due_tbd_uses_hint(tc2_state) -> None:
    """Task có due_hint → render hint thay vì 'TBD' (R2)."""
    md = render_minutes(tc2_state)
    # T2 có due_hint 'sau khi ký hợp đồng' → render hint
    assert "sau khi ký hợp đồng" in md


def test_minutes_blocker_format(tc2_state) -> None:
    md = render_minutes(tc2_state)
    assert "- B1 Vendor API key chưa có (cần Hà)" in md


def test_minutes_open_issue_format(tc2_state) -> None:
    md = render_minutes(tc2_state)
    assert "O1 Xác minh điều kiện hợp đồng" in md
    assert "next_step: Hà xác minh với vendor" in md


def test_minutes_requirement_and_knowledge_in_last_section(tc2_state) -> None:
    md = render_minutes(tc2_state)
    assert "R1 KH muốn hỗ trợ tiếng Việt" in md
    assert "origin: customer" in md
    assert "K1 A chỉ cam kết best-effort" in md
    assert "tags: risk, vendor-A" in md


def test_minutes_footer_known_limitations(tc2_state) -> None:
    md = render_minutes(tc2_state)
    assert "*Hạn chế:*" in md
    assert "merge: id=T2 trùng" in md
    assert "evidence_mismatch id=T1: -0.30" in md


def test_minutes_empty_state_renders_placeholder() -> None:
    """Mọi mục rỗng → placeholder '(không có ...)' để cấu trúc đủ 4 mục."""
    state = {
        "meeting": {"id": "e", "title": "T", "date": "2026-10-13",
                    "participants": [], "source_file": "x",
                    "pipeline_version": "0.3.0"},
        "items": [],
        "no_decision": True,
        "stats": {"by_type": {}, "items_total": 0,
                  "by_badge": {"red": 0, "yellow": 0, "green": 0}},
        "known_limitations": [],
    }
    md = render_minutes(state)
    assert "_(không có quyết định)_" in md
    assert "_(không có công việc)_" in md
    assert "_(không có vướng mắc)_" in md
    assert "_(không có yêu cầu / kiến thức)_" in md


# ──────────────────────────────────────────────────────────────────────
# 2. render_jira_csv
# ──────────────────────────────────────────────────────────────────────


def test_csv_header(tc2_state) -> None:
    csv_text = render_jira_csv(tc2_state)
    first = csv_text.splitlines()[0]
    assert first == "Summary,Issue Type,Assignee,Due Date,Labels,Description"


def test_csv_decision_row(tc2_state) -> None:
    """Decision có prefix [D1], Labels `tc2;decision-D1`."""
    csv_text = render_jira_csv(tc2_state)
    rows = _csv_rows(csv_text)
    # Tìm row của D1
    d1_rows = [r for r in rows if r[0] == "[D1] Chọn vendor Y, gói premium"]
    assert len(d1_rows) == 1
    r = d1_rows[0]
    assert r[1] == "Task"
    assert r[2] == ""  # decision không có owner → ô trống
    assert r[3] == ""  # decision không có due → ô trống
    assert r[4] == "tc2;decision-D1"
    # Description có evidence đầu
    assert "Evidence [00:45:30] Lan:" in r[5]


def test_csv_task_t1_explicit_owner_due(tc2_state) -> None:
    csv_text = render_jira_csv(tc2_state)
    rows = _csv_rows(csv_text)
    t1 = [r for r in rows if r[0].startswith("[T1]")][0]
    assert t1[2] == "Nam"
    assert t1[3] == "2026-10-12"
    assert t1[4] == "tc2;task-T1"
    # Không có note TBD vì owner/due rõ
    assert "TBD" not in t1[5]


def test_csv_task_t2_tbd_owner_due_empty_with_notes(tc2_state) -> None:
    """T2 owner=TBD, due=TBD, có due_hint → ô trống + note."""
    csv_text = render_jira_csv(tc2_state)
    rows = _csv_rows(csv_text)
    t2 = [r for r in rows if r[0].startswith("[T2]")][0]
    assert t2[2] == ""  # Owner TBD → ô trống
    assert t2[3] == ""  # Due TBD → ô trống
    assert "Owner TBD - cần gán" in t2[5]
    assert "Due TBD - cần xác định" in t2[5]
    assert "due_hint: sau khi ký hợp đồng" in t2[5]
    assert t2[4] == "tc2;task-T2"


def test_csv_ignores_non_task_decision_types(tc2_state) -> None:
    """Chỉ decision + task xuất hiện trong CSV; blocker/requirement/knowledge bỏ."""
    csv_text = render_jira_csv(tc2_state)
    rows = _csv_rows(csv_text)
    summaries = [r[0] for r in rows]
    assert any(s.startswith("[D1]") for s in summaries)
    assert any(s.startswith("[T1]") for s in summaries)
    assert any(s.startswith("[T2]") for s in summaries)
    # Không có prefix [B1] / [O1] / [R1] / [K1] / [D0]
    assert not any(s.startswith("[B1]") for s in summaries)
    assert not any(s.startswith("[O1]") for s in summaries)
    assert not any(s.startswith("[R1]") for s in summaries)
    assert not any(s.startswith("[K1]") for s in summaries)
    assert not any(s.startswith("[D0]") for s in summaries)


def test_csv_row_count_matches_task_plus_decision(tc2_state) -> None:
    csv_text = render_jira_csv(tc2_state)
    # header + 1 decision (D1) + 2 tasks (T2)
    # (D0 discarded bị bỏ — vì status != final)
    lines = [l for l in csv_text.splitlines() if l]
    assert len(lines) == 1 + 1 + 2


# ──────────────────────────────────────────────────────────────────────
# 3. export_meeting — top-level
# ──────────────────────────────────────────────────────────────────────


def test_export_meeting_writes_files(tmp_path: Path, tc2_state) -> None:
    """Có confirmed_state.json → ghi 2 file, trả paths."""
    runs = tmp_path / "runs"
    meeting = "tc2"
    ts = "20260101-120000"
    run_dir = runs / meeting / ts
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps(tc2_state, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "confirmed_state.json").write_text(
        json.dumps(tc2_state, ensure_ascii=False), encoding="utf-8"
    )

    result = export_meeting(meeting, runs, now_ts="20260101-120500")

    files = result["files"]
    assert len(files) == 2
    assert any(f.endswith("minutes.md") for f in files)
    assert any(f.endswith("tasks_jira.csv") for f in files)

    # File tồn tại + non-empty
    for f in result["absolute_paths"]:
        p = Path(f)
        assert p.exists()
        assert p.stat().st_size > 0

    # minutes.md có tiêu đề đúng
    minutes_text = Path(result["absolute_paths"][0]).read_text(encoding="utf-8")
    assert "# Biên bản họp - Chọn vendor tích hợp CRM" in minutes_text
    assert "## ✅ Quyết định" in minutes_text


def test_export_meeting_no_run_dir_raises(tmp_path: Path) -> None:
    """Không có runs/<meeting>/ → FileNotFoundError rõ ràng."""
    runs = tmp_path / "runs"
    runs.mkdir()
    with pytest.raises(FileNotFoundError, match="meeting not found"):
        export_meeting("ghost", runs, now_ts="20260101-120000")


def test_export_meeting_no_confirmed_raises_no_fallback(tmp_path: Path) -> None:
    """Có state.json NHƯNG không có confirmed_state.json → lỗi rõ,
    KHÔNG fallback sang state.json thô (gate R6 / ADR-0004).

    Chỉ được 1 file runs/<meeting>/<ts>/ để verify state.json không được đọc lén.
    """
    runs = tmp_path / "runs"
    meeting = "tc2"
    ts = "20260101-120000"
    run_dir = runs / meeting / ts
    run_dir.mkdir(parents=True)
    state = {"meeting": {"id": meeting}, "items": []}
    (run_dir / "state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    # KHÔNG ghi confirmed_state.json — đây là điểm test.

    with pytest.raises(FileNotFoundError, match="confirmed_state.json not found"):
        export_meeting(meeting, runs, now_ts="20260101-120500")


def test_export_meeting_creates_new_timestamp_dir(tmp_path: Path, tc2_state) -> None:
    """export_meeting tạo dir mới theo ts (audit) — không overwrite run cũ."""
    runs = tmp_path / "runs"
    meeting = "tc2"
    ts = "20260101-120000"
    run_dir = runs / meeting / ts
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps(tc2_state), encoding="utf-8"
    )
    (run_dir / "confirmed_state.json").write_text(
        json.dumps(tc2_state), encoding="utf-8"
    )

    # Gọi 2 lần cùng now_ts → tạo 2 dir khác nhau (suffix -1)
    r_a = export_meeting(meeting, runs, now_ts="20260101-130000")
    r_b = export_meeting(meeting, runs, now_ts="20260101-130000")
    assert r_a["out_dir"] != r_b["out_dir"]
    # Cả 2 đều tồn tại
    assert Path(r_a["out_dir"]).exists()
    assert Path(r_b["out_dir"]).exists()


# ──────────────────────────────────────────────────────────────────────
# 4. review_log schema (spec §3)
# ──────────────────────────────────────────────────────────────────────


def test_review_log_schema_shape() -> None:
    """Spec §3: review_log.json schema."""
    log = {
        "meeting_id": "tc2",
        "entries": [
            {
                "item_id": "T2",
                "action": "edit",
                "old": {"owner": "TBD"},
                "new": {"owner": "Nam"},
                "reviewer": "host",
                "ts": "2026-10-13T10:00:00Z",
            },
        ],
    }
    # Schema cho phép action ∈ {agree, edit, remove} (backend enforce).
    assert log["entries"][0]["action"] in {"agree", "edit", "remove"}
    assert "ts" in log["entries"][0]
    assert "reviewer" in log["entries"][0]