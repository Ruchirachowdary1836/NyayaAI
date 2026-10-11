from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from backend.app.api.deps import DB, CurrentUser, record_usage
from backend.app.core.config import settings
from backend.app.schemas.library import (
    ExperimentCreate,
    ExperimentDetail,
    ExperimentList,
    ExperimentSummary,
)
from backend.app.services.experiments import run_experiment

router = APIRouter(prefix="/experiments", tags=["experiments"])
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


# ---------------------------------------------------------------- benchmark runs
@router.get("/benchmarks")
def list_benchmarks(request: Request, _: CurrentUser) -> list[dict[str, object]]:
    """Offline benchmark runs recorded under ``evaluation/results`` (e.g. AILA 2019)."""
    results_dir: Path = request.app.state.results_dir
    if not results_dir.is_dir():
        return []
    runs = []
    for path in sorted(results_dir.iterdir(), reverse=True):
        metrics = path / "metrics.json"
        if path.is_dir() and _RUN_ID.fullmatch(path.name) and metrics.is_file():
            runs.append({"run_id": path.name, **json.loads(metrics.read_text(encoding="utf-8"))})
    return runs


@router.get("/benchmarks/{run_id}")
def get_benchmark(run_id: str, request: Request, _: CurrentUser) -> dict[str, object]:
    if not _RUN_ID.fullmatch(run_id):
        raise HTTPException(status_code=422, detail="Invalid run ID")
    metrics_path = request.app.state.results_dir / run_id / "metrics.json"
    if not metrics_path.is_file():
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return {"run_id": run_id, **json.loads(metrics_path.read_text(encoding="utf-8"))}


# -------------------------------------------------------------- user experiments
@router.post("/runs", response_model=ExperimentDetail, status_code=201)
async def create_experiment(
    payload: ExperimentCreate, request: Request, user: CurrentUser, database: DB
) -> ExperimentDetail:
    if len(payload.queries) > settings.experiment_max_queries:
        raise HTTPException(
            status_code=422,
            detail=f"Experiments are limited to {settings.experiment_max_queries} queries.",
        )
    registry = request.app.state.retrievers
    disabled = [name for name in payload.retrievers if name not in registry.available]
    if disabled:
        raise HTTPException(
            status_code=422,
            detail=f"Not enabled on this deployment: {', '.join(disabled)}.",
        )
    corpus = request.app.state.corpus
    outcome = await asyncio.to_thread(
        run_experiment,
        registry,
        list(payload.retrievers),
        [query.model_dump() for query in payload.queries],
        payload.k,
        corpus.__contains__ if len(corpus) else None,
    )
    experiment_id = str(uuid.uuid4())
    config = {
        "retrievers": list(payload.retrievers),
        "k": payload.k,
        "query_count": len(payload.queries),
        "hybrid": {
            "method": settings.hybrid_method,
            "alpha": settings.hybrid_alpha,
            "rrf_k": settings.hybrid_rrf_k,
        },
        "embedding_model": settings.embedding_model,
    }
    database.insert_experiment(
        {
            "experiment_id": experiment_id,
            "owner": user["username"],
            "name": payload.name,
            "status": outcome["status"],
            "config": config,
            "results": outcome["results"],
            "summary": outcome["summary"],
            "duration_ms": outcome["duration_ms"],
        }
    )
    record_usage(
        request,
        user["username"],
        "experiment",
        outcome["status"],
        result_count=len(payload.queries),
        latency_ms=outcome["duration_ms"],
    )
    stored = database.get_experiment(user["username"], experiment_id)
    if stored is None:
        raise HTTPException(status_code=500, detail="Experiment could not be saved")
    return ExperimentDetail(**stored)


@router.get("/runs", response_model=ExperimentList)
def list_experiments(
    user: CurrentUser,
    database: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExperimentList:
    rows, total = database.list_experiments(user["username"], limit=limit, offset=offset)
    return ExperimentList(
        experiments=[ExperimentSummary(**row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(experiment_id: str, user: CurrentUser, database: DB) -> ExperimentDetail:
    row = database.get_experiment(user["username"], experiment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ExperimentDetail(**row)


@router.delete("/runs/{experiment_id}", status_code=204)
def delete_experiment(experiment_id: str, user: CurrentUser, database: DB) -> Response:
    if not database.delete_experiment(user["username"], experiment_id):
        raise HTTPException(status_code=404, detail="Experiment not found")
    return Response(status_code=204)
