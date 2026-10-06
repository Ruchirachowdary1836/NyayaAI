from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.ingestion.loaders import LegalDocument


def corpus_statistics(documents: list[LegalDocument], chunks: list[LegalChunk]) -> dict[str, Any]:
    courts = Counter(
        str(document.metadata["court"])
        for document in documents
        if document.metadata.get("court") not in (None, "")
    )
    years = Counter(
        str(document.metadata["year"])
        for document in documents
        if document.metadata.get("year") not in (None, "")
    )
    return {
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "unique_source_count": len({document.source for document in documents}),
        "total_characters": sum(len(document.text) for document in documents),
        "total_chunk_tokens": sum(chunk.token_count for chunk in chunks),
        "average_chunk_tokens": (
            sum(chunk.token_count for chunk in chunks) / len(chunks) if chunks else 0.0
        ),
        "documents_by_source": dict(sorted(Counter(doc.source for doc in documents).items())),
        "documents_by_court": dict(sorted(courts.items())),
        "documents_by_year": dict(sorted(years.items())),
    }
