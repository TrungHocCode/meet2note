"""
test_api.py — P2 + P3: FastAPI layer mỏng theo docs/spec/api-contract.md.

Phủ:
- GET /health → 200
- GET /api/v1/review?meeting=... 404 (chưa run) | 200 (có run)
- PUT /api/v1/review ghi confirmed_state.json + append review_log.json
- POST /api/v1/export:
  + 403 gate_red_items khi còn thẻ đỏ
  + 200 export thật (minutes.md + tasks_jira.csv) khi hết đỏ + có confirmed_state
  + 400 not_confirmed khi hết đỏ nhưng chưa PUT
  + 404 nếu chưa run
"""

from __future__ import annotations

import json
import io
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import app


@pytest.fixture
def db(tmp_path: Path, monkeypatch) -> dict:
    """SQLite tmp + seed user + meeting 'tc_test' (P6b).

    Set DATABASE_URL/JWT_SECRET qua env — backend đọc env mỗi lần gọi
    nên test có DB riêng, không chạm Postgres local.
    """
    from backend.db.models import Base, Meeting, User
    from backend.db.security import hash_password
    from backend.db.session import make_engine
    from sqlalchemy.orm import Session as _Session

    monkeypatch.setenv("JWT_SECRET", "test-only-secret-du-32-ky-tu-abcdef")
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    email, password = "host@example.com", "Testpass123"
    with _Session(engine) as s:
        user = User(email=email, password_hash=hash_password(password))
        s.add(user)
        s.flush()
        uid = user.id
        s.add(Meeting(id="tc_test", owner_id=uid, title="Test", date="2026-10-13"))
        s.commit()
    return {"email": email, "password": password, "user_id": uid, "url": url}


@pytest.fixture
def client(db: dict) -> TestClient:
    """TestClient đã login — mọi /api/v1/* đi kèm Bearer token."""
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        data={"username": db["email"], "password": db["password"]},
    )
    assert r.status_code == 200, r.text
    c.headers.update(
        {"Authorization": f"Bearer {r.json()['access_token']}"}
    )
    return c


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
    assert confirmed["meeting"]["id"] == "tc_test"
    assert confirmed["items"][0]["content"] == "Chốt B (đã sửa)"
    # Envelope meeting (title/date/version) được giữ từ state.json để export dùng
    assert confirmed["meeting"].get("date") == "2026-10-13"

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


def test_export_400_when_no_confirmed_state(
    client: TestClient, runs_dir: Path
) -> None:
    """Gate pass nhưng chưa PUT review → 400 not_confirmed (không fallback).

    P3 thay đổi: trước đây (P2) là 501 export_not_implemented. Sau P3,
    export_meeting yêu cầu confirmed_state.json — host phải review trước.
    """
    state_path = (
        runs_dir / "runs" / "tc_test" / "20260101-120000" / "state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # Sửa D1 confidence lên xanh → gate pass
    state["items"][0]["confidence"] = 0.90
    state["stats"]["by_badge"] = {"red": 0, "yellow": 0, "green": 2}
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    r = client.post("/api/v1/export?meeting=tc_test")
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "not_confirmed"
    assert "xác nhận" in body["detail"]  # message thân thiện, không lộ path server


def test_export_200_writes_files(
    client: TestClient, runs_dir: Path, tmp_path: Path
) -> None:
    """Hết thẻ đỏ + có confirmed_state.json → 200 + 2 files thật."""
    state_path = (
        runs_dir / "runs" / "tc_test" / "20260101-120000" / "state.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # Sửa D1 confidence lên xanh → gate pass
    state["items"][0]["confidence"] = 0.90
    state["stats"]["by_badge"] = {"red": 0, "yellow": 0, "green": 2}
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Tạo confirmed_state.json (giả lập host đã PUT 1 lần)
    run_dir = state_path.parent
    confirmed = {
        "meeting": "tc_test",
        "items": state["items"],
        "updated_at": "2026-10-13T12:00:00Z",
    }
    (run_dir / "confirmed_state.json").write_text(
        json.dumps(confirmed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    r = client.post("/api/v1/export?meeting=tc_test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "files" in body
    assert len(body["files"]) == 2
    assert any(f.endswith("minutes.md") for f in body["files"])
    assert any(f.endswith("tasks_jira.csv") for f in body["files"])
    # File thật được tạo (path relative tới PROJECT_ROOT — resolve để assert tồn tại)
    for f in body["files"]:
        # f dạng "runs/tc_test/<ts>/<ts3>/minutes.md" — resolve ra tuyệt đối
        # qua PROJECT_ROOT (tmp_path tại test).
        abs_path = runs_dir / f
        assert abs_path.exists(), f"missing: {abs_path}"
        assert abs_path.stat().st_size > 0


def test_export_404_when_meeting_missing(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    import backend.api as api_mod
    monkeypatch.setattr(api_mod, "PROJECT_ROOT", tmp_path)
    r = client.post("/api/v1/export?meeting=nope")
    assert r.status_code == 404


def test_export_200_when_red_handled_via_review_log(
    client: TestClient, runs_dir: Path
) -> None:
    """Thẻ đỏ đã được host Đồng ý (có entry trong review_log) → không chặn export.

    Bug thực tế: gate đọc state.json thô, host agree xong vẫn 403 mãi.
    """
    run_dir = runs_dir / "runs" / "tc_test" / "20260101-120000"
    # confirmed như state hiện tại (D1 vẫn đỏ 0.40) + review_log có agree D1
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    (run_dir / "confirmed_state.json").write_text(
        json.dumps(
            {"meeting": state["meeting"], "items": state["items"], "updated_at": "t"},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "review_log.json").write_text(
        json.dumps(
            {"meeting_id": "tc_test",
             "entries": [{"item_id": "D1", "action": "agree",
                          "old": None, "new": None,
                          "reviewer": "host", "ts": "t"}]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    r = client.post("/api/v1/export?meeting=tc_test")
    assert r.status_code == 200, r.text
    assert "files" in r.json()


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
        encoding="utf-8",
        errors="replace",
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


# ──────────────────────────────────────────────────────────────────────
# 5. GET /api/v1/transcript (P5 — click evidence xem context)
# ──────────────────────────────────────────────────────────────────────


def test_transcript_404(client: TestClient, runs_dir: Path) -> None:
    r = client.get("/api/v1/transcript", params={"meeting": "nope"})
    assert r.status_code == 404

def test_transcript_200(client: TestClient, runs_dir: Path, db: dict) -> None:
    from backend.db.models import Meeting
    from backend.db.session import session_scope

    with session_scope(db["url"]) as s:
        s.add(Meeting(id="tx", owner_id=db["user_id"], title="Tx"))
    d = runs_dir / "data" / "transcripts"
    d.mkdir(parents=True)
    (d / "tx.txt").write_text(
        "[00:00:05] Lan: Chào.\n[00:00:10] Nam: Ok.\n", encoding="utf-8"
    )
    r = client.get("/api/v1/transcript", params={"meeting": "tx"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "tx.txt"
    assert len(body["turns"]) == 2
    assert body["turns"][0]["speaker"] == "Lan"
    assert body["turns"][1]["turn"] == 2


# ──────────────────────────────────────────────────────────────────────
# 6. POST /api/v1/meetings/upload (P5 — upload chạy pipeline)
# ──────────────────────────────────────────────────────────────────────


def test_upload_bad_extension(client: TestClient, runs_dir: Path) -> None:
    r = client.post(
        "/api/v1/meetings/upload",
        files={"file": ("x.pdf", "hello", "application/pdf")},
        data={"date": "2026-10-13"},
    )
    assert r.status_code == 400


def test_upload_bad_date_and_participants(client: TestClient, runs_dir: Path) -> None:
    files = {"file": ("x.txt", "[00:00:05] Lan: Chào.\n", "text/plain")}
    r = client.post(
        "/api/v1/meetings/upload", files=files,
        data={"meeting_id": "up1", "date": "13/10/2026"},
    )
    assert r.status_code == 400
    r = client.post(
        "/api/v1/meetings/upload", files=files,
        data={"meeting_id": "up1", "date": "2026-10-13",
              "participants": "không phải json"},
    )
    assert r.status_code == 400


def test_upload_success_mocked(
    client: TestClient, runs_dir: Path, tmp_path: Path, monkeypatch
) -> None:
    """Upload OK (pipeline mock — không cần LLM): file + meta lưu uploads/."""
    from pipeline.schema import Meeting, MeetingState, Stats

    st = MeetingState(
        meeting=Meeting(
            id="up1", title="Up", date="2026-10-13", participants=[],
            source_file="up1.txt", pipeline_version="t",
        ),
        items=[], no_decision=False, stats=Stats(), known_limitations=[],
    )
    out_dir = tmp_path / "runs" / "up1" / "ts"
    monkeypatch.setattr(
        "pipeline.service.run_pipeline",
        lambda **kw: {"state": st, "out_dir": out_dir, "turns_count": 2},
    )
    monkeypatch.setattr(
        "pipeline.extract.extract_brief", lambda *a, **k: None
    )
    r = client.post(
        "/api/v1/meetings/upload",
        files={"file": ("up1.txt", "[00:00:05] Lan: Chào.\n", "text/plain")},
        data={"meeting_id": "up1", "title": "Up", "date": "2026-10-13",
              "participants": '[{"name": "Lan", "role": "PM"}]'},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meeting_id"] == "up1"
    assert body["turns_count"] == 2
    assert (tmp_path / "data" / "uploads" / "up1.txt").exists()
    assert (tmp_path / "data" / "uploads" / "up1_meta.json").exists()


def test_upload_docx_accepted(
    client: TestClient, runs_dir: Path, tmp_path: Path, monkeypatch
) -> None:
    """Upload .docx đi qua ext-check và parse thật (pipeline mock)."""
    pytest.importorskip("docx")
    from docx import Document

    from pipeline.schema import Meeting, MeetingState, Stats

    st = MeetingState(
        meeting=Meeting(
            id="updoc", title="Up", date="2026-10-13", participants=[],
            source_file="updoc.docx", pipeline_version="t",
        ),
        items=[], no_decision=False, stats=Stats(), known_limitations=[],
    )
    monkeypatch.setattr(
        "pipeline.service.run_pipeline",
        lambda **kw: {"state": st, "out_dir": tmp_path, "turns_count": 1},
    )
    monkeypatch.setattr(
        "pipeline.extract.extract_brief", lambda *a, **k: None
    )
    doc = Document()
    doc.add_paragraph("[00:00:05] Lan: Chào.")
    blob = io.BytesIO()
    doc.save(blob)
    r = client.post(
        "/api/v1/meetings/upload",
        files={"file": (
            "updoc.docx", blob.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )},
        data={"meeting_id": "updoc", "date": "2026-10-13", "participants": "[]"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["turns_count"] == 1
    assert (tmp_path / "data" / "uploads" / "updoc.docx").exists()


# ──────────────────────────────────────────────────────────────────────
# 7. GET /api/v1/meetings (danh sách của mình — khỏi nhớ id)
# ──────────────────────────────────────────────────────────────────────


def test_meetings_requires_token(db: dict) -> None:
    r = TestClient(app).get("/api/v1/meetings")
    assert r.status_code == 401


def test_meetings_lists_only_mine(client: TestClient, db: dict) -> None:
    from backend.db.models import Meeting, User
    from backend.db.session import session_scope

    # Meeting của user khác trong cùng DB → không được lộ.
    with session_scope(db["url"]) as s:
        other = User(email="other@example.com", password_hash="x")
        s.add(other)
        s.flush()
        s.add(Meeting(id="hidden1", owner_id=other.id, title="Hidden"))
    r = client.get("/api/v1/meetings")
    assert r.status_code == 200, r.text
    ids = [m["id"] for m in r.json()["meetings"]]
    assert "tc_test" in ids  # seed từ fixture db
    assert "hidden1" not in ids


# ──────────────────────────────────────────────────────────────────────
# 8. GET /api/v1/export/file (tải file về máy user)
# ──────────────────────────────────────────────────────────────────────


def _seed_export_file(runs_dir: Path) -> None:
    out = runs_dir / "runs" / "tc_test" / "20260101-120000" / "exp1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "minutes.md").write_text("# Minutes\n", encoding="utf-8")
    (out / "tasks_jira.csv").write_text("key,summary\n", encoding="utf-8")


def test_download_minutes_200(client: TestClient, runs_dir: Path) -> None:
    _seed_export_file(runs_dir)
    r = client.get("/api/v1/export/file?meeting=tc_test&name=minutes.md")
    assert r.status_code == 200, r.text
    assert r.text.startswith("# Minutes")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "tc_test_minutes.md" in r.headers.get("content-disposition", "")


def test_download_csv_200(client: TestClient, runs_dir: Path) -> None:
    _seed_export_file(runs_dir)
    r = client.get("/api/v1/export/file?meeting=tc_test&name=tasks_jira.csv")
    assert r.status_code == 200
    assert "key,summary" in r.text


def test_download_rejects_bad_name(client: TestClient, runs_dir: Path) -> None:
    _seed_export_file(runs_dir)
    assert client.get(
        "/api/v1/export/file?meeting=tc_test&name=../state.json"
    ).status_code in (400, 422)
    assert client.get(
        "/api/v1/export/file?meeting=tc_test&name=state.json"
    ).status_code == 400


def test_download_404_without_file(client: TestClient, runs_dir: Path) -> None:
    r = client.get("/api/v1/export/file?meeting=tc_test&name=minutes.md")
    assert r.status_code == 404


def test_download_requires_token(db: dict, runs_dir: Path) -> None:
    _seed_export_file(runs_dir)
    r = TestClient(app).get("/api/v1/export/file?meeting=tc_test&name=minutes.md")
    assert r.status_code == 401


def test_download_other_owner_404(client: TestClient, db: dict) -> None:
    from backend.db.models import Meeting, User
    from backend.db.session import session_scope

    with session_scope(db["url"]) as s:
        other = User(email="dl-other@example.com", password_hash="x")
        s.add(other)
        s.flush()
        s.add(Meeting(id="priv", owner_id=other.id, title="Priv"))
    r = client.get("/api/v1/export/file?meeting=priv&name=minutes.md")
    assert r.status_code == 404