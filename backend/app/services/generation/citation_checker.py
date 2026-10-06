from __future__ import annotations

import re
from dataclasses import dataclass

_CITATION = re.compile(r"\[(\d+)\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class CitationAudit:
    valid_citations: tuple[int, ...]
    invalid_citations: tuple[int, ...]
    unsupported_sentences: tuple[str, ...]

    @property
    def citation_precision(self) -> float:
        total = len(self.valid_citations) + len(self.invalid_citations)
        return len(self.valid_citations) / total if total else 0.0


def audit_citations(answer: str, passage_count: int) -> CitationAudit:
    valid: list[int] = []
    invalid: list[int] = []
    for match in _CITATION.finditer(answer):
        index = int(match.group(1))
        (valid if 1 <= index <= passage_count else invalid).append(index)
    sentences = [sentence.strip() for sentence in _SENTENCE.split(answer) if sentence.strip()]
    unsupported = tuple(
        sentence
        for sentence in sentences
        if not _CITATION.search(sentence) and not sentence.startswith("[")
    )
    return CitationAudit(tuple(valid), tuple(invalid), unsupported)
