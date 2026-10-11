from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import settings
from backend.app.core.security import decode_access_token
from backend.app.db.database import DatabaseConfig, as_database

# PBKDF2-HMAC-SHA256 with 600k iterations follows current OWASP guidance.
_PASSWORD_ROUNDS = 600_000
bearer_auth = HTTPBearer(auto_error=False)
logger = logging.getLogger("nyayaai.auth")


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PASSWORD_ROUNDS)


def initialize_auth_store(store_config: DatabaseConfig) -> None:
    database = as_database(store_config)
    database.initialize()
    initial_username = settings.initial_admin_username.strip()
    initial_password = settings.initial_admin_password
    if initial_username and initial_password:
        if len(initial_password) < 12:
            logger.warning("INITIAL_ADMIN_PASSWORD is shorter than 12 characters; skipping")
            return
        if create_user(database, initial_username, initial_password, role="admin"):
            logger.info("Bootstrap administrator account created")


def create_user(
    store_config: DatabaseConfig, username: str, password: str, role: str = "user"
) -> bool:
    database = as_database(store_config)
    salt = secrets.token_bytes(16)
    return database.create_user(username, _hash_password(password, salt), salt, role)


def authenticate(store_config: DatabaseConfig, username: str, password: str) -> str | None:
    """Return the account role for valid credentials of an active account."""
    row = as_database(store_config).get_user_credentials(username)
    if row is None:
        # Spend comparable time so response timing does not reveal unknown usernames.
        _hash_password(password, b"\0" * 16)
        return None
    password_hash, salt, role, is_active = row
    if not hmac.compare_digest(_hash_password(password, salt), password_hash):
        return None
    if not is_active:
        return None
    return str(role)


def update_profile(
    store_config: DatabaseConfig,
    username: str,
    current_password: str,
    new_username: str,
    new_password: str | None = None,
) -> bool:
    if authenticate(store_config, username, current_password) is None:
        return False
    password_hash = None
    password_salt = None
    if new_password:
        password_salt = secrets.token_bytes(16)
        password_hash = _hash_password(new_password, password_salt)
    return as_database(store_config).update_user_credentials(
        username, new_username, password_hash, password_salt
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized("Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
        username = payload.get("sub")
        role = payload.get("role")
        jti = payload.get("jti")
        issued_at = payload.get("iat")
        if (
            not isinstance(username, str)
            or role not in {"user", "admin"}
            or not isinstance(jti, str)
            or not isinstance(issued_at, int | float)
        ):
            raise ValueError("Invalid token claims")
    except (jwt.PyJWTError, ValueError) as error:
        raise _unauthorized("Invalid or expired access token") from error

    database = as_database(request.app.state.database)
    state = database.get_user_auth_state(username)
    if state is None or not state["is_active"] or state["role"] != role:
        raise _unauthorized("User account is unavailable")
    valid_after: datetime | None = state["tokens_valid_after"]
    if valid_after is not None and datetime.fromtimestamp(issued_at, UTC) < valid_after:
        raise _unauthorized("Session has expired; sign in again")
    if database.is_token_revoked(jti):
        raise _unauthorized("Session has been signed out")
    return {
        "username": username,
        "role": role,
        "jti": jti,
        "expires_at": datetime.fromtimestamp(int(payload["exp"]), UTC),
    }


def require_admin(user: dict[str, Any]) -> None:
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required"
        )
