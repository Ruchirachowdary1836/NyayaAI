"""Retrieval services for BM25, dense, and hybrid search."""

from backend.app.services.retrieval.base import Hit, Retriever
from backend.app.services.retrieval.bm25 import BM25Retriever
from backend.app.services.retrieval.dense import DenseRetriever
from backend.app.services.retrieval.hybrid import HybridRetriever
from backend.app.services.retrieval.registry import RetrieverRegistry

__all__ = [
    "BM25Retriever",
    "DenseRetriever",
    "Hit",
    "HybridRetriever",
    "Retriever",
    "RetrieverRegistry",
]
