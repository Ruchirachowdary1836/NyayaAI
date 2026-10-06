from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from evaluation.run_experiment import _log_mlflow


def test_logs_experiment_metrics_and_artifacts(tmp_path, monkeypatch):
    mlflow = MagicMock()
    active_run = SimpleNamespace(info=SimpleNamespace(run_id="test-run-id"))
    mlflow.active_run.return_value = active_run
    monkeypatch.setitem(sys.modules, "mlflow", mlflow)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    (tmp_path / "per_query.csv").write_text("query_id\nq1\n", encoding="utf-8")
    summary = {
        "seed": 42,
        "config_sha256": "abc123",
        "query_count": 1,
        "document_count": 2,
        "chunk_count": 3,
        "systems": {"bm25": {"ndcg@5": 0.5}},
    }

    run_id = _log_mlflow(
        {
            "retrieval": {"top_k": 10, "embedding_model": "test-model"},
            "tracking": {
                "tracking_uri": "file:./mlruns",
                "experiment_name": "NyayaAI tests",
            },
        },
        "test-run",
        summary,
        tmp_path,
    )

    assert run_id == "test-run-id"
    mlflow.set_tracking_uri.assert_called_once_with("file:./mlruns")
    mlflow.set_experiment.assert_called_once_with("NyayaAI tests")
    mlflow.log_params.assert_called_once()
    mlflow.log_metrics.assert_called_once_with({"bm25_ndcg@5": 0.5})
    assert mlflow.log_artifact.call_count == 2
    saved_metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert saved_metrics["mlflow_run_id"] == run_id
