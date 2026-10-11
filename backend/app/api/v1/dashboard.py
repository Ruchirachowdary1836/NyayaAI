from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Request

from backend.app.api.deps import DB, CurrentUser
from backend.app.db.database import utcnow

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(request: Request, user: CurrentUser, database: DB) -> dict[str, Any]:
    """Database-backed summary of the signed-in user's work and the corpus they search."""
    username = user["username"]
    retrievers = request.app.state.retrievers
    generator = request.app.state.generator
    documents, document_total = database.list_user_documents(username, limit=5)
    experiments, experiment_total = database.list_experiments(username, limit=5)
    usage = database.usage_summary(utcnow() - timedelta(days=30), username=username)
    activity: dict[str, int] = {}
    for row in usage:
        activity[row["event_type"]] = activity.get(row["event_type"], 0) + row["count"]
    return {
        "user": database.get_user_profile(username),
        "corpus": {
            "documents": retrievers.document_count,
            "chunks": retrievers.corpus_size,
            "facets": request.app.state.corpus.facets(),
        },
        "retrievers": retrievers.status(),
        "generation": {
            "provider": getattr(generator, "provider", None),
            "model": getattr(generator, "model", None),
            "configured": bool(getattr(generator, "configured", False)),
        },
        "library": {
            "total": document_total,
            "by_status": database.count_user_documents(username),
            "recent": documents,
        },
        "experiments": {
            "total": experiment_total,
            "recent": [
                {key: row[key] for key in ("experiment_id", "name", "status", "created_at")}
                for row in experiments
            ],
        },
        "activity_last_30_days": activity,
    }
