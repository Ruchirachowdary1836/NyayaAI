from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.app.api.deps import limit_generation, record_usage
from backend.app.api.v1.search import retrieval_error
from backend.app.core.config import settings
from backend.app.schemas.retrieval import QARequest, QAResponse
from backend.app.services.generation.llm import GenerationError
from backend.app.services.generation.pipeline import (
    PreparedQuestion,
    finalize_answer,
    prepare_question,
    refusal_payload,
)

router = APIRouter(prefix="/qa", tags=["qa"])
GenerationUser = Annotated[dict[str, Any], Depends(limit_generation)]


def _require_generator(request: Request):
    generator = request.app.state.generator
    if not getattr(generator, "configured", True):
        # Explicit configuration error; retrieval-only features keep working.
        raise HTTPException(
            status_code=503,
            detail=(
                "AI answer generation is not configured. Set GENERATOR_API_KEY in the API "
                "service. Search and document review remain available."
            ),
        )
    return generator


def _retrieve(request: Request, payload: QARequest, username: str) -> PreparedQuestion | None:
    registry = request.app.state.retrievers
    try:
        hits = registry.get(payload.retriever).search(payload.query, max(payload.k, 5))
    except (ValueError, RuntimeError) as error:
        record_usage(request, username, "qa", "error", retriever=payload.retriever)
        raise retrieval_error(error) from error
    if not hits:
        return None
    return prepare_question(
        payload.query, hits, payload.query_type, passage_chars=settings.qa_passage_chars
    )


def _model_fields(generator) -> dict[str, str | None]:
    return {
        "model": getattr(generator, "model", None),
        "provider": getattr(generator, "provider", settings.generator_provider),
    }


@router.post("", response_model=QAResponse)
async def answer(payload: QARequest, request: Request, user: GenerationUser) -> QAResponse:
    generator = _require_generator(request)
    started = time.perf_counter()
    prepared = _retrieve(request, payload, user["username"])
    if prepared is None:
        record_usage(request, user["username"], "qa", "no_evidence", retriever=payload.retriever)
        return QAResponse(**refusal_payload(payload.query), **_model_fields(generator))
    try:
        answer_text = await generator.generate(prepared.prompt)
    except GenerationError as error:
        record_usage(request, user["username"], "qa", error.kind, retriever=payload.retriever)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    result = finalize_answer(prepared, answer_text)
    record_usage(
        request,
        user["username"],
        "qa",
        result["refusal_reason"] or "ok",
        retriever=payload.retriever,
        result_count=len(result["citations"]),
        latency_ms=(time.perf_counter() - started) * 1000,
    )
    return QAResponse(**result, **_model_fields(generator))


def _event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream")
async def stream_answer(
    payload: QARequest, request: Request, user: GenerationUser
) -> StreamingResponse:
    """Stream tokens as server-sent events, then a final audited ``complete`` event.

    The question is sent in the JSON body (not the URL) so it never appears in access logs.
    """
    generator = _require_generator(request)
    started = time.perf_counter()
    prepared = _retrieve(request, payload, user["username"])
    model_fields = _model_fields(generator)

    async def events() -> AsyncIterator[str]:
        if prepared is None:
            record_usage(
                request, user["username"], "qa", "no_evidence", retriever=payload.retriever
            )
            yield _event("refusal", {**refusal_payload(payload.query), **model_fields})
            return
        fragments: list[str] = []
        try:
            async for token in generator.stream(prepared.prompt):
                fragments.append(token)
                yield _event("token", {"token": token})
        except GenerationError as error:
            record_usage(request, user["username"], "qa", error.kind, retriever=payload.retriever)
            yield _event("error", {"detail": str(error), "kind": error.kind})
            return
        result = finalize_answer(prepared, "".join(fragments))
        record_usage(
            request,
            user["username"],
            "qa",
            result["refusal_reason"] or "ok",
            retriever=payload.retriever,
            result_count=len(result["citations"]),
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        yield _event("complete", {**result, **model_fields})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
