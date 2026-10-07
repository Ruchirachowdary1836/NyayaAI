from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

from backend.app.services.ingestion.loaders import LegalDocument

_TOKEN = re.compile(r"\S+")


@dataclass(frozen=True)
class LegalChunk:
    doc_id: str
    chunk_id: str
    text: str
    start_char: int
    end_char: int
    token_count: int
    metadata: dict[str, object] = field(default_factory=dict)


def chunk_document(
    document: LegalDocument, chunk_size: int = 512, overlap: float = 0.15
) -> list[LegalChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if not 0 <= overlap < 1:
        raise ValueError("overlap must be in [0, 1)")

    tokens = list(_TOKEN.finditer(document.text))
    if not tokens:
        return []

    overlap_tokens = min(chunk_size - 1, int(chunk_size * overlap))
    paragraph_ends = sorted(
        {
            index + 1
            for index in range(len(tokens) - 1)
            if "\n\n" in document.text[tokens[index].end() : tokens[index + 1].start()]
        }
    )
    chunks: list[LegalChunk] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        minimum_end = start + max(1, int((end - start) * 0.6))
        paragraph_index = bisect_right(paragraph_ends, end) - 1
        if paragraph_index >= 0 and paragraph_ends[paragraph_index] >= minimum_end:
            end = paragraph_ends[paragraph_index]
        chunks.append(
            LegalChunk(
                doc_id=document.doc_id,
                chunk_id=f"{document.doc_id}:{len(chunks)}",
                text=document.text[tokens[start].start() : tokens[end - 1].end()],
                start_char=tokens[start].start(),
                end_char=tokens[end - 1].end(),
                token_count=end - start,
                metadata=document.metadata,
            )
        )
        if end == len(tokens):
            break
        start = max(start + 1, end - overlap_tokens)
    return chunks


def chunk_documents(
    documents: list[LegalDocument], chunk_size: int = 512, overlap: float = 0.15
) -> list[LegalChunk]:
    return [
        chunk
        for document in documents
        for chunk in chunk_document(document, chunk_size=chunk_size, overlap=overlap)
    ]
