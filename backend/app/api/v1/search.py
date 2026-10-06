from __future__ import annotations

from backend.app.schemas.retrieval import HitResponse, SearchRequest, SearchResponse
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["search"])


def _hit_response(hit) -> HitResponse:
    return HitResponse(
        doc_id=hit.doc_id,
        chunk_id=hit.chunk_id,
        text=hit.text,
        score=hit.score,
        rank=hit.rank,
        source_scores=hit.source_scores,
        metadata=hit.metadata,
    )


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, request: Request) -> SearchResponse:
    registry = request.app.state.retrievers
    try:
        hits = registry.get(payload.retriever).search(payload.query, payload.k)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return SearchResponse(
        query=payload.query,
        retriever=payload.retriever,
        hits=[_hit_response(hit) for hit in hits],
        corpus_available=bool(registry._chunks),
    )
