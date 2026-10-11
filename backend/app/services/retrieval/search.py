"""Search orchestration shared by the search, compare, QA, and experiment endpoints."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

from backend.app.services.retrieval.base import Hit, legal_tokenize
from backend.app.services.retrieval.corpus import document_title
from backend.app.services.retrieval.registry import RetrieverRegistry

CANDIDATE_POOL = 100
MAX_CANDIDATE_POOL = 6400
_EXCERPT_CHARS = 360


@dataclass(frozen=True)
class SearchFilters:
    document_type: str | None = None
    court: str | None = None
    year_from: int | None = None
    year_to: int | None = None

    def matches(self, hit: Hit) -> bool:
        metadata = hit.metadata
        if self.document_type and metadata.get("document_type") != self.document_type:
            return False
        if self.court and metadata.get("court") != self.court:
            return False
        if self.year_from is not None or self.year_to is not None:
            year = metadata.get("year")
            if not isinstance(year, int):
                return False
            if self.year_from is not None and year < self.year_from:
                return False
            if self.year_to is not None and year > self.year_to:
                return False
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "court": self.court,
            "year_from": self.year_from,
            "year_to": self.year_to,
        }


@dataclass
class SearchPage:
    hits: list[Hit]
    total: int
    total_is_capped: bool
    latency_ms: float
    filters: dict[str, Any] = field(default_factory=dict)


def best_excerpt(text: str, query: str, width: int = _EXCERPT_CHARS) -> str:
    """Return the window of ``text`` containing the most query terms."""
    if len(text) <= width:
        return text
    terms = {term for term in legal_tokenize(query) if len(term) > 2}
    lowered = text.casefold()
    positions = sorted(position for term in terms for position in _find_all(lowered, term))
    if not positions:
        return text[:width].rstrip() + "…"
    best_start, best_count = positions[0], 0
    right = 0
    for left, start in enumerate(positions):
        while right < len(positions) and positions[right] < start + width:
            right += 1
        if right - left > best_count:
            best_start, best_count = start, right - left
    start = max(0, best_start - width // 6)
    # Align the excerpt to a word boundary.
    if start > 0:
        space = text.rfind(" ", 0, start)
        start = space + 1 if space != -1 and start - space < 40 else start
    end = min(len(text), start + width)
    excerpt = text[start:end].strip()
    return ("…" if start > 0 else "") + excerpt + ("…" if end < len(text) else "")


def _find_all(text: str, term: str, limit: int = 50) -> list[int]:
    positions: list[int] = []
    start = text.find(term)
    while start != -1 and len(positions) < limit:
        positions.append(start)
        start = text.find(term, start + 1)
    return positions


def hit_title(hit: Hit) -> str:
    return document_title(hit.doc_id, dict(hit.metadata))


def rerank_page(
    hits: list[Hit],
    filters: SearchFilters,
    group_by_document: bool,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[Hit], int]:
    candidates = [hit for hit in hits if filters.matches(hit)]
    if group_by_document:
        seen: set[str] = set()
        unique: list[Hit] = []
        for hit in candidates:
            if hit.doc_id not in seen:
                seen.add(hit.doc_id)
                unique.append(hit)
        candidates = unique
    if sort == "title":
        candidates = sorted(candidates, key=lambda hit: (hit_title(hit).casefold(), hit.rank))
    elif sort == "document":
        candidates = sorted(candidates, key=lambda hit: (hit.doc_id, hit.rank))
    elif sort in {"newest", "oldest"}:
        # Undated sources (e.g. statutes) keep relevance order after the dated ones.
        dated = [hit for hit in candidates if hit.metadata.get("judgment_date")]
        undated = [hit for hit in candidates if not hit.metadata.get("judgment_date")]
        dated.sort(key=lambda hit: str(hit.metadata["judgment_date"]), reverse=sort == "newest")
        candidates = dated + undated
    start = (page - 1) * page_size
    return candidates[start : start + page_size], len(candidates)


def run_search(
    registry: RetrieverRegistry,
    retriever: str,
    query: str,
    filters: SearchFilters | None = None,
    group_by_document: bool = True,
    sort: str = "relevance",
    page: int = 1,
    page_size: int = 10,
) -> SearchPage:
    filters = filters or SearchFilters()
    engine = registry.get(retriever)
    needed = page * page_size
    pool_size = max(CANDIDATE_POOL, needed)
    started = time.perf_counter()
    hits = engine.search(query, pool_size)
    page_hits, total = rerank_page(hits, filters, group_by_document, sort, page, page_size)
    # Filters and per-document grouping shrink the candidate pool; widen it until the
    # requested page is filled or the corpus is exhausted, instead of returning a
    # misleadingly short page.
    while total < needed and len(hits) >= pool_size and pool_size < MAX_CANDIDATE_POOL:
        pool_size = min(pool_size * 4, MAX_CANDIDATE_POOL)
        hits = engine.search(query, pool_size)
        page_hits, total = rerank_page(hits, filters, group_by_document, sort, page, page_size)
    latency_ms = (time.perf_counter() - started) * 1000
    return SearchPage(
        hits=page_hits,
        total=total,
        total_is_capped=len(hits) >= pool_size,
        latency_ms=round(latency_ms, 2),
        filters=filters.as_dict(),
    )


def timed_document_search(registry: RetrieverRegistry, retriever: str, query: str, k: int):
    """Top ``k`` documents (best passage each), re-ranked 1..k, plus engine latency."""
    started = time.perf_counter()
    hits = registry.get(retriever).search(query, k * 4)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    seen: set[str] = set()
    documents: list[Hit] = []
    for hit in hits:
        if hit.doc_id not in seen:
            seen.add(hit.doc_id)
            documents.append(replace(hit, rank=len(documents) + 1))
            if len(documents) == k:
                break
    return documents, latency_ms
