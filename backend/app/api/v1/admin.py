from __future__ import annotations

from typing import Annotated

from backend.app.db.database import as_database
from backend.app.schemas.auth import AdminOverview, UserResponse
from backend.app.services.auth import bearer_auth, get_current_user, require_admin
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_auth)],
) -> dict[str, str]:
    user = get_current_user(request, credentials)
    require_admin(user)
    return user


@router.get("/overview", response_model=AdminOverview)
def overview(request: Request, _: Annotated[dict[str, str], Depends(_admin_user)]) -> AdminOverview:
    user_count = as_database(request.app.state.auth_db).count_users()
    results = request.app.state.results_dir
    experiment_count = (
        sum(1 for path in results.iterdir() if path.is_dir() and (path / "metrics.json").is_file())
        if results.is_dir()
        else 0
    )
    retrievers = request.app.state.retrievers
    return AdminOverview(
        corpus_documents=retrievers.document_count,
        corpus_chunks=retrievers.corpus_size,
        experiment_runs=experiment_count,
        users=user_count,
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(
    request: Request, _: Annotated[dict[str, str], Depends(_admin_user)]
) -> list[UserResponse]:
    rows = as_database(request.app.state.auth_db).list_users()
    return [
        UserResponse(username=username, role=role, created_at=created_at)
        for username, role, created_at in rows
    ]
