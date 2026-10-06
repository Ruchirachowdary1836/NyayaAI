from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from backend.app.core.config import settings


def create_access_token(subject: str, role: str = "user", expires_delta: int | None = None) -> str:
    if expires_delta is None:
        expires_delta = settings.jwt_access_token_expire_minutes

    expires_at = datetime.now(UTC) + timedelta(minutes=expires_delta)
    payload = {"sub": subject, "role": role, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
