from __future__ import annotations

from backend.app.services.retrieval.base import Hit


def confidence_score(hits: list[Hit], citations: list[int]) -> float:
    if not hits:
        return 0.0
    top_score = hits[0].score
    next_score = hits[1].score if len(hits) > 1 else 0.0
    margin = max(0.0, min(1.0, (top_score - next_score) / max(abs(top_score), 1e-9)))
    source_ranks = [hit.source_scores for hit in hits[:5]]
    agreement = (
        sum(
            1
            for scores in source_ranks
            if scores.get("bm25_rank") is not None and scores.get("dense_rank") is not None
        )
        / len(source_ranks)
        if source_ranks
        else 0.0
    )
    coverage = min(1.0, len(set(citations)) / min(3, len(hits)))
    return round(0.4 * margin + 0.35 * agreement + 0.25 * coverage, 4)
