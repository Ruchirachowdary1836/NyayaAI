"""Extract structured metadata that judgments state in their own header lines.

Only values literally present in the source text are recorded; nothing is inferred.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime

from backend.app.services.ingestion.loaders import LegalDocument

_DATE_LINE = re.compile(r"^(\d{1,2}) ([A-Z][a-z]+) (\d{4})$")
_CASE_NUMBER = re.compile(
    r"\b(nos?\.|no\(s\)\.|appeal|petition|s\.\s?l\.\s?p|writ|reference|\d+\s+of\s+\d{4}|\d+/\d{4})",
    re.IGNORECASE,
)
_HEADER_LINES = 8


def content_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def judgment_header_metadata(text: str) -> dict[str, object]:
    lines = [line.strip() for line in text.splitlines()[:_HEADER_LINES] if line.strip()]
    metadata: dict[str, object] = {}
    for index, line in enumerate(lines):
        match = _DATE_LINE.match(line)
        if not match:
            continue
        try:
            parsed = datetime.strptime(line, "%d %B %Y").date()
        except ValueError:
            continue
        metadata["judgment_date"] = parsed.isoformat()
        metadata["year"] = parsed.year
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if (
            following
            and len(following) <= 200
            and not following.lower().startswith("the judgment was delivered")
            and _CASE_NUMBER.search(following)
        ):
            metadata["case_number"] = following
        break
    return metadata


def enrich_document(document: LegalDocument) -> LegalDocument:
    metadata = dict(document.metadata)
    metadata["content_sha256"] = content_checksum(document.text)
    if metadata.get("document_type") == "judgment":
        for key, value in judgment_header_metadata(document.text).items():
            metadata.setdefault(key, value)
    return replace(document, metadata=metadata)
