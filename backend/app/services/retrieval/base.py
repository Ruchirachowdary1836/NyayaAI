from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

_TOKEN = re.compile(
    r"article\s+\d+[a-z]?|section\s+\d+[a-z]?|ipc\s+\d+[a-z]?|crpc\s+\d+[a-z]?|\d+[a-z]?|[^\W\d_]+",
    re.IGNORECASE,
)


def legal_tokenize(text: str) -> list[str]:
    """Tokenize while keeping common Indian legal references and provision numbers intact."""
    return [token.casefold() for token in _TOKEN.findall(text)]


@dataclass(frozen=True)
class Hit:
    doc_id: str
    chunk_id: str
    text: str
    score: float
    rank: int
    source_scores: dict[str, float | int | None] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


class Retriever(Protocol):
    name: str

    def search(self, query: str, k: int = 10) -> list[Hit]: ...
