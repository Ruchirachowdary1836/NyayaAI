from __future__ import annotations

import hashlib
import hmac
import os
import secrets

import jwt
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import settings
from backend.app.db.database import DatabaseConfig, as_database

_PASSWORD_ROUNDS = 600_000
bearer_auth = HTTPBearer(auto_error=False)


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PASSWORD_ROUNDS)


def initialize_auth_store(store_config: DatabaseConfig) -> None:
    database = as_database(store_config)
    database.initialize()
    initial_username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
    initial_password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if initial_username and initial_password:
        create_user(database, initial_username, initial_password, role="admin")


def create_user(
    store_config: DatabaseConfig, username: str, password: str, role: str = "user"
) -> bool:
    database = as_database(store_config)
    salt = secrets.token_bytes(16)
    return database.create_user(username, _hash_password(password, salt), salt, role)


def authenticate(store_config: DatabaseConfig, username: str, password: str) -> str | None:
    row = as_database(store_config).get_user_credentials(username)
    if row is None:
        _hash_password(password, b"\0" * 16)
        return None
    password_hash, salt, role = row
    if not hmac.compare_digest(_hash_password(password, salt), password_hash):
        return None
    return str(role)


def get_current_user(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> dict[str, str]:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        username = payload.get("sub")
        role = payload.get("role")
        if not isinstance(username, str) or role not in {"user", "admin"}:
            raise ValueError("Invalid token claims")
    except (jwt.PyJWTError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    if as_database(request.app.state.auth_db).get_user_role(username) != role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is unavailable"
        )
    return {"username": username, "role": role}


def require_admin(user: dict[str, str]) -> None:
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required"
        )
