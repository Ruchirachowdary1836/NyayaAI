from __future__ import annotations

import json
from collections.abc import AsyncIterator

from backend.app.schemas.retrieval import PassageResponse, QARequest, QAResponse
from backend.app.services.explain.confidence import confidence_score
from backend.app.services.generation.citation_checker import audit_citations
from backend.app.services.generation.llm import OllamaGenerator, OpenAICompatibleGenerator
from backend.app.services.generation.prompts import DISCLAIMER, build_prompt
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/qa", tags=["qa"])


def _prepare(request: Request, query: str, retriever_name: str, k: int):
    registry = request.app.state.retrievers
    try:
        hits = registry.get(retriever_name).search(query, k)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return hits


@router.post("", response_model=QAResponse)
async def answer(payload: QARequest, request: Request) -> QAResponse:
    hits = _prepare(request, payload.query, payload.retriever, payload.k)
    if not hits:
        refusal = "The available corpus contains no passages relevant to this question."
        return QAResponse(
            query=payload.query,
            answer=refusal,
            citations=[],
            invalid_citations=[],
            unsupported_sentences=[],
            passages=[],
            confidence=0.0,
            disclaimer=DISCLAIMER,
            refused=True,
        )

    generator = request.app.state.generator
    try:
        answer_text = await generator.generate(
            build_prompt(
                payload.query,
                [hit.text for hit in hits[:5]],
                payload.query_type,
            )
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    audit = audit_citations(answer_text, min(len(hits), 5))
    citations = list(dict.fromkeys(audit.valid_citations))
    passages = [
        PassageResponse(
            index=index,
            doc_id=hit.doc_id,
            chunk_id=hit.chunk_id,
            text=hit.text,
            score=hit.score,
            source_scores=hit.source_scores,
        )
        for index, hit in enumerate(hits[:5], start=1)
    ]
    invalid_reference = bool(audit.invalid_citations)
    return QAResponse(
        query=payload.query,
        answer=(
            "The generated answer contained a reference to a passage that was not provided. "
            "It has been withheld; review the retrieved passages directly."
            if invalid_reference
            else answer_text
        ),
        citations=citations,
        invalid_citations=list(audit.invalid_citations),
        unsupported_sentences=list(audit.unsupported_sentences),
        passages=passages,
        confidence=confidence_score(hits, citations),
        disclaimer=DISCLAIMER,
        refused=invalid_reference,
    )


@router.get("/stream")
async def stream_answer(
    request: Request,
    query: str = Query(min_length=1, max_length=4000),
    retriever: str = Query(default="bm25", pattern="^(bm25|dense|hybrid)$"),
    k: int = Query(default=10, ge=1, le=100),
    query_type: str = Query(
        default="auto", pattern="^(auto|statute_lookup|conceptual|fact_pattern)$"
    ),
) -> StreamingResponse:
    hits = _prepare(request, query, retriever, k)

    async def events() -> AsyncIterator[str]:
        if not hits:
            yield (
                "event: refusal\ndata: "
                + json.dumps(
                    {
                        "query": query,
                        "answer": "The available corpus contains no passages relevant to this question.",
                        "citations": [],
                        "invalid_citations": [],
                        "unsupported_sentences": [],
                        "passages": [],
                        "confidence": 0.0,
                        "disclaimer": DISCLAIMER,
                        "refused": True,
                    }
                )
                + "\n\n"
            )
            return
        generator: OllamaGenerator | OpenAICompatibleGenerator = request.app.state.generator
        try:
            prompt = build_prompt(query, [hit.text for hit in hits[:5]], query_type)
            fragments: list[str] = []
            async for token in generator.stream(prompt):
                fragments.append(token)
                yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
            complete = "".join(fragments)
            audit = audit_citations(complete, min(len(hits), 5))
            valid_citations = list(dict.fromkeys(audit.valid_citations))
            invalid_reference = bool(audit.invalid_citations)
            passages = [
                PassageResponse(
                    index=index,
                    doc_id=hit.doc_id,
                    chunk_id=hit.chunk_id,
                    text=hit.text,
                    score=hit.score,
                    source_scores=hit.source_scores,
                ).model_dump()
                for index, hit in enumerate(hits[:5], start=1)
            ]
            yield (
                "event: complete\ndata: "
                + json.dumps(
                    {
                        "query": query,
                        "answer": complete,
                        "citations": valid_citations,
                        "invalid_citations": list(audit.invalid_citations),
                        "unsupported_sentences": list(audit.unsupported_sentences),
                        "disclaimer": DISCLAIMER,
                        "passages": passages,
                        "confidence": confidence_score(hits, valid_citations),
                        "refused": invalid_reference,
                    }
                )
                + "\n\n"
            )
        except RuntimeError as error:
            yield f"event: error\ndata: {json.dumps({'detail': str(error)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
