from __future__ import annotations

from typing import Annotated

from backend.app.core.security import create_access_token
from backend.app.db.database import as_database
from backend.app.schemas.auth import Credentials, ProfileUpdate, TokenResponse
from backend.app.services.auth import (
    authenticate,
    bearer_auth,
    create_user,
    get_current_user,
    update_profile,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: Credentials, request: Request) -> TokenResponse:
    if not create_user(request.app.state.auth_db, payload.username, payload.password):
        raise HTTPException(status_code=409, detail="Username is already registered")
    return TokenResponse(
        access_token=create_access_token(payload.username, role="user"),
        role="user",
    )


@router.post("/token", response_model=TokenResponse)
def login(payload: Credentials, request: Request) -> TokenResponse:
    role = authenticate(request.app.state.auth_db, payload.username, payload.password)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(payload.username, role=role),
        role=role,
    )


@router.get("/me")
def me(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_auth)],
) -> dict[str, str]:
    return get_current_user(request, credentials)


@router.put("/me", response_model=TokenResponse)
def update_me(
    payload: ProfileUpdate,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_auth)],
) -> TokenResponse:
    current_user = get_current_user(request, credentials)
    if not update_profile(
        request.app.state.auth_db,
        current_user["username"],
        payload.current_password,
        payload.username,
        payload.new_password,
    ):
        existing = as_database(request.app.state.auth_db).get_user_profile(payload.username)
        if existing and payload.username != current_user["username"]:
            raise HTTPException(status_code=409, detail="Username is already registered")
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    return TokenResponse(
        access_token=create_access_token(payload.username, role=current_user["role"]),
        role=current_user["role"],
    )
