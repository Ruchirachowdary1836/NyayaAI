from __future__ import annotations

from backend.app.api.v1.search import _hit_response
from backend.app.schemas.retrieval import CompareResponse, SearchRequest
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=CompareResponse)
def compare(payload: SearchRequest, request: Request) -> CompareResponse:
    registry = request.app.state.retrievers
    results = {}
    try:
        for name in registry.available:
            results[name] = registry.get(name).search(payload.query, payload.k)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    id_sets = {name: {hit.doc_id for hit in hits} for name, hits in results.items()}
    overlap = {
        f"{left}-{right}": (
            len(id_sets[left] & id_sets[right]) / len(id_sets[left] | id_sets[right])
            if id_sets[left] | id_sets[right]
            else 0.0
        )
        for left, right in (("bm25", "dense"), ("bm25", "hybrid"), ("dense", "hybrid"))
    }
    return CompareResponse(
        query=payload.query,
        results={name: [_hit_response(hit) for hit in hits] for name, hits in results.items()},
        overlap=overlap,
    )
