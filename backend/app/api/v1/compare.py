from __future__ import annotations

from itertools import combinations

from fastapi import APIRouter, HTTPException, Request

from backend.app.api.deps import CurrentUser, record_usage
from backend.app.api.v1.search import _hit_response
from backend.app.schemas.retrieval import CompareRequest, CompareResponse, EngineResult
from backend.app.services.retrieval.search import timed_document_search

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=CompareResponse)
def compare(payload: CompareRequest, request: Request, user: CurrentUser) -> CompareResponse:
    """Run one query through each requested engine on the same corpus.

    Engines that are disabled or fail to load are reported in ``unavailable``; their
    results are never substituted with another engine's ranking.
    """
    registry = request.app.state.retrievers
    requested = payload.retrievers or registry.available
    engines: dict[str, EngineResult] = {}
    unavailable: dict[str, str] = {}
    for name in requested:
        try:
            hits, latency_ms = timed_document_search(registry, name, payload.query, payload.k)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            unavailable[name] = str(error)
            engines[name] = EngineResult(error=str(error))
            continue
        engines[name] = EngineResult(
            hits=[_hit_response(hit, payload.query) for hit in hits], latency_ms=latency_ms
        )
    succeeded = {name: result for name, result in engines.items() if result.error is None}
    if not succeeded:
        record_usage(request, user["username"], "compare", "error")
        raise HTTPException(status_code=503, detail="No requested retrieval engine is available.")
    doc_sets = {name: {hit.doc_id for hit in result.hits} for name, result in succeeded.items()}
    overlap = {
        f"{left}-{right}": (
            len(doc_sets[left] & doc_sets[right]) / len(doc_sets[left] | doc_sets[right])
            if doc_sets[left] | doc_sets[right]
            else 0.0
        )
        for left, right in combinations(sorted(doc_sets, key=requested.index), 2)
    }
    record_usage(
        request,
        user["username"],
        "compare",
        "ok" if not unavailable else "partial",
        result_count=sum(len(result.hits) for result in succeeded.values()),
    )
    return CompareResponse(
        query=payload.query,
        k=payload.k,
        results={name: result.hits for name, result in succeeded.items()},
        engines=engines,
        overlap=overlap,
        unavailable=unavailable,
    )
