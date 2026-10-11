from __future__ import annotations

import re
from dataclasses import dataclass

_CITATION = re.compile(r"\[(\d+)\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_INTERPRETATION = re.compile(r"(?im)^\s*\**interpretation:?\**:?\s*")
# Variants models commonly emit: [1, 2], [1,2], [Passage 1], [passages 1 and 3].
_GROUPED_CITATION = re.compile(
    r"\[(?:passages?\s+)?(\d+(?:\s*(?:,|and|&)\s*\d+)*)\]", re.IGNORECASE
)


def normalize_citations(answer: str) -> str:
    """Rewrite grouped or labelled passage markers into the canonical ``[n]`` form."""

    def expand(match: re.Match[str]) -> str:
        return "".join(f"[{number}]" for number in re.findall(r"\d+", match.group(1)))

    return _GROUPED_CITATION.sub(expand, answer)


@dataclass(frozen=True)
class CitationAudit:
    valid_citations: tuple[int, ...]
    invalid_citations: tuple[int, ...]
    unsupported_sentences: tuple[str, ...]
    interpretation: str | None = None

    @property
    def citation_precision(self) -> float:
        total = len(self.valid_citations) + len(self.invalid_citations)
        return len(self.valid_citations) / total if total else 0.0


def split_interpretation(answer: str) -> tuple[str, str | None]:
    """Separate the sourced answer from an optional trailing ``Interpretation:`` section."""
    match = _INTERPRETATION.search(answer)
    if match is None:
        return answer, None
    interpretation = answer[match.end() :].strip()
    return answer[: match.start()].strip(), interpretation or None


def audit_citations(answer: str, passage_count: int) -> CitationAudit:
    valid: list[int] = []
    invalid: list[int] = []
    for match in _CITATION.finditer(answer):
        index = int(match.group(1))
        (valid if 1 <= index <= passage_count else invalid).append(index)
    sourced, interpretation = split_interpretation(answer)
    sentences = [sentence.strip() for sentence in _SENTENCE.split(sourced) if sentence.strip()]
    unsupported = tuple(
        sentence
        for sentence in sentences
        if not _CITATION.search(sentence) and not sentence.startswith("[")
    )
    return CitationAudit(tuple(valid), tuple(invalid), unsupported, interpretation)
