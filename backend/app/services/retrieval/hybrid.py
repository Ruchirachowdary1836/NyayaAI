from __future__ import annotations

from backend.app.services.retrieval.base import Hit, Retriever


class HybridRetriever:
    name = "hybrid"

    def __init__(
        self,
        bm25: Retriever,
        dense: Retriever,
        method: str = "rrf",
        alpha: float = 0.7,
        rrf_k: int = 60,
    ) -> None:
        if method not in {"rrf", "weighted"}:
            raise ValueError("method must be 'rrf' or 'weighted'")
        if not 0 <= alpha <= 1:
            raise ValueError("alpha must be in [0, 1]")
        if rrf_k < 1:
            raise ValueError("rrf_k must be greater than zero")
        self.bm25 = bm25
        self.dense = dense
        self.method = method
        self.alpha = alpha
        self.rrf_k = rrf_k

    def search(self, query: str, k: int = 10) -> list[Hit]:
        if k < 1:
            raise ValueError("k must be greater than zero")
        sparse = self.bm25.search(query, max(k * 3, k))
        dense = self.dense.search(query, max(k * 3, k))
        hits: dict[str, Hit] = {}
        ranks: dict[str, dict[str, int]] = {"bm25": {}, "dense": {}}
        for retriever_name, result in (("bm25", sparse), ("dense", dense)):
            for hit in result:
                hits.setdefault(hit.chunk_id, hit)
                ranks[retriever_name][hit.chunk_id] = hit.rank

        if self.method == "rrf":
            scores = {
                chunk_id: sum(
                    1 / (self.rrf_k + rank)
                    for retriever_ranks in ranks.values()
                    if (rank := retriever_ranks.get(chunk_id)) is not None
                )
                for chunk_id in hits
            }
        else:

            def normalized(results: list[Hit]) -> dict[str, float]:
                maximum = max((hit.score for hit in results), default=0.0)
                minimum = min((hit.score for hit in results), default=0.0)
                delta = maximum - minimum
                return {
                    hit.chunk_id: (hit.score - minimum) / delta if delta else 0.0 for hit in results
                }

            sparse_scores = normalized(sparse)
            dense_scores = normalized(dense)
            scores = {
                chunk_id: (1 - self.alpha) * sparse_scores.get(chunk_id, 0.0)
                + self.alpha * dense_scores.get(chunk_id, 0.0)
                for chunk_id in hits
            }

        ordered = sorted(hits, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
        return [
            Hit(
                doc_id=hits[chunk_id].doc_id,
                chunk_id=chunk_id,
                text=hits[chunk_id].text,
                score=scores[chunk_id],
                rank=rank,
                source_scores={
                    "bm25": hits[chunk_id].source_scores.get("bm25"),
                    "dense": hits[chunk_id].source_scores.get("dense"),
                    "bm25_rank": ranks["bm25"].get(chunk_id),
                    "dense_rank": ranks["dense"].get(chunk_id),
                    "fused": scores[chunk_id],
                },
                metadata=hits[chunk_id].metadata,
            )
            for rank, chunk_id in enumerate(ordered[:k], start=1)
        ]
