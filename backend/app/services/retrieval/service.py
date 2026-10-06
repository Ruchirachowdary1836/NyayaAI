from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.registry import RetrieverRegistry


def load_chunks(path: str | Path = "data/processed/chunks.jsonl") -> list[LegalChunk]:
    chunk_path = Path(path)
    if not chunk_path.is_file():
        return []
    chunks: list[LegalChunk] = []
    with chunk_path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            try:
                chunks.append(
                    LegalChunk(
                        doc_id=str(record["doc_id"]),
                        chunk_id=str(record["chunk_id"]),
                        text=str(record["text"]),
                        start_char=int(record["start_char"]),
                        end_char=int(record["end_char"]),
                        token_count=int(record["token_count"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid chunk record at {chunk_path}:{line_number}") from error
    return chunks


def load_document(path: str | Path, document_id: str) -> dict[str, object] | None:
    documents_path = Path(path)
    if not documents_path.is_file():
        return None
    with documents_path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("doc_id") == document_id:
                chunks = []
                chunk_path = documents_path.parent / "chunks.jsonl"
                if chunk_path.is_file():
                    with chunk_path.open(encoding="utf-8") as chunk_file:
                        for chunk_line in chunk_file:
                            chunk = json.loads(chunk_line)
                            if chunk.get("doc_id") == document_id:
                                chunks.append(chunk)
                return {"document": record, "chunks": chunks}
    return None


def build_registry() -> RetrieverRegistry:
    chunks = load_chunks()
    return RetrieverRegistry(
        chunks,
        embedding_model="BAAI/bge-m3",
        alpha=0.7,
        fusion_method="rrf",
        rrf_k=60,
    )
