from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RetrieverName = Literal["bm25", "dense", "hybrid"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    retriever: RetrieverName = "hybrid"
    k: int = Field(default=10, ge=1, le=100)


class HitResponse(BaseModel):
    doc_id: str
    chunk_id: str
    text: str
    score: float
    rank: int
    source_scores: dict[str, float | int | None]
    metadata: dict[str, object] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    retriever: RetrieverName
    hits: list[HitResponse]
    corpus_available: bool


class QARequest(SearchRequest):
    retriever: RetrieverName = "hybrid"
    query_type: Literal["auto", "statute_lookup", "conceptual", "fact_pattern"] = "auto"


class PassageResponse(BaseModel):
    index: int
    doc_id: str
    chunk_id: str
    text: str
    score: float
    source_scores: dict[str, float | int | None]


class QAResponse(BaseModel):
    query: str
    answer: str
    citations: list[int]
    invalid_citations: list[int]
    unsupported_sentences: list[str]
    passages: list[PassageResponse]
    confidence: float
    disclaimer: str
    refused: bool


class FeedbackRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    rating: Literal["up", "down"]
    correctness: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    accepted: bool
    feedback_id: str


class CompareResponse(BaseModel):
    query: str
    results: dict[str, list[HitResponse]]
    overlap: dict[str, float]
