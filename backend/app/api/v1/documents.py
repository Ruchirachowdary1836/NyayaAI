"""Read-only access to the indexed legal corpus (judgments and statutes)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.api.deps import CurrentUser
from backend.app.schemas.library import CorpusDocumentList
from backend.app.services.retrieval.corpus import CorpusStore

router = APIRouter(prefix="/documents", tags=["corpus documents"])


def _store(request: Request) -> CorpusStore:
    return request.app.state.corpus


@router.get("", response_model=CorpusDocumentList)
def list_documents(
    request: Request,
    _: CurrentUser,
    q: Annotated[str | None, Query(max_length=200)] = None,
    document_type: Annotated[str | None, Query(max_length=40)] = None,
    court: Annotated[str | None, Query(max_length=120)] = None,
    sort: Literal["id", "title"] = "id",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CorpusDocumentList:
    store = _store(request)
    documents, total = store.list(
        query=q, document_type=document_type, court=court, sort=sort, limit=limit, offset=offset
    )
    return CorpusDocumentList(
        documents=documents, total=total, limit=limit, offset=offset, facets=store.facets()
    )


@router.get("/{document_id}")
def get_document(document_id: str, request: Request, _: CurrentUser) -> dict[str, object]:
    if len(document_id) > 120:
        raise HTTPException(status_code=404, detail="Document not found")
    record = _store(request).read(document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = [asdict(chunk) for chunk in request.app.state.retrievers.chunks_for(document_id)]
    for chunk in chunks:
        chunk.pop("metadata", None)  # Identical to the document metadata.
    return {"document": record, "chunks": chunks}
