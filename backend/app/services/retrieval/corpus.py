"""Read-only access to the processed legal corpus (``documents.jsonl``).

The store keeps lightweight metadata in memory and remembers each record's byte
offset, so listing and filtering never re-read the full corpus and a document's
full text is loaded only when it is opened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_EXCERPT_CHARS = 280


@dataclass(frozen=True)
class CorpusEntry:
    doc_id: str
    source: str
    title: str
    document_type: str | None
    court: str | None
    excerpt: str
    char_count: int
    offset: int
    length: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source": self.source,
            "title": self.title,
            "document_type": self.document_type,
            "court": self.court,
            "excerpt": self.excerpt,
            "char_count": self.char_count,
            "metadata": self.metadata,
        }


def document_title(doc_id: str, metadata: dict[str, Any]) -> str:
    for key in ("title", "case_title", "citation", "case_name"):
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return doc_id


class CorpusStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries: dict[str, CorpusEntry] = {}
        self._order: list[str] = []
        if self.path.is_file():
            self._load()

    def _load(self) -> None:
        with self.path.open("rb") as file:
            offset = 0
            for raw_line in file:
                length = len(raw_line)
                if raw_line.strip():
                    record = json.loads(raw_line)
                    doc_id = str(record["doc_id"])
                    text = str(record.get("text", ""))
                    metadata = record.get("metadata") or {}
                    if doc_id not in self._entries:
                        excerpt = " ".join(text[: _EXCERPT_CHARS * 2].split())
                        if len(excerpt) > _EXCERPT_CHARS:
                            excerpt = excerpt[:_EXCERPT_CHARS].rstrip() + "…"
                        self._entries[doc_id] = CorpusEntry(
                            doc_id=doc_id,
                            source=str(record.get("source", "")),
                            title=document_title(doc_id, metadata),
                            document_type=_optional(metadata.get("document_type")),
                            court=_optional(metadata.get("court")),
                            excerpt=excerpt,
                            char_count=len(text),
                            offset=offset,
                            length=length,
                            metadata=metadata,
                        )
                        self._order.append(doc_id)
                offset += length

    def __len__(self) -> int:
        return len(self._order)

    def __contains__(self, doc_id: object) -> bool:
        return doc_id in self._entries

    def entry(self, doc_id: str) -> CorpusEntry | None:
        return self._entries.get(doc_id)

    def facets(self) -> dict[str, list[str]]:
        document_types = sorted(
            {entry.document_type for entry in self._entries.values() if entry.document_type}
        )
        courts = sorted({entry.court for entry in self._entries.values() if entry.court})
        return {"document_types": document_types, "courts": courts}

    def list(
        self,
        query: str | None = None,
        document_type: str | None = None,
        court: str | None = None,
        sort: str = "id",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        needle = query.casefold().strip() if query else ""
        matches = [
            entry
            for doc_id in self._order
            if (entry := self._entries[doc_id])
            and (not document_type or entry.document_type == document_type)
            and (not court or entry.court == court)
            and (
                not needle
                or needle in entry.doc_id.casefold()
                or needle in entry.title.casefold()
                or needle in entry.excerpt.casefold()
            )
        ]
        if sort == "title":
            matches.sort(key=lambda entry: (entry.title.casefold(), entry.doc_id))
        return [entry.summary() for entry in matches[offset : offset + limit]], len(matches)

    def read(self, doc_id: str) -> dict[str, Any] | None:
        entry = self._entries.get(doc_id)
        if entry is None:
            return None
        with self.path.open("rb") as file:
            file.seek(entry.offset)
            record = json.loads(file.read(entry.length))
        return record


def _optional(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
