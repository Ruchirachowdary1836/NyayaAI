from __future__ import annotations

import json
import platform
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.api.deps import DB, AdminUser
from backend.app.core.config import settings
from backend.app.db.database import utcnow
from backend.app.schemas.auth import AdminOverview, UserAccessUpdate, UserList, UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


def _benchmark_count(results: Path) -> int:
    if not results.is_dir():
        return 0
    return sum(
        1 for path in results.iterdir() if path.is_dir() and (path / "metrics.json").is_file()
    )


def ingestion_status(processed_dir: Path) -> dict[str, Any]:
    status: dict[str, Any] = {}
    for name in ("ingestion_report.json", "corpus_statistics.json"):
        path = processed_dir / name
        if path.is_file():
            try:
                status[path.stem] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                status[path.stem] = {"error": "unreadable"}
    for key, value in (
        ("chunks", settings.data_chunks_path),
        ("documents", settings.data_documents_path),
    ):
        path = Path(value)
        status[f"{key}_file"] = {
            "present": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else 0,
        }
    report = status.get("ingestion_report")
    if isinstance(report, dict):
        # Lists of skipped IDs can be long; the overview reports counts.
        for key in ("skipped_duplicate_ids", "skipped_empty_documents"):
            if isinstance(report.get(key), list):
                report[key] = len(report[key])
    return status


@router.get("/overview", response_model=AdminOverview)
def overview(request: Request, _: AdminUser, database: DB) -> AdminOverview:
    now = utcnow()
    retrievers = request.app.state.retrievers
    generator = request.app.state.generator
    return AdminOverview(
        corpus_documents=retrievers.document_count,
        corpus_chunks=retrievers.corpus_size,
        experiment_runs=database.count_experiments(),
        benchmark_runs=_benchmark_count(request.app.state.results_dir),
        users=database.count_users(),
        active_users=database.count_users(active_only=True),
        users_active_last_7_days=database.active_user_count(now - timedelta(days=7)),
        uploaded_documents=database.count_user_documents(),
        uploaded_bytes=database.total_user_document_bytes(),
        feedback=database.count_feedback(),
        usage_last_24h=database.usage_summary(now - timedelta(hours=24)),
        usage_last_7d=database.usage_summary(now - timedelta(days=7)),
        retrievers=retrievers.status(),
        ingestion=ingestion_status(Path(settings.data_documents_path).parent),
        system={
            "database": "ok" if database.ping() else "unreachable",
            "database_backend": "sqlite" if database.is_sqlite else "postgresql",
            "schema_revision": database.schema_revision(),
            "generation_provider": getattr(generator, "provider", settings.generator_provider),
            "generation_model": getattr(generator, "model", None),
            "generation_configured": bool(getattr(generator, "configured", False)),
            "environment": settings.app_env,
            "python": platform.python_version(),
        },
    )


@router.get("/users", response_model=UserList)
def list_users(
    _: AdminUser,
    database: DB,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserList:
    rows, total = database.list_users(limit=limit, offset=offset, query=q)
    return UserList(
        users=[UserResponse(**row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.patch("/users/{username}", response_model=UserResponse)
def update_user(
    username: str, payload: UserAccessUpdate, admin: AdminUser, database: DB
) -> UserResponse:
    target = database.get_user_profile(username)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if username == admin["username"] and (payload.role == "user" or payload.is_active is False):
        raise HTTPException(
            status_code=409, detail="You cannot remove your own administrator access."
        )
    removes_admin = (
        target["role"] == "admin"
        and target["is_active"]
        and (payload.role == "user" or payload.is_active is False)
    )
    if removes_admin and database.count_active_admins() <= 1:
        raise HTTPException(
            status_code=409, detail="At least one active administrator is required."
        )
    database.update_user_access(username, role=payload.role, is_active=payload.is_active)
    updated = database.get_user_profile(username)
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**updated)
