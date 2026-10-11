"""Grounded question answering: retrieve → select passages → generate → audit citations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.services.explain.confidence import confidence_score
from backend.app.services.generation.citation_checker import audit_citations, normalize_citations
from backend.app.services.generation.prompts import (
    DISCLAIMER,
    INSUFFICIENT_EVIDENCE,
    PromptPassage,
    build_prompt,
)
from backend.app.services.retrieval.base import Hit
from backend.app.services.retrieval.search import best_excerpt, hit_title

MAX_PASSAGES = 5
MAX_PASSAGES_PER_DOCUMENT = 2

NO_EVIDENCE = "The available corpus contains no passages relevant to this question."
WITHHELD_INVALID = (
    "The generated answer referred to a passage that was not provided, so it has been "
    "withheld. Review the retrieved passages directly."
)
WITHHELD_UNCITED = (
    "The generated answer did not cite any retrieved passage, so it has been withheld. "
    "Review the retrieved passages directly."
)


@dataclass
class PreparedQuestion:
    query: str
    hits: list[Hit]
    passages: list[Hit] = field(default_factory=list)
    prompt: str = ""


def select_passages(hits: list[Hit]) -> list[Hit]:
    """Keep the top passages while limiting how many come from a single document."""
    selected: list[Hit] = []
    per_document: dict[str, int] = {}
    for hit in hits:
        if per_document.get(hit.doc_id, 0) >= MAX_PASSAGES_PER_DOCUMENT:
            continue
        per_document[hit.doc_id] = per_document.get(hit.doc_id, 0) + 1
        selected.append(hit)
        if len(selected) == MAX_PASSAGES:
            break
    return selected


def prepare_question(
    query: str, hits: list[Hit], query_type: str, passage_chars: int = 1200
) -> PreparedQuestion:
    """Build the prompt from query-focused windows of each selected passage.

    Windows keep prompts small enough for local models; the full passage is still
    returned to the user so every citation can be checked against its source.
    """
    passages = select_passages(hits)
    prompt = build_prompt(
        query,
        [
            PromptPassage(best_excerpt(hit.text, query, passage_chars), hit_title(hit), hit.doc_id)
            for hit in passages
        ],
        query_type,
    )
    return PreparedQuestion(query=query, hits=hits, passages=passages, prompt=prompt)


def passage_payload(passages: list[Hit]) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "doc_id": hit.doc_id,
            "chunk_id": hit.chunk_id,
            "title": hit_title(hit),
            "text": hit.text,
            "score": hit.score,
            "source_scores": hit.source_scores,
            "metadata": dict(hit.metadata),
        }
        for index, hit in enumerate(passages, start=1)
    ]


def refusal_payload(query: str) -> dict[str, Any]:
    return {
        "query": query,
        "answer": NO_EVIDENCE,
        "citations": [],
        "invalid_citations": [],
        "unsupported_sentences": [],
        "interpretation": None,
        "passages": [],
        "confidence": 0.0,
        "disclaimer": DISCLAIMER,
        "refused": True,
        "refusal_reason": "no_evidence",
    }


def is_insufficient_evidence(answer: str) -> bool:
    # Models often drop the final period or change case; compare the bare sentence.
    expected = INSUFFICIENT_EVIDENCE.rstrip(".").casefold()
    return answer.strip().strip("*\"'").casefold().startswith(expected)


def finalize_answer(prepared: PreparedQuestion, answer_text: str) -> dict[str, Any]:
    passages = prepared.passages
    answer_text = normalize_citations(answer_text.strip())
    audit = audit_citations(answer_text, len(passages))
    citations = list(dict.fromkeys(audit.valid_citations))
    refusal_reason: str | None = None
    answer = answer_text
    if is_insufficient_evidence(answer_text):
        refusal_reason = "insufficient_evidence"
        answer = INSUFFICIENT_EVIDENCE
    elif audit.invalid_citations:
        refusal_reason = "invalid_citations"
        answer = WITHHELD_INVALID
    elif not citations:
        refusal_reason = "uncited_answer"
        answer = WITHHELD_UNCITED
    withheld = refusal_reason in {"invalid_citations", "uncited_answer"}
    return {
        "query": prepared.query,
        "answer": answer,
        "citations": [] if withheld else citations,
        "invalid_citations": list(audit.invalid_citations),
        "unsupported_sentences": [] if refusal_reason else list(audit.unsupported_sentences),
        "interpretation": None if refusal_reason else audit.interpretation,
        "passages": passage_payload(passages),
        "confidence": 0.0 if refusal_reason else confidence_score(prepared.hits, citations),
        "disclaimer": DISCLAIMER,
        "refused": refusal_reason is not None,
        "refusal_reason": refusal_reason,
    }
