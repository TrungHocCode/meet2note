"""
test_auth.py — P6b: JWT auth + owner isolation (docs/spec/api-contract.md §0).

Phủ:
- POST /auth/register → 201 | 409 email trùng | 422 pass ngắn
- POST /auth/login → 200 access_token + refresh cookie | 401 sai pass
- GET /auth/me → 200 với token | 401 không token
- POST /auth/refresh → 200 xoay refresh (cookie) | 401 không cookie
- POST /auth/logout → 200 + refresh cũ hết hiệu lực
- /api/v1/* không token → 401; token user B xem meeting user A → 404
- Upload tạo meetings + runs rows đúng owner (DB, không chỉ file).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import app


@pytest.fixture
def tdb(tmp_path, monkeypatch) -> dict:
    """DB sqlite riêng cho suite auth (độc lập với test_api.py)."""
    from backend.db.models import Base
    from backend.db.session import make_engine

    monkeypatch.setenv("JWT_SECRET", "auth-suite-secret-du-32-ky-tu-abcdef")
    monkeypatch.delenv("COOKIE_CROSS_SITE", raising=False)
    url = f"sqlite:///{tmp_path / 'auth.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    make_engine(url).connect().close()
    # create_all cần engine giữ tables — dùng engine trực tiếp:
    eng = make_engine(url)
    Base.metadata.create_all(eng)
    eng.dispose()
    return {"url": url}


@pytest.fixture
def anon(tdb: dict) -> TestClient:
    return TestClient(app)


def _register(c: TestClient, email: str, pw: str = "Matkhau123") -> dict:
    r = c.post("/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 201, r.text
    return r.json()


def _login(c: TestClient, email: str, pw: str = "Matkhau123"):
    r = c.post("/auth/login", data={"username": email, "password": pw})
    assert r.status_code == 200, r.text
    return r


# ── register / login ──────────────────────────────────────────────


def test_register_and_duplicate(anon: TestClient) -> None:
    u = _register(anon, "a@example.com")
    assert u["email"] == "a@example.com" and "id" in u
    r = anon.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "Matkhau123"},
    )
    assert r.status_code == 409


def test_register_short_password_rejected(anon: TestClient) -> None:
    r = anon.post(
        "/auth/register", json={"email": "b@example.com", "password": "ngan"}
    )
    assert r.status_code in (401, 422)


def test_login_wrong_password_401(anon: TestClient) -> None:
    _register(anon, "c@example.com")
    r = anon.post(
        "/auth/login", data={"username": "c@example.com", "password": "sai-hoan-toan"}
    )
    assert r.status_code == 401


def test_login_sets_refresh_cookie(anon: TestClient) -> None:
    _register(anon, "d@example.com")
    r = _login(anon, "d@example.com")
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert "refresh_token" in (r.cookies or {})


def test_cross_site_cookie_flags(monkeypatch) -> None:
    """COOKIE_CROSS_SITE=1 → SameSite=None + Secure (link demo Vercel+tunnel)."""
    from backend.api import _set_refresh_cookie
    from fastapi.responses import JSONResponse

    monkeypatch.setenv("COOKIE_CROSS_SITE", "1")
    resp = JSONResponse(status_code=200, content={})
    _set_refresh_cookie(resp, "raw-token")
    hdr = resp.headers.get("set-cookie", "").lower()
    assert "samesite=none" in hdr and "secure" in hdr


# ── me / refresh / logout ─────────────────────────────────────────


def test_me_ok_and_unauthorized(anon: TestClient) -> None:
    assert anon.get("/auth/me").status_code == 401
    _register(anon, "e@example.com")
    token = _login(anon, "e@example.com").json()["access_token"]
    r = anon.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "e@example.com"


def test_refresh_rotates(anon: TestClient) -> None:
    _register(anon, "f@example.com")
    _login(anon, "f@example.com")  # cookie lưu trong client
    r1 = anon.post("/auth/refresh")
    assert r1.status_code == 200, r1.text
    assert r1.json()["access_token"]
    # Refresh lần nữa bằng cookie đã xoay → vẫn 200 (cookie mới)
    r2 = anon.post("/auth/refresh")
    assert r2.status_code == 200


def test_refresh_without_cookie_401() -> None:
    assert TestClient(app).post("/auth/refresh").status_code == 401


def test_logout_revokes_refresh(anon: TestClient) -> None:
    _register(anon, "g@example.com")
    _login(anon, "g@example.com")
    assert anon.post("/auth/logout").status_code == 200
    # Refresh sau logout → 401 (cookie đã xoá / token bị revoke)
    assert anon.post("/auth/refresh").status_code == 401


# ── gating + isolation ────────────────────────────────────────────


def test_api_requires_token(anon: TestClient) -> None:
    assert anon.get("/api/v1/review?meeting=x").status_code == 401
    assert anon.post("/api/v1/export?meeting=x").status_code == 401


def _seed_meeting(url: str, owner_id: str, mid: str) -> None:
    from backend.db.models import Meeting
    from backend.db.session import session_scope

    with session_scope(url) as s:
        s.add(Meeting(id=mid, owner_id=owner_id, title=mid))


def test_user_b_cannot_see_user_a_meeting(anon: TestClient, tdb: dict) -> None:
    ua = _register(anon, "owner@example.com")
    ub = _register(anon, "other@example.com")
    _seed_meeting(tdb["url"], ua["id"], "private1")
    tb = _login(anon, "other@example.com").json()["access_token"]
    r = anon.get(
        "/api/v1/review?meeting=private1",
        headers={"Authorization": f"Bearer {tb}"},
    )
    assert r.status_code == 404  # 404 như nhau, không lộ tồn tại
    assert ub["id"] != ua["id"]


def test_owner_can_read_own_meeting_file(
    anon: TestClient, tdb: dict, tmp_path, monkeypatch
) -> None:
    """Owner + có state.json trên disk → 200 (đủ cả 2 lớp)."""
    import json as _json

    import backend.api as api_mod

    monkeypatch.setattr(api_mod, "PROJECT_ROOT", tmp_path)
    ua = _register(anon, "h@example.com")
    _seed_meeting(tdb["url"], ua["id"], "m1")
    run_dir = tmp_path / "runs" / "m1" / "ts1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        _json.dumps({"meeting": {"id": "m1"}, "items": []}), encoding="utf-8"
    )
    token = _login(anon, "h@example.com").json()["access_token"]
    r = anon.get(
        "/api/v1/review?meeting=m1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_upload_creates_meeting_and_run_rows(
    anon: TestClient, tdb: dict, tmp_path, monkeypatch
) -> None:
    """Upload (pipeline mock) → meetings + runs rows đúng owner."""
    from backend.db.models import Meeting, Run
    from backend.db.session import session_scope
    from pipeline.schema import Meeting as MMeta
    from pipeline.schema import MeetingState, Stats

    import backend.api as api_mod

    monkeypatch.setattr(api_mod, "PROJECT_ROOT", tmp_path)
    ua = _register(anon, "uploader@example.com")
    st = MeetingState(
        meeting=MMeta(
            id="updb", title="Up", date="2026-10-13", participants=[],
            source_file="updb.txt", pipeline_version="t",
        ),
        items=[], no_decision=False, stats=Stats(), known_limitations=[],
    )
    monkeypatch.setattr(
        "pipeline.service.run_pipeline",
        lambda **kw: {
            "state": st,
            "out_dir": tmp_path / "runs" / "updb" / "ts",
            "turns_count": 1,
        },
    )
    monkeypatch.setattr("pipeline.extract.extract_brief", lambda *a, **k: None)
    token = _login(anon, "uploader@example.com").json()["access_token"]
    r = anon.post(
        "/api/v1/meetings/upload",
        files={"file": ("updb.txt", "[00:00:05] Lan: Chào.\n", "text/plain")},
        data={"meeting_id": "updb", "date": "2026-10-13", "participants": "[]"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    with session_scope(tdb["url"]) as s:
        m = s.query(Meeting).filter_by(id="updb").one()
        assert m.owner_id == ua["id"]
        runs = s.query(Run).filter_by(meeting_id="updb").all()
        assert len(runs) == 1 and runs[0].status == "done"
