from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from backend.app.services.ingestion.loaders import load_qrels, load_queries
from backend.app.services.retrieval.bm25 import BM25Retriever
from backend.app.services.retrieval.dense import DenseRetriever
from backend.app.services.retrieval.hybrid import HybridRetriever
from backend.app.services.retrieval.service import load_chunks
from evaluation.metrics.retrieval import retrieval_metrics
from evaluation.statistics import compare_systems, holm_bonferroni


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _log_mlflow(
    config: dict[str, Any],
    run_name: str,
    metrics_summary: dict[str, Any],
    results_dir: Path,
) -> str:
    import mlflow

    tracking_config = config.get("tracking", {})
    tracking_uri = os.getenv(
        "MLFLOW_TRACKING_URI",
        tracking_config.get("tracking_uri", "file:./mlruns"),
    )
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(tracking_config.get("experiment_name", "NyayaAI retrieval"))
    with mlflow.start_run(run_name=run_name):
        active_run = mlflow.active_run()
        if active_run is None:
            raise RuntimeError("MLflow did not create an active experiment run")
        run_id = active_run.info.run_id
        metrics_summary["mlflow_run_id"] = run_id
        mlflow.log_params(
            {
                "seed": metrics_summary["seed"],
                "config_sha256": metrics_summary["config_sha256"],
                "query_count": metrics_summary["query_count"],
                "document_count": metrics_summary["document_count"],
                "chunk_count": metrics_summary["chunk_count"],
                **{
                    f"retrieval_{key}": value
                    for key, value in config.get("retrieval", {}).items()
                    if isinstance(value, (str, int, float, bool))
                },
            }
        )
        mlflow.log_metrics(
            {
                f"{system}_{metric}": score
                for system, scores in metrics_summary["systems"].items()
                for metric, score in scores.items()
            }
        )
        metrics_path = results_dir / "metrics.json"
        metrics_path.write_text(json.dumps(metrics_summary, indent=2), encoding="utf-8")
        mlflow.log_artifact(str(metrics_path), artifact_path="results")
        mlflow.log_artifact(str(results_dir / "per_query.csv"), artifact_path="results")
        return run_id


def run_experiment(config_path: str | Path) -> Path:
    with Path(config_path).open(encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    dataset_config = config.get("dataset", {})
    retrieval_config = config.get("retrieval", {})
    output_config = config.get("output", {})
    corpus_path = dataset_config.get("corpus_path", "data/processed/chunks.jsonl")
    query_path = dataset_config.get("queries_path")
    qrels_path = dataset_config.get("qrels_path")
    if not query_path or not qrels_path:
        raise ValueError("dataset.queries_path and dataset.qrels_path must be configured")
    queries = load_queries(query_path)
    qrels = load_qrels(qrels_path)
    chunks = load_chunks(corpus_path)
    if not chunks:
        raise ValueError(f"No corpus chunks found at {corpus_path}")

    bm25 = BM25Retriever(chunks)
    dense = DenseRetriever(
        chunks,
        model_name=retrieval_config.get("embedding_model", "BAAI/bge-m3"),
    )
    hybrid = HybridRetriever(
        bm25,
        dense,
        method=retrieval_config.get("fusion_method", "rrf"),
        alpha=float(retrieval_config.get("alpha", 0.7)),
        rrf_k=int(retrieval_config.get("rrf_k", 60)),
    )
    retrievers = {"bm25": bm25, "dense": dense, "hybrid": hybrid}
    top_k = int(retrieval_config.get("top_k", 10))
    seed = int(config.get("seed", 42))
    query_rows = []
    aggregate: dict[str, dict[str, list[float]]] = {name: {} for name in retrievers}

    for query in queries:
        judgments = qrels.get(query.query_id, {})
        for name, retriever in retrievers.items():
            hits = retriever.search(query.text, top_k)
            ranked_documents = list(dict.fromkeys(hit.doc_id for hit in hits))
            metrics = retrieval_metrics(
                ranked_documents,
                judgments,
                cutoffs=tuple(retrieval_config.get("cutoffs", [5, 10])),
            )
            row: dict[str, Any] = {
                "query_id": query.query_id,
                "query_type": query.query_type or "unspecified",
                "retriever": name,
                "result_doc_ids": json.dumps(ranked_documents),
            }
            row.update(metrics)
            query_rows.append(row)
            for metric, value in metrics.items():
                aggregate[name].setdefault(metric, []).append(value)

    metric_names = sorted({metric for values in aggregate.values() for metric in values})
    metrics_summary: dict[str, Any] = {
        "seed": seed,
        "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
        "query_count": len(queries),
        "document_count": len({chunk.doc_id for chunk in chunks}),
        "chunk_count": len(chunks),
        "systems": {
            name: {
                metric: sum(values) / len(values) if values else 0.0
                for metric, values in system_metrics.items()
            }
            for name, system_metrics in aggregate.items()
        },
        "comparisons": {},
    }
    comparisons = []
    for left, right in (("bm25", "dense"), ("bm25", "hybrid"), ("dense", "hybrid")):
        metrics_summary["comparisons"][f"{left}_vs_{right}"] = {}
        for metric in metric_names:
            result = compare_systems(
                aggregate[left][metric],
                aggregate[right][metric],
                seed=seed,
                bootstrap_samples=int(config.get("bootstrap_samples", 1000)),
            )
            metrics_summary["comparisons"][f"{left}_vs_{right}"][metric] = result
            comparisons.append((f"{left}_vs_{right}", metric, result["paired_t_pvalue"]))
    adjusted = holm_bonferroni([float(item[2] or 1) for item in comparisons])
    for (comparison, metric, _), adjusted_p in zip(comparisons, adjusted):
        metrics_summary["comparisons"][comparison][metric]["holm_adjusted_pvalue"] = adjusted_p

    results_root = Path(output_config.get("results_dir", "evaluation/results"))
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results_dir = results_root / run_id
    results_dir.mkdir(parents=True, exist_ok=False)
    (results_dir / "metrics.json").write_text(
        json.dumps(metrics_summary, indent=2), encoding="utf-8"
    )
    _write_csv(results_dir / "per_query.csv", query_rows)
    mlflow_run_id = _log_mlflow(config, run_id, metrics_summary, results_dir)
    print(f"MLflow run: {mlflow_run_id}")
    print(f"Experiment results: {results_dir}")
    return results_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare legal retrieval baselines.")
    parser.add_argument("--config", default="configs/experiment.yaml")
    args = parser.parse_args()
    run_experiment(args.config)


if __name__ == "__main__":
    main()
