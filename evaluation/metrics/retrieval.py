from __future__ import annotations

import math
from collections.abc import Sequence


def precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    _validate_k(k)
    return sum(document_id in relevant for document_id in ranked[:k]) / k


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    _validate_k(k)
    return (
        sum(document_id in relevant for document_id in ranked[:k]) / len(relevant)
        if relevant
        else 0.0
    )


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    return next(
        (1 / rank for rank, document_id in enumerate(ranked, start=1) if document_id in relevant),
        0.0,
    )


def average_precision(ranked: Sequence[str], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    matches = 0
    total = 0.0
    for rank, document_id in enumerate(ranked, start=1):
        if document_id in relevant:
            matches += 1
            total += matches / rank
    return total / len(relevant)


def ndcg_at_k(ranked: Sequence[str], relevance: dict[str, int], k: int) -> float:
    _validate_k(k)

    def dcg(scores: Sequence[int]) -> float:
        return sum(
            (2**score - 1) / math.log2(rank + 1) for rank, score in enumerate(scores, start=1)
        )

    actual = [relevance.get(document_id, 0) for document_id in ranked[:k]]
    ideal = sorted(relevance.values(), reverse=True)[:k]
    ideal_score = dcg(ideal)
    return dcg(actual) / ideal_score if ideal_score else 0.0


def retrieval_metrics(
    ranked: Sequence[str], relevance: dict[str, int], cutoffs: tuple[int, ...] = (5, 10)
) -> dict[str, float]:
    relevant = {document_id for document_id, score in relevance.items() if score > 0}
    metrics = {
        f"precision@{cutoff}": precision_at_k(ranked, relevant, cutoff) for cutoff in cutoffs
    }
    metrics.update(
        {f"recall@{cutoff}": recall_at_k(ranked, relevant, cutoff) for cutoff in cutoffs}
    )
    metrics["map"] = average_precision(ranked, relevant)
    metrics["mrr"] = reciprocal_rank(ranked, relevant)
    metrics["ndcg@10"] = ndcg_at_k(ranked, relevance, 10)
    return metrics


def _validate_k(k: int) -> None:
    if k < 1:
        raise ValueError("k must be greater than zero")
