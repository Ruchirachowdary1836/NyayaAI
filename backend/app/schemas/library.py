from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.retrieval import RetrieverName


class UserDocumentSummary(BaseModel):
    document_id: str
    title: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: Literal["processing", "ready", "failed"]
    error: str | None
    page_count: int | None
    char_count: int
    created_at: str | None
    updated_at: str | None


class UserDocumentDetail(UserDocumentSummary):
    text: str | None


class UserDocumentList(BaseModel):
    documents: list[UserDocumentSummary]
    total: int
    limit: int
    offset: int


class LibrarySearchHit(BaseModel):
    document_id: str
    title: str
    filename: str
    chunk_index: int
    excerpt: str
    score: float
    rank: int


class LibrarySearchResponse(BaseModel):
    query: str
    hits: list[LibrarySearchHit]
    searched_documents: int


class CorpusDocumentList(BaseModel):
    documents: list[dict[str, object]]
    total: int
    limit: int
    offset: int
    facets: dict[str, list[str]]


class ExperimentQuery(BaseModel):
    # Benchmark queries (e.g. AILA fact descriptions) can be several thousand characters long.
    query: str = Field(min_length=1, max_length=8000)
    relevant_doc_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("query")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query must contain text")
        return value

    @field_validator("relevant_doc_ids")
    @classmethod
    def _clean_ids(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 120 for item in cleaned):
            raise ValueError("Document IDs must be at most 120 characters")
        return cleaned


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    retrievers: list[RetrieverName] = Field(min_length=1, max_length=3)
    k: int = Field(default=10, ge=1, le=50)
    queries: list[ExperimentQuery] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must contain text")
        return value

    @field_validator("retrievers")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class ExperimentSummary(BaseModel):
    experiment_id: str
    name: str
    status: Literal["completed", "partial", "failed"]
    config: dict[str, object]
    summary: dict[str, object]
    duration_ms: float
    created_at: str | None


class ExperimentDetail(ExperimentSummary):
    results: dict[str, object]


class ExperimentList(BaseModel):
    experiments: list[ExperimentSummary]
    total: int
    limit: int
    offset: int
