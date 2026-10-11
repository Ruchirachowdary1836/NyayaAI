"""User-defined retrieval experiments run against the live corpus index.

Every system sees the same queries and corpus. Metrics are computed only for queries
that include relevance judgments; nothing is estimated or filled in.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from backend.app.services.retrieval.registry import RetrieverRegistry
from backend.app.services.retrieval.search import hit_title
from evaluation.metrics.retrieval import retrieval_metrics

_CHUNK_POOL_FACTOR = 4


def _document_ranking(registry: RetrieverRegistry, retriever: str, query: str, k: int):
    started = time.perf_counter()
    hits = registry.get(retriever).search(query, k * _CHUNK_POOL_FACTOR)
    latency_ms = (time.perf_counter() - started) * 1000
    ranking: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.doc_id in seen:
            continue
        seen.add(hit.doc_id)
        ranking.append(
            {
                "rank": len(ranking) + 1,
                "doc_id": hit.doc_id,
                "chunk_id": hit.chunk_id,
                "title": hit_title(hit),
                "score": round(float(hit.score), 6),
            }
        )
        if len(ranking) == k:
            break
    return ranking, round(latency_ms, 2)


def run_experiment(
    registry: RetrieverRegistry,
    retrievers: list[str],
    queries: list[dict[str, Any]],
    k: int,
    known_document: Any = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    cutoffs = tuple(sorted({min(5, k), k}))
    system_errors: dict[str, str] = {}
    query_results: list[dict[str, Any]] = []
    per_system_metrics: dict[str, list[dict[str, float]]] = {name: [] for name in retrievers}
    per_system_latency: dict[str, list[float]] = {name: [] for name in retrievers}
    unknown_relevant: set[str] = set()

    for query_index, item in enumerate(queries, start=1):
        relevant = list(item.get("relevant_doc_ids") or [])
        if known_document is not None:
            unknown_relevant.update(doc_id for doc_id in relevant if not known_document(doc_id))
        relevance = {doc_id: 1 for doc_id in relevant}
        systems: dict[str, Any] = {}
        for name in retrievers:
            if name in system_errors:
                systems[name] = {"error": system_errors[name]}
                continue
            try:
                ranking, latency_ms = _document_ranking(registry, name, item["query"], k)
            except RuntimeError as error:
                system_errors[name] = str(error)
                systems[name] = {"error": str(error)}
                continue
            entry: dict[str, Any] = {"ranking": ranking, "latency_ms": latency_ms}
            per_system_latency[name].append(latency_ms)
            if relevance:
                ranked_ids = [row["doc_id"] for row in ranking]
                metrics = {
                    key: round(value, 6)
                    for key, value in retrieval_metrics(ranked_ids, relevance, cutoffs).items()
                }
                entry["metrics"] = metrics
                entry["relevant_retrieved"] = sum(doc_id in relevance for doc_id in ranked_ids)
                per_system_metrics[name].append(metrics)
            systems[name] = entry
        query_results.append(
            {
                "index": query_index,
                "query": item["query"],
                "relevant_doc_ids": relevant,
                "systems": systems,
            }
        )

    judged = sum(1 for item in queries if item.get("relevant_doc_ids"))
    summary_systems: dict[str, Any] = {}
    for name in retrievers:
        if name in system_errors and not per_system_latency[name]:
            summary_systems[name] = {"status": "unavailable", "error": system_errors[name]}
            continue
        metric_rows = per_system_metrics[name]
        means = (
            {
                metric: round(statistics.fmean(row[metric] for row in metric_rows), 6)
                for metric in metric_rows[0]
            }
            if metric_rows
            else {}
        )
        latencies = per_system_latency[name]
        summary_systems[name] = {
            "status": "ok",
            "evaluated_queries": len(metric_rows),
            "metrics": means,
            "mean_latency_ms": round(statistics.fmean(latencies), 2) if latencies else None,
            "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
        }

    succeeded = [name for name, value in summary_systems.items() if value["status"] == "ok"]
    status = (
        "failed"
        if not succeeded
        else "partial"
        if len(succeeded) < len(retrievers)
        else "completed"
    )
    return {
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "results": {"queries": query_results},
        "summary": {
            "query_count": len(queries),
            "judged_query_count": judged,
            "cutoffs": list(cutoffs),
            "systems": summary_systems,
            "unknown_relevant_doc_ids": sorted(unknown_relevant),
            "corpus": {"documents": registry.document_count, "chunks": registry.corpus_size},
            "notes": (
                []
                if judged
                else [
                    "No relevance judgments were supplied, so only rankings and latency "
                    "are reported."
                ]
            ),
        },
    }
