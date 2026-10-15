"""Cố định env cho toàn bộ suite — `.env` thật của máy dev (CORS demo,
COOKIE_CROSS_SITE, JWT_SECRET…) KHÔNG được rò vào tests."""
import os

import pytest

os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
os.environ.setdefault("JWT_SECRET", "test-suite-secret-du-32-ky-tu-abcdef")
os.environ.pop("COOKIE_CROSS_SITE", None)


@pytest.fixture(autouse=True)
def _clean_demo_env(monkeypatch):
    """Xóa env demo sau load_dotenv() lúc import — backend đọc COOKIE_*
    mỗi request nên phải dọn mỗi test, không chỉ lúc import."""
    monkeypatch.delenv("COOKIE_CROSS_SITE", raising=False)
    yield
