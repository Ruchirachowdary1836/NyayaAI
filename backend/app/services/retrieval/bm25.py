from __future__ import annotations

import math
from array import array
from collections import Counter

import numpy as np

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.base import Hit, legal_tokenize


class BM25Retriever:
    name = "bm25"

    def __init__(self, chunks: list[LegalChunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self._postings: dict[str, tuple[array, array]] = {}
        self._doc_lengths = np.empty(len(chunks), dtype=np.float64)
        self._average_doc_length = 0.0
        self._idf: dict[str, float] = {}
        if not chunks:
            return

        for document_index, chunk in enumerate(chunks):
            tokens = legal_tokenize(chunk.text)
            self._doc_lengths[document_index] = len(tokens)
            for term, frequency in Counter(tokens).items():
                postings = self._postings.get(term)
                if postings is None:
                    postings = (array("I"), array("I"))
                    self._postings[term] = postings
                postings[0].append(document_index)
                postings[1].append(frequency)

        if not self._postings:
            return
        self._average_doc_length = float(self._doc_lengths.mean())
        document_count = len(chunks)
        idf_total = 0.0
        for term, (document_indices, _) in self._postings.items():
            document_frequency = len(document_indices)
            idf = math.log(document_count - document_frequency + 0.5) - math.log(
                document_frequency + 0.5
            )
            self._idf[term] = idf
            idf_total += idf

        average_idf = idf_total / len(self._idf)
        floor_idf = 0.25 * average_idf
        for term, idf in self._idf.items():
            if idf < 0:
                self._idf[term] = floor_idf

    def search(self, query: str, k: int = 10) -> list[Hit]:
        if k < 1:
            raise ValueError("k must be greater than zero")
        query_tokens = legal_tokenize(query)
        if not query_tokens or not self._postings:
            return []
        scores = np.zeros(len(self.chunks), dtype=np.float64)
        candidates: set[int] = set()
        for term in query_tokens:
            postings = self._postings.get(term)
            if postings is None:
                continue
            document_indices = np.frombuffer(postings[0], dtype=np.uint32)
            frequencies = np.frombuffer(postings[1], dtype=np.uint32)
            candidates.update(int(index) for index in document_indices)
            document_lengths = self._doc_lengths[document_indices]
            denominator = frequencies + self.k1 * (
                1 - self.b + self.b * document_lengths / self._average_doc_length
            )
            scores[document_indices] += self._idf[term] * frequencies * (self.k1 + 1) / denominator
        ranked = sorted(candidates, key=lambda index: (-float(scores[index]), index))[:k]
        return [
            Hit(
                doc_id=self.chunks[index].doc_id,
                chunk_id=self.chunks[index].chunk_id,
                text=self.chunks[index].text,
                score=float(scores[index]),
                rank=rank,
                source_scores={"bm25": float(scores[index])},
                metadata=self.chunks[index].metadata,
            )
            for rank, index in enumerate(ranked, start=1)
        ]
