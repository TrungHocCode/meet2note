"""backend/auth.py — JWT auth đa user (P6b).

- Access token (JWT HS256, 60 phút) qua header `Authorization: Bearer`.
- Refresh token (opaque 32B, 7 ngày) qua httpOnly cookie `refresh_token`.
- `get_current_user`: dependency bảo vệ mọi `/api/v1/*` (trừ `/health`).
- Thiếu `JWT_SECRET` → lỗi rõ lúc tạo/verify token (không default ngầm).
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.db.models import User
from backend.db.session import session_scope

ACCESS_MINUTES = int(os.environ.get("JWT_ACCESS_MINUTES", "60"))
REFRESH_DAYS = int(os.environ.get("JWT_REFRESH_DAYS", "7"))
REFRESH_COOKIE = "refresh_token"


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "thiếu JWT_SECRET trong .env (tạo chuỗi ngẫu nhiên dài, "
            "KHÔNG commit — xem .env.example)"
        )
    return secret


def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token hết hạn — đăng nhập lại",
        ) from e
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token không hợp lệ",
        ) from e


def new_refresh_token() -> tuple[str, str]:
    """Trả (token_thô, token_hash_lưu_db)."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db() -> Session:
    """Session per-request (đóng sau response). Test override qua dependency."""
    with session_scope() as session:
        yield session


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    user = db.query(User).filter_by(id=payload.get("sub")).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user không tồn tại",
        )
    return user


__all__ = [
    "ACCESS_MINUTES",
    "REFRESH_COOKIE",
    "REFRESH_DAYS",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "get_db",
    "new_refresh_token",
]
