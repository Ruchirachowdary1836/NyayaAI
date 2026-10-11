from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.app.api.deps import DB, CurrentUser, limit_auth_attempts
from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.schemas.auth import (
    Credentials,
    ProfileUpdate,
    Registration,
    TokenResponse,
    UserProfile,
)
from backend.app.services.auth import authenticate, create_user, update_profile

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger("nyayaai.auth")
RateLimited = Annotated[None, Depends(limit_auth_attempts)]


def _token(username: str, role: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(username, role=role),
        role=role,
        username=username,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: Registration, database: DB, _: RateLimited) -> TokenResponse:
    if not create_user(database, payload.username, payload.password):
        raise HTTPException(status_code=409, detail="Username is already registered")
    database.record_login(payload.username)
    logger.info("account_registered")
    return _token(payload.username, "user")


@router.post("/token", response_model=TokenResponse)
def login(payload: Credentials, database: DB, _: RateLimited) -> TokenResponse:
    role = authenticate(database, payload.username, payload.password)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    database.record_login(payload.username)
    return _token(payload.username, role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser, database: DB) -> Response:
    database.revoke_token(user["jti"], user["username"], user["expires_at"])
    database.purge_expired_tokens()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserProfile)
def me(user: CurrentUser, database: DB) -> UserProfile:
    profile = database.get_user_profile(user["username"])
    if profile is None:
        raise HTTPException(status_code=401, detail="User account is unavailable")
    return UserProfile(**profile)


@router.put("/me", response_model=TokenResponse)
def update_me(
    payload: ProfileUpdate, user: CurrentUser, database: DB, _: RateLimited
) -> TokenResponse:
    if payload.username != user["username"]:
        existing = database.get_user_profile(payload.username)
        if existing is not None:
            raise HTTPException(status_code=409, detail="Username is already registered")
    if not update_profile(
        database,
        user["username"],
        payload.current_password,
        payload.username,
        payload.new_password,
    ):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    database.revoke_token(user["jti"], payload.username, user["expires_at"])
    return _token(payload.username, user["role"])
