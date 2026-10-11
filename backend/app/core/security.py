from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from backend.app.core.config import settings


def create_access_token(subject: str, role: str = "user", expires_delta: int | None = None) -> str:
    if expires_delta is None:
        expires_delta = settings.jwt_access_token_expire_minutes

    issued_at = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "sub": subject,
        "role": role,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=expires_delta),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a token's signature, expiry, and required claims."""
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "role", "exp", "iat", "jti"]},
    )
