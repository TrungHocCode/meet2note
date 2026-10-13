"""
test_api.py — P2: FastAPI layer mỏng theo docs/spec/api-contract.md.

Phủ:
- GET /health → 200
- GET /api/v1/review?meeting=... 404 (chưa run) | 200 (có run)
- PUT /api/v1/review ghi confirmed_state.json + append review_log.json
- POST /api/v1/export:
  + 403 gate_red_items khi còn thẻ đỏ
  + 501 export_not_implemented khi hết đỏ (P3 hiện thực file)
  + 404 nếu chưa run
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def runs_dir(tmp_path: Path, monkeypatch) -> Path:
    """Trỏ PROJECT_ROOT tới tmp_path để không chạm runs/ thật.

    Tạo sẵn 1 meeting 'tc_test' với 1 run có state.json chứa 1 đỏ + 1 xanh.
    """
    # Ghi đè env TRƯỚC khi backend.api đã import module → project root đã set.
    # Vì PROJECT_ROOT đã set tại import time, ta cần monkeypatch trực tiếp.
    import backend.api as api_mod
    monkeypatch.setattr(api_mod, "PROJECT_ROOT", tmp_path)

    meeting = "tc_test"
    ts = "20260101-120000"
    run_dir = tmp_path / "runs" / meeting / ts
    run_dir.mkdir(parents=True)

    state = {
        "meeting": {
            "id": meeting,
            "title": "Test",
            "date": "2026-10-13",
            "participants": [],
            "source_file": "fake.txt",
            "pipeline_version": "0.3.0",
        },
        "items": [
            {
                "id": "D1", "type": "decision",
                "content": "Chốt B",
                "status": "final", "decided_by": "Lan",
                "reason": "ok", "supersedes": [],
                "objections": [], "confidence": 0.40,  # đỏ (<0.50)
                "confidence_reason": "evidence_mismatch",
                "evidence": [],
            },
            {
                "id": "T1", "type": "task",
                "what": "x", "owner": "Nam", "owner_source": "explicit",
                "due": "2026-10-12", "due_source": "explicit",
                "due_hint": None, "link_to_decision": None,
                "confidence": 0.90,  # xanh
                "confidence_reason": "ok",
                "evidence": [],
            },
        ],
        "no_decision": False,
        "stats": {
            "by_type": {"decision": 1, "task": 1},
            "items_total": 2,
            "by_badge": {"red": 1, "green": 1, "yellow": 0},
        },
        "known_limitations": [],
    }
    (run_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return tmp_path


# ──────────────────────────────────────────────────────────────────────
# 1. GET /health
# ──────────────────────────────────────────────────────────────────────


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ──────────────────────────────────────────────────────────────────────
# 2. GET /api/v1/review
# ──────────────────────────────────────────────────────────────────────


def test_review_404_when_meeting_missing(client: TestClient) -> None:
    r = client.get("/api/v1/review?meeting=nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "meeting not found"}


def test_review_200_when_run_exists(
    client: TestClient, runs_dir: Path
) -> None:
    r = client.get("/api/v1/review?meeting=tc_test")
    assert r.status_code == 200
    body = r.json()
    assert body["meeting"]["id"] == "tc_test"
    assert len(body["items"]) == 2


def test_review_404_when_no_state_file(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """Có runs/<meeting>/<ts>/ nhưng thiếu state.json → 404."""
    import backend.api as api_mod
    monkeypatch.setattr(api_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / "runs" / "tc_empty" / "20260101-120000").mkdir(parents=True)
    r = client.get("/api/v1/review?meeting=tc_empty")
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# 3. PUT /api/v1/review
# ──────────────────────────────────────────────────────────────────────


def test_put_review_writes_confirmed_and_appends_log(
    client: TestClient, runs_dir: Path
) -> None:
    body = {
        "items": [
            {"id": "D1", "type": "decision",
             "content": "Chốt B (đã sửa)", "status": "final",
             "decided_by": "Lan", "reason": "ok",
             "supersedes": [], "objections": [],
             "confidence": 0.85, "confidence_reason": "ok",
             "evidence": []},
        ],
        "changes": [
            {"item_id": "D1", "action": "edit",
             "old": {"content": "Chốt B"},
             "new": {"content": "Chốt B (đã sửa)"}},
            {"item_id": "T1", "action": "remove"},
        ],
    }
    r = client.put("/api/v1/review?meeting=tc_test", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out["stats"]["changes_count"] == 2

    # confirmed_state.json được ghi
    run_dir = runs_dir / "runs" / "tc_test" / "20260101-120000"
    confirmed = json.loads(
        (run_dir / "confirmed_state.json").read_text(encoding="utf-8")
    )
    assert confirmed["meeting"] == "tc_test"
    assert confirmed["items"][0]["content"] == "Chốt B (đã sửa)"

    # review_log.json được append (không overwrite)
    log = json.loads((run_dir / "review_log.json").read_text(encoding="utf-8"))
    assert log["meeting_id"] == "tc_test"
    assert len(log["entries"]) == 2
    actions = [e["action"] for e in log["entries"]]
    assert "edit" in actions and "remove" in actions
    assert log["entries"][0]["item_id"] == "D1"


def test_put_review_appends_existing_log(
    client: TestClient, runs_dir: Path
) -> None:
    """Gọi PUT 2 lần → review_log.json entries tăng dần (ADR-0004)."""
    run_dir = runs_dir / "runs" / "tc_test" / "20260101-120000"
    existing_log = {
        "meeting_id": "tc_test",
        "entries": [
            {"item_id": "OLD", "action": "agree",
             "old": None, "new": None, "reviewer": "host",
             "ts": "2026-01-01T00:00:00Z"},
        ],
    }
    (run_dir / "review_log.json").write_text(
        json.dumps(existing_log), encoding="utf-8"
    )
    body = {
        "items": [{"id": "D1", "type": "decision", "content": "x",
                   "status": "final", "decided_by": "Lan",
                   "reason": None, "supersedes": [], "objections": [],
                   "confidence": 0.9, "confidence_reason": "ok",
                   "evidence": []}],
        "changes": [{"item_id": "D1", "action": "agree"}],
    }
    r = client.put("/api/v1/review?meeting=tc_test", json=body)
    assert r.status_code == 200
    log = json.loads((run_dir / "review_log.json").read_text(encoding="utf-8"))
    assert len(log["entries"]) == 2  # 1 cũ + 1 mới
    assert log["entries"][0]["item_id"] == "OLD"
    assert log["entries"][1]["item_id"] == "D1"


def test_put_review_action_validation(
    client: TestClient, runs_dir: Path
) -> None:
    """Action ngoài {agree, edit, remove} → 422 (Pydantic)."""
    body = {
        "items": [],
        "changes": [{"item_id": "D1", "action": "delete"}],  # invalid
    }
    r = client.put("/api/v1/review?meeting=tc_test", json=body)
    assert r.status_code == 422


def test_put_review_404_when_meeting_missing(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    import backend.api as api_mod
    monkeypatch.setattr(api_mod, "PROJECT_ROOT", tmp_path)
    body = {"items": [], "changes": []}
    r = client.put("/api/v1/review?meeting=nope", json=body)
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# 4. POST /api/v1/export — gate R6
# ──────────────────────────────────────────────────────────────────────


def test_export_403_when_red_items_exist(
    client: TestClient, runs_dir: Path
) -> None:
    """Còn badge đỏ → 403 gate_red_items + list red_items."""
    r = client.post("/api/v1/export?meeting=tc_test")
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "gate_red_items"
    assert "D1" in body["red_items"]


def test_export_501_when_no_red_items(
    client: TestClient, runs_dir: Path
) -> None:
    """Hết thẻ đỏ → 501 export_not_implemented (P3 hiện thực file)."""
    state_path = (
        runs_dir / "runs" / "tc_test" / "20260101-120000" / "state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # Sửa D1 confidence lên xanh
    state["items"][0]["confidence"] = 0.90
    state["stats"]["by_badge"] = {"red": 0, "yellow": 0, "green": 2}
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    r = client.post("/api/v1/export?meeting=tc_test")
    assert r.status_code == 501
    body = r.json()
    assert body["error"] == "export_not_implemented"
    assert "would_export" in body
    assert any("minutes.md" in f for f in body["would_export"])


def test_export_404_when_meeting_missing(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    import backend.api as api_mod
    monkeypatch.setattr(api_mod, "PROJECT_ROOT", tmp_path)
    r = client.post("/api/v1/export?meeting=nope")
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# 5. CORS — chỉ React dev
# ──────────────────────────────────────────────────────────────────────


def test_cors_preflight_allows_react_dev(client: TestClient) -> None:
    """OPTIONS preflight từ http://localhost:5173 → 200 (CORS OK)."""
    r = client.options(
        "/api/v1/review",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ──────────────────────────────────────────────────────────────────────
# 6. CLI rewiring — run gọi resolve
# ──────────────────────────────────────────────────────────────────────


def test_cli_run_calls_resolve_and_writes_state(
    tmp_path: Path, monkeypatch
) -> None:
    """Smoke: cli run --meeting tc2 với fixture → state.json có resolve output.

    Bằng chứng rewire P2: trong state.json, nếu resolve detect contradiction,
    sẽ có limitation 'R4: ...; resolve phase sẽ xử lý A→B→A' (P1) HOẠC
    'link_supersedes' (P2 mới). Cũng có 'same-id conflict' nếu fixture có.

    Đơn giản nhất: chạy với tc1_llm.json (1 chunk, không cross-chunk conflict)
    → state.json ghi ra thành công + stats đầy đủ. Đây đã là bằng chứng
    `extract → resolve → verify` đã được rewire.
    """
    import subprocess
    import sys
    project_root = Path(__file__).resolve().parent.parent
    fixture = project_root / "data" / "fixtures" / "tc1_llm.json"
    if not fixture.exists():
        pytest.skip(f"fixture chưa có: {fixture}")
    # Chạy với cwd là project root, --runs-dir trỏ vào tmp_path
    env = os.environ.copy()
    env["MEET2NOTE_ROOT"] = str(project_root)
    result = subprocess.run(
        [
            sys.executable, "-m", "pipeline.cli", "run",
            "--meeting", "tc1",
            "--llm-fixture", str(fixture),
            "--runs-dir", str(tmp_path),
        ],
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"cli run failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    # output có 'resolve:'
    assert "resolve:" in result.stdout

    # Tìm state.json được ghi
    out_dirs = list((tmp_path / "tc1").iterdir())
    assert len(out_dirs) == 1
    state_path = out_dirs[0] / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["meeting"]["id"] == "tc1"
    # Stats đầy đủ (Pydantic Stats model).
    assert "by_type" in state["stats"]
    assert "items_total" in state["stats"]
    assert state["stats"]["items_total"] >= 1