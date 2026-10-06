from __future__ import annotations

from datetime import datetime, timedelta

import jwt

from backend.app.core.config import settings


def create_access_token(subject: str, expires_delta: int | None = None) -> str:
    if expires_delta is None:
        expires_delta = settings.jwt_access_token_expire_minutes

    expires_at = datetime.utcnow() + timedelta(minutes=expires_delta)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
