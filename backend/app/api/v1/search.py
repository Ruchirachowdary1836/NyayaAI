from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.app.api.deps import CurrentUser, record_usage
from backend.app.schemas.retrieval import HitResponse, SearchRequest, SearchResponse
from backend.app.services.retrieval.base import Hit
from backend.app.services.retrieval.search import (
    SearchFilters,
    best_excerpt,
    hit_title,
    run_search,
)

router = APIRouter(tags=["search"])


def _hit_response(hit: Hit, query: str = "") -> HitResponse:
    return HitResponse(
        doc_id=hit.doc_id,
        chunk_id=hit.chunk_id,
        title=hit_title(hit),
        text=hit.text,
        excerpt=best_excerpt(hit.text, query) if query else hit.text[:360],
        score=hit.score,
        rank=hit.rank,
        source_scores=hit.source_scores,
        metadata=dict(hit.metadata),
    )


def retrieval_error(error: Exception) -> HTTPException:
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=503, detail=str(error))


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, request: Request, user: CurrentUser) -> SearchResponse:
    registry = request.app.state.retrievers
    if (
        payload.year_from is not None
        and payload.year_to is not None
        and payload.year_from > payload.year_to
    ):
        raise HTTPException(status_code=422, detail="year_from must not be after year_to")
    try:
        result = run_search(
            registry,
            payload.retriever,
            payload.query,
            filters=SearchFilters(
                document_type=payload.document_type,
                court=payload.court,
                year_from=payload.year_from,
                year_to=payload.year_to,
            ),
            group_by_document=payload.group_by_document,
            sort=payload.sort,
            page=payload.page,
            page_size=payload.k,
        )
    except (ValueError, RuntimeError) as error:
        record_usage(request, user["username"], "search", "error", retriever=payload.retriever)
        raise retrieval_error(error) from error
    record_usage(
        request,
        user["username"],
        "search",
        "ok",
        retriever=payload.retriever,
        result_count=result.total,
        latency_ms=result.latency_ms,
    )
    return SearchResponse(
        query=payload.query,
        retriever=payload.retriever,
        hits=[_hit_response(hit, payload.query) for hit in result.hits],
        corpus_available=registry.corpus_size > 0,
        page=payload.page,
        page_size=payload.k,
        total=result.total,
        total_is_capped=result.total_is_capped,
        latency_ms=result.latency_ms,
        filters=result.filters,
    )
