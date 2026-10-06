from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/experiments", tags=["experiments"])
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


@router.get("")
def list_experiments(request: Request) -> list[dict[str, object]]:
    results_dir: Path = request.app.state.results_dir
    if not results_dir.is_dir():
        return []
    runs = []
    for path in sorted(results_dir.iterdir(), reverse=True):
        metrics = path / "metrics.json"
        if path.is_dir() and metrics.is_file():
            runs.append({"run_id": path.name, **json.loads(metrics.read_text(encoding="utf-8"))})
    return runs


@router.get("/{run_id}")
def get_experiment(run_id: str, request: Request) -> dict[str, object]:
    if not _RUN_ID.fullmatch(run_id):
        raise HTTPException(status_code=400, detail="Invalid run ID")
    metrics_path = request.app.state.results_dir / run_id / "metrics.json"
    if not metrics_path.is_file():
        raise HTTPException(status_code=404, detail="Experiment run not found")
    return {"run_id": run_id, **json.loads(metrics_path.read_text(encoding="utf-8"))}
