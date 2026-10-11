"""User document library: upload validation, text extraction, and private search."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from backend.app.services.ingestion.chunker import LegalChunk, chunk_document
from backend.app.services.ingestion.loaders import LegalDocument
from backend.app.services.retrieval.bm25 import BM25Retriever
from backend.app.services.retrieval.search import best_excerpt

logger = logging.getLogger("nyayaai.library")

ALLOWED_EXTENSIONS = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}
MAX_EXTRACTED_CHARS = 2_000_000
MAX_PDF_PAGES = 1_000
# Signatures of binary formats that must never be accepted as text.
_BINARY_SIGNATURES = (
    b"%PDF-",
    b"PK\x03\x04",
    b"MZ",
    b"\x7fELF",
    b"\x89PNG",
    b"\xff\xd8\xff",
    b"GIF8",
)


_SPACES = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_upload_text(text: str) -> str:
    """Normalize whitespace and control characters without dropping any content lines."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(char for char in text if char in "\n\t" or unicodedata.category(char) != "Cc")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


class UploadRejected(ValueError):
    """The uploaded file failed validation; the message is safe to show to users."""


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    text: str | None
    page_count: int | None
    error: str | None


def safe_filename(filename: str | None) -> str:
    name = PurePath((filename or "").replace("\\", "/")).name
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]+", "_", name).strip(" .")
    return name[:200] or "document"


def validate_upload(filename: str, content: bytes, max_bytes: int) -> tuple[str, str]:
    """Validate extension, size, and actual content. Returns (extension, content_type)."""
    extension = PurePath(filename).suffix.casefold()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadRejected("Unsupported file type. Upload a PDF, TXT, or Markdown (.md) file.")
    if not content:
        raise UploadRejected("The uploaded file is empty.")
    if len(content) > max_bytes:
        raise UploadRejected(f"The file exceeds the {max_bytes // (1024 * 1024)} MB upload limit.")
    if extension == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise UploadRejected("The file has a .pdf extension but is not a valid PDF document.")
    else:
        if content.startswith(_BINARY_SIGNATURES) or b"\x00" in content:
            raise UploadRejected("The file is not plain text. Upload UTF-8 encoded text.")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise UploadRejected("Text files must be UTF-8 encoded.") from error
    return extension, ALLOWED_EXTENSIONS[extension]


def extract_text(extension: str, content: bytes) -> ExtractionResult:
    try:
        if extension == ".pdf":
            text, pages = _extract_pdf(content)
        else:
            text, pages = content.decode("utf-8-sig"), None
    except UploadRejected as error:
        return ExtractionResult("failed", None, None, str(error))
    except Exception:
        logger.exception("document_extraction_failed extension=%s", extension)
        return ExtractionResult("failed", None, None, "Text could not be extracted from this file.")
    text = normalize_upload_text(text)[:MAX_EXTRACTED_CHARS]
    if not text.strip():
        return ExtractionResult(
            "failed",
            None,
            pages,
            "No extractable text was found. Scanned PDFs need OCR before upload.",
        )
    return ExtractionResult("ready", text, pages, None)


def _extract_pdf(content: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(BytesIO(content))
    except PdfReadError as error:
        raise UploadRejected("The PDF is damaged or could not be read.") from error
    if reader.is_encrypted:
        raise UploadRejected("Encrypted PDFs are not supported. Remove the password and retry.")
    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise UploadRejected(f"PDFs are limited to {MAX_PDF_PAGES} pages.")
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
        if sum(len(item) for item in pages) > MAX_EXTRACTED_CHARS:
            break
    return "\n\n".join(pages), page_count


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class LibrarySearchCache:
    """Caches a BM25 index per user, rebuilt whenever their set of ready documents changes."""

    def __init__(self, max_users: int = 64) -> None:
        self._entries: dict[str, tuple[tuple[str, ...], BM25Retriever, dict[str, dict]]] = {}
        self._lock = threading.Lock()
        self._max_users = max_users

    def search(self, owner: str, documents: list[dict], query: str, k: int = 10) -> list[dict]:
        key = tuple(sorted(document["document_id"] for document in documents))
        with self._lock:
            cached = self._entries.get(owner)
        if cached is None or cached[0] != key:
            chunks: list[LegalChunk] = []
            for document in documents:
                chunks.extend(
                    chunk_document(
                        LegalDocument(document["document_id"], document["text"] or "", "upload"),
                        chunk_size=256,
                        overlap=0.15,
                    )
                )
            info = {document["document_id"]: document for document in documents}
            cached = (key, BM25Retriever(chunks), info)
            with self._lock:
                if len(self._entries) >= self._max_users and owner not in self._entries:
                    self._entries.pop(next(iter(self._entries)))
                self._entries[owner] = cached
        _, retriever, info = cached
        results = []
        seen: set[str] = set()
        for hit in retriever.search(query, k * 4):
            if hit.doc_id in seen:
                continue
            seen.add(hit.doc_id)
            document = info[hit.doc_id]
            results.append(
                {
                    "document_id": hit.doc_id,
                    "title": document["title"],
                    "filename": document["filename"],
                    "chunk_index": int(hit.chunk_id.rsplit(":", 1)[-1]),
                    "excerpt": best_excerpt(hit.text, query),
                    "score": hit.score,
                    "rank": len(results) + 1,
                }
            )
            if len(results) == k:
                break
        return results

    def invalidate(self, owner: str) -> None:
        with self._lock:
            self._entries.pop(owner, None)


library_search_cache = LibrarySearchCache()
