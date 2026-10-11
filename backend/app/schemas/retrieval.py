from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

RetrieverName = Literal["bm25", "dense", "hybrid"]
QueryType = Literal["auto", "statute_lookup", "conceptual", "fact_pattern"]


class QueryModel(BaseModel):
    query: str = Field(min_length=1, max_length=2000)

    @field_validator("query")
    @classmethod
    def _query_has_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query must contain text")
        return value


class SearchRequest(QueryModel):
    retriever: RetrieverName = "bm25"
    k: int = Field(default=10, ge=1, le=50, description="Page size (results per page)")
    page: int = Field(default=1, ge=1, le=10)
    document_type: str | None = Field(default=None, max_length=40)
    court: str | None = Field(default=None, max_length=120)
    year_from: int | None = Field(default=None, ge=1800, le=2100)
    year_to: int | None = Field(default=None, ge=1800, le=2100)
    group_by_document: bool = True
    sort: Literal["relevance", "title", "document", "newest", "oldest"] = "relevance"


class CompareRequest(QueryModel):
    k: int = Field(default=10, ge=1, le=20)
    retrievers: list[RetrieverName] | None = None


class HitResponse(BaseModel):
    doc_id: str
    chunk_id: str
    title: str
    text: str
    excerpt: str
    score: float
    rank: int
    source_scores: dict[str, float | int | None]
    metadata: dict[str, object] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    retriever: RetrieverName
    hits: list[HitResponse]
    corpus_available: bool
    page: int
    page_size: int
    total: int
    total_is_capped: bool
    latency_ms: float
    filters: dict[str, str | int | None]


class QARequest(QueryModel):
    retriever: RetrieverName = "bm25"
    k: int = Field(default=8, ge=1, le=20)
    query_type: QueryType = "auto"


class PassageResponse(BaseModel):
    index: int
    doc_id: str
    chunk_id: str
    title: str
    text: str
    score: float
    source_scores: dict[str, float | int | None]
    metadata: dict[str, object] = Field(default_factory=dict)


class QAResponse(BaseModel):
    query: str
    answer: str
    citations: list[int]
    invalid_citations: list[int]
    unsupported_sentences: list[str]
    interpretation: str | None = None
    passages: list[PassageResponse]
    confidence: float
    disclaimer: str
    refused: bool
    refusal_reason: str | None = None
    model: str | None = None
    provider: str | None = None


class FeedbackRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    rating: Literal["up", "down"]
    correctness: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    accepted: bool
    feedback_id: str


class EngineResult(BaseModel):
    hits: list[HitResponse] = Field(default_factory=list)
    latency_ms: float | None = None
    error: str | None = None


class CompareResponse(BaseModel):
    query: str
    k: int
    results: dict[str, list[HitResponse]]
    engines: dict[str, EngineResult]
    overlap: dict[str, float]
    unavailable: dict[str, str]
