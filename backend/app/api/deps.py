"""Shared FastAPI dependencies: authentication, roles, rate limits, and app services."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from backend.app.core.config import settings
from backend.app.core.rate_limit import SlidingWindowLimiter, auth_limiter, qa_limiter
from backend.app.db.database import Database, as_database
from backend.app.services.auth import bearer_auth, get_current_user, require_admin

logger = logging.getLogger("nyayaai.api")


def client_ip(request: Request) -> str:
    # Uvicorn resolves X-Forwarded-For into request.client when started with --proxy-headers.
    return request.client.host if request.client else "unknown"


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_auth)],
) -> dict[str, Any]:
    return get_current_user(request, credentials)


def admin_user(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    require_admin(user)
    return user


def get_database(request: Request) -> Database:
    return as_database(request.app.state.database)


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]
AdminUser = Annotated[dict[str, Any], Depends(admin_user)]
DB = Annotated[Database, Depends(get_database)]


def _enforce(limiter: SlidingWindowLimiter, key: str, limit: int, detail: str) -> None:
    if not limiter.allow(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": "60"},
        )


def limit_auth_attempts(request: Request) -> None:
    _enforce(
        auth_limiter,
        f"auth:{client_ip(request)}",
        settings.auth_rate_limit_per_minute,
        "Too many authentication attempts. Wait a minute and try again.",
    )


def limit_generation(user: CurrentUser) -> dict[str, Any]:
    _enforce(
        qa_limiter,
        f"qa:{user['username']}",
        settings.qa_rate_limit_per_minute,
        "Answer generation rate limit reached. Wait a minute and try again.",
    )
    return user


def record_usage(
    request: Request,
    username: str | None,
    event_type: str,
    status_value: str,
    retriever: str | None = None,
    result_count: int | None = None,
    latency_ms: float | None = None,
) -> None:
    """Persist an anonymized usage event; failures never break the user request."""
    try:
        as_database(request.app.state.database).record_usage(
            username,
            event_type,
            status_value,
            retriever=retriever,
            result_count=result_count,
            latency_ms=latency_ms,
        )
    except Exception:
        logger.exception("usage_event_write_failed event_type=%s", event_type)
