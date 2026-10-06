from __future__ import annotations

import json

from backend.app.services.retrieval.service import load_document
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents(request: Request, limit: int = 50, offset: int = 0) -> dict[str, object]:
    documents_path = request.app.state.documents_path
    if not documents_path.is_file():
        return {"documents": [], "total": 0}
    documents = []
    with documents_path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            record = json.loads(line)
            text = str(record.get("text", ""))
            documents.append(
                {
                    "doc_id": record.get("doc_id"),
                    "source": record.get("source"),
                    "metadata": record.get("metadata", {}),
                    "excerpt": text[:280] + ("…" if len(text) > 280 else ""),
                }
            )
    return {"documents": documents[offset : offset + min(limit, 100)], "total": len(documents)}


@router.get("/{document_id}")
def get_document(document_id: str, request: Request) -> dict[str, object]:
    result = load_document(request.app.state.documents_path, document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result
