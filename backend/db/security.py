"""Hashing mật khẩu (argon2 qua pwdlib — tránh bẫy bcrypt 4.x/passlib).

Dùng cho seed admin (P6a) và register/login (P6b).
"""

from __future__ import annotations

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    if not plain or len(plain) < 8:
        raise ValueError("mật khẩu phải ≥ 8 ký tự")
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(plain, hashed)
    except Exception:
        return False
