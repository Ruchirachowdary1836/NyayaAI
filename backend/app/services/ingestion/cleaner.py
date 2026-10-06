from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import replace

from backend.app.services.ingestion.loaders import LegalDocument

_PAGE_NUMBER = re.compile(r"^\s*(?:(?:page\s+)?\d+|[-–—]\s*\d+\s*[-–—])\s*$", re.IGNORECASE)
_WHITESPACE = re.compile(r"[ \t]+")
_TOO_MANY_NEWLINES = re.compile(r"\n{3,}")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def clean_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(?<=\w)-\n(?=\w)", "", normalized)
    lines = [_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")]
    lines = [line for line in lines if line and not _PAGE_NUMBER.fullmatch(line)]
    counts = Counter(line.casefold() for line in lines)
    filtered = [line for line in lines if not (len(line) <= 120 and counts[line.casefold()] >= 3)]
    return _TOO_MANY_NEWLINES.sub("\n\n", "\n".join(filtered)).strip()


def clean_document(document: LegalDocument) -> LegalDocument:
    return replace(document, text=clean_text(document.text))


def _simhash(text: str) -> int:
    words = _NON_WORD.sub(" ", text.casefold()).split()
    shingles = [" ".join(words[index : index + 3]) for index in range(max(1, len(words) - 2))]
    if not shingles:
        shingles = words or [text.casefold()]
    weights = [0] * 64
    for shingle in shingles:
        digest = int.from_bytes(
            hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big"
        )
        for bit in range(64):
            weights[bit] += 1 if digest & (1 << bit) else -1
    return sum(1 << bit for bit, weight in enumerate(weights) if weight > 0)


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def deduplicate_documents(
    documents: list[LegalDocument], similarity_threshold: float = 0.96
) -> list[LegalDocument]:
    """Remove exact and near-duplicate texts, retaining the first occurrence."""
    if not 0 < similarity_threshold <= 1:
        raise ValueError("similarity_threshold must be in (0, 1]")

    seen_hashes: set[str] = set()
    band_index: dict[tuple[int, int], list[int]] = {}
    retained: list[LegalDocument] = []
    fingerprints: list[int] = []

    for document in documents:
        normalized = _NON_WORD.sub(" ", document.text.casefold()).split()
        canonical = " ".join(normalized)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)

        fingerprint = _simhash(document.text)
        candidates: set[int] = set()
        for band in range(4):
            key = (band, (fingerprint >> (band * 16)) & 0xFFFF)
            candidates.update(band_index.get(key, []))
        max_distance = int((1 - similarity_threshold) * 64)
        if any(
            _hamming_distance(fingerprint, fingerprints[index]) <= max_distance
            for index in candidates
        ):
            continue

        new_index = len(retained)
        retained.append(document)
        fingerprints.append(fingerprint)
        for band in range(4):
            key = (band, (fingerprint >> (band * 16)) & 0xFFFF)
            band_index.setdefault(key, []).append(new_index)
    return retained
