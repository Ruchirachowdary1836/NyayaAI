from __future__ import annotations

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.base import Hit, legal_tokenize


class BM25Retriever:
    name = "bm25"

    def __init__(self, chunks: list[LegalChunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self._index = None
        self._corpus_tokens: list[list[str]] = []
        if chunks:
            from rank_bm25 import BM25Okapi

            self._corpus_tokens = [legal_tokenize(chunk.text) for chunk in chunks]
            self._index = BM25Okapi(self._corpus_tokens, k1=k1, b=b)

    def search(self, query: str, k: int = 10) -> list[Hit]:
        if k < 1:
            raise ValueError("k must be greater than zero")
        query_tokens = legal_tokenize(query)
        if not query_tokens or self._index is None:
            return []
        scores = self._index.get_scores(query_tokens)
        ranked = sorted(enumerate(scores), key=lambda item: (-float(item[1]), item[0]))
        query_terms = set(query_tokens)
        matched = [
            (index, float(score))
            for index, score in ranked
            if query_terms.intersection(self._corpus_tokens[index])
        ][:k]
        return [
            Hit(
                doc_id=self.chunks[index].doc_id,
                chunk_id=self.chunks[index].chunk_id,
                text=self.chunks[index].text,
                score=score,
                rank=rank,
                source_scores={"bm25": score},
            )
            for rank, (index, score) in enumerate(matched, start=1)
        ]
