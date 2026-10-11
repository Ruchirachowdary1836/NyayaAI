"""Private document library: each user can only see and manage their own uploads."""

from __future__ import annotations

import logging
import uuid
from pathlib import PurePath
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile

from backend.app.api.deps import DB, CurrentUser, record_usage
from backend.app.core.config import settings
from backend.app.core.rate_limit import upload_limiter
from backend.app.db.database import DuplicateRecordError
from backend.app.schemas.library import (
    LibrarySearchHit,
    LibrarySearchResponse,
    UserDocumentDetail,
    UserDocumentList,
    UserDocumentSummary,
)
from backend.app.schemas.retrieval import QueryModel
from backend.app.services.library import (
    UploadRejected,
    extract_text,
    library_search_cache,
    safe_filename,
    sha256_hex,
    validate_upload,
)

router = APIRouter(prefix="/library", tags=["document library"])
logger = logging.getLogger("nyayaai.library")
_UPLOADS_PER_MINUTE = 20


def _not_found() -> HTTPException:
    # The same response is returned for missing documents and other users' documents.
    return HTTPException(status_code=404, detail="Document not found")


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"The file exceeds the {max_bytes // (1024 * 1024)} MB upload limit.",
        )
    return content


@router.post("/documents", response_model=UserDocumentSummary, status_code=201)
async def upload_document(
    request: Request,
    user: CurrentUser,
    database: DB,
    file: Annotated[UploadFile, File(description="PDF, TXT, or Markdown file")],
    title: Annotated[str | None, Form(max_length=200)] = None,
) -> UserDocumentSummary:
    owner = user["username"]
    if not upload_limiter.allow(f"upload:{owner}", _UPLOADS_PER_MINUTE):
        raise HTTPException(status_code=429, detail="Upload rate limit reached. Try again later.")
    counts = database.count_user_documents(owner)
    if sum(counts.values()) >= settings.upload_max_documents_per_user:
        raise HTTPException(
            status_code=409,
            detail=f"Library limit of {settings.upload_max_documents_per_user} documents reached.",
        )
    filename = safe_filename(file.filename)
    content = await _read_limited(file, settings.upload_max_bytes)
    try:
        extension, content_type = validate_upload(filename, content, settings.upload_max_bytes)
    except UploadRejected as error:
        record_usage(request, owner, "upload", "rejected")
        raise HTTPException(status_code=422, detail=str(error)) from error

    digest = sha256_hex(content)
    existing = database.find_user_document_by_hash(owner, digest)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This file is already in your library (document {existing}).",
        )
    extraction = extract_text(extension, content)
    document_id = str(uuid.uuid4())
    clean_title = (title or "").strip() or PurePath(filename).stem or "Untitled document"
    try:
        database.insert_user_document(
            {
                "document_id": document_id,
                "owner": owner,
                "title": clean_title[:200],
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(content),
                "sha256": digest,
                "status": extraction.status,
                "error": extraction.error,
                "text": extraction.text,
                "page_count": extraction.page_count,
                "char_count": len(extraction.text or ""),
                "content": content,
            }
        )
    except DuplicateRecordError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    library_search_cache.invalidate(owner)
    record_usage(request, owner, "upload", extraction.status)
    logger.info("document_uploaded status=%s bytes=%d", extraction.status, len(content))
    document = database.get_user_document(owner, document_id)
    if document is None:
        raise HTTPException(status_code=500, detail="Uploaded document could not be saved")
    return UserDocumentSummary(**document)


@router.get("/documents", response_model=UserDocumentList)
def list_documents(
    user: CurrentUser,
    database: DB,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: Literal["processing", "ready", "failed"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserDocumentList:
    documents, total = database.list_user_documents(
        user["username"], limit=limit, offset=offset, query=q, status=status
    )
    return UserDocumentList(
        documents=[UserDocumentSummary(**document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{document_id}", response_model=UserDocumentDetail)
def get_document(document_id: str, user: CurrentUser, database: DB) -> UserDocumentDetail:
    document = database.get_user_document(user["username"], document_id)
    if document is None:
        raise _not_found()
    return UserDocumentDetail(**document)


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, user: CurrentUser, database: DB) -> Response:
    document = database.get_user_document(user["username"], document_id, include_content=True)
    if document is None:
        raise _not_found()
    filename = document["filename"]
    ascii_name = filename.encode("ascii", "ignore").decode() or "document"
    return Response(
        content=document["content"],
        media_type=document["content_type"],
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: str, request: Request, user: CurrentUser, database: DB
) -> Response:
    if not database.delete_user_document(user["username"], document_id):
        raise _not_found()
    library_search_cache.invalidate(user["username"])
    record_usage(request, user["username"], "delete_document", "ok")
    return Response(status_code=204)


class LibrarySearchRequest(QueryModel):
    k: int = 10


@router.post("/search", response_model=LibrarySearchResponse)
def search_library(
    payload: LibrarySearchRequest, user: CurrentUser, database: DB
) -> LibrarySearchResponse:
    k = max(1, min(payload.k, 50))
    documents = database.list_ready_document_texts(user["username"])
    hits = library_search_cache.search(user["username"], documents, payload.query, k)
    return LibrarySearchResponse(
        query=payload.query,
        hits=[LibrarySearchHit(**hit) for hit in hits],
        searched_documents=len(documents),
    )
