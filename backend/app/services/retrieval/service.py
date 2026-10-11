from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.ingestion.chunker import LegalChunk


def load_chunks(path: str | Path = "data/processed/chunks.jsonl") -> list[LegalChunk]:
    chunk_path = Path(path)
    if not chunk_path.is_file():
        return []
    chunks: list[LegalChunk] = []
    # Chunks of one document carry identical metadata; share one dict to save memory.
    shared_metadata: dict[str, dict[str, object]] = {}
    with chunk_path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            try:
                doc_id = str(record["doc_id"])
                metadata = record.get("metadata") or {}
                cached = shared_metadata.get(doc_id)
                if cached == metadata:
                    metadata = cached
                else:
                    shared_metadata[doc_id] = metadata
                chunks.append(
                    LegalChunk(
                        doc_id=doc_id,
                        chunk_id=str(record["chunk_id"]),
                        text=str(record["text"]),
                        start_char=int(record["start_char"]),
                        end_char=int(record["end_char"]),
                        token_count=int(record["token_count"]),
                        metadata=metadata,
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid chunk record at {chunk_path}:{line_number}") from error
    return chunks
