from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.app.services.ingestion.loaders import load_qrels, load_queries
from backend.app.services.retrieval.bm25 import BM25Retriever
from backend.app.services.retrieval.service import load_chunks
from evaluation.metrics.retrieval import retrieval_metrics

SOURCE_URL = "https://doi.org/10.5281/zenodo.4063986"
ATTRIBUTION = (
    "Paheli Bhattacharya, Kripabandhu Ghosh, Saptarshi Ghosh, Arindam Pal, "
    "Parth Mehta, Arnab Bhattacharya, and Prasenjit Majumder"
)
TASK_DOCUMENT_TYPES = {"priorcases": "judgment", "statutes": "statute"}


def _mean_metrics(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        raise ValueError("Cannot calculate benchmark metrics without evaluated queries")
    metric_names = rows[0]
    return {metric: sum(row[metric] for row in rows) / len(rows) for metric in metric_names}


def seed_benchmark(
    chunks_path: str | Path,
    queries_path: str | Path,
    priorcase_qrels_path: str | Path,
    statute_qrels_path: str | Path,
    results_dir: str | Path,
) -> Path:
    chunks = load_chunks(chunks_path)
    queries = load_queries(queries_path)
    if not chunks or not queries:
        raise ValueError("The AILA benchmark requires a non-empty corpus and query set")

    qrels_by_task = {
        task: load_qrels(qrels_path)
        for task, qrels_path in (
            ("priorcases", priorcase_qrels_path),
            ("statutes", statute_qrels_path),
        )
    }
    task_summaries: dict[str, dict[str, Any]] = {}
    aggregate_rows: list[dict[str, float]] = []

    for task, document_type in TASK_DOCUMENT_TYPES.items():
        task_chunks = [
            chunk for chunk in chunks if chunk.metadata.get("document_type") == document_type
        ]
        if not task_chunks:
            raise ValueError(f"The corpus has no chunks for the AILA {task} task")
        task_queries = [
            query
            for query in queries
            if query.query_type == task and query.query_id in qrels_by_task[task]
        ]
        if not task_queries:
            raise ValueError(f"The AILA {task} task has no queries with relevance judgments")

        retriever = BM25Retriever(task_chunks)
        rows: list[dict[str, float]] = []
        expected_document_ids = {chunk.doc_id for chunk in task_chunks}
        relevance_document_ids = {
            document_id for judgments in qrels_by_task[task].values() for document_id in judgments
        }
        missing_document_ids = sorted(relevance_document_ids - expected_document_ids)
        for query in task_queries:
            relevance = qrels_by_task[task][query.query_id]
            ranked_documents = list(
                dict.fromkeys(hit.doc_id for hit in retriever.search(query.text, k=10))
            )
            rows.append(retrieval_metrics(ranked_documents, relevance, cutoffs=(5, 10)))

        aggregate_rows.extend(rows)
        task_summaries[task] = {
            "query_count": len(rows),
            "document_count": len(expected_document_ids),
            "chunk_count": len(task_chunks),
            "missing_judged_document_ids": missing_document_ids,
            "missing_judged_document_count": len(missing_document_ids),
            "systems": {"bm25": _mean_metrics(rows)},
        }

    run = {
        "run_id": "aila-2019-bm25",
        "dataset_name": "AILA 2019 Precedent & Statute Retrieval Task",
        "source_url": SOURCE_URL,
        "license": "CC BY 4.0",
        "attribution": ATTRIBUTION,
        "evaluation_protocol": (
            "Official AILA queries evaluated separately for prior-case and statute retrieval; "
            "BM25 top-10 passages deduplicated by document; task-specific judged pools. "
            "Relevant judgments absent from the indexed corpus remain in metric denominators."
        ),
        "query_count": len(aggregate_rows),
        "document_count": len({chunk.doc_id for chunk in chunks}),
        "chunk_count": len(chunks),
        "systems": {"bm25": _mean_metrics(aggregate_rows)},
        "tasks": task_summaries,
    }

    run_dir = Path(results_dir) / "aila-2019-bm25"
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = run_dir / "metrics.json"
    metrics_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    return metrics_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate the BM25 baseline on official AILA 2019 judgments."
    )
    parser.add_argument("--chunks", default="data/processed/chunks.jsonl")
    parser.add_argument("--queries", default="data/processed/aila_evaluation/queries.jsonl")
    parser.add_argument(
        "--priorcase-qrels",
        default="data/processed/aila_evaluation/qrels_priorcases.jsonl",
    )
    parser.add_argument(
        "--statute-qrels",
        default="data/processed/aila_evaluation/qrels_statutes.jsonl",
    )
    parser.add_argument("--results-dir", default="evaluation/results")
    args = parser.parse_args()
    path = seed_benchmark(
        args.chunks,
        args.queries,
        args.priorcase_qrels,
        args.statute_qrels,
        args.results_dir,
    )
    print(f"Wrote official AILA BM25 baseline metrics to {path}")


if __name__ == "__main__":
    main()
