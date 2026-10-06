from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".csv", ".json", ".jsonl"}
_TEXT_FIELDS = (
    "judgment_text",
    "document_text",
    "full_text",
    "content",
    "text",
    "judgment",
    "body",
)
_ID_FIELDS = ("doc_id", "document_id", "judgment_id", "case_id", "id")


@dataclass(frozen=True)
class LegalDocument:
    doc_id: str
    text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LegalQuery:
    query_id: str
    text: str
    query_type: str | None = None


@dataclass(frozen=True)
class LegalQAExample:
    example_id: str
    question: str
    answer: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AILADataset:
    documents: tuple[LegalDocument, ...]
    queries: tuple[LegalQuery, ...]
    qrels: dict[str, dict[str, int]]


def _records_from_json(value: Any, path: Path) -> list[dict[str, Any]]:
    if isinstance(value, list):
        records = value
    elif isinstance(value, dict):
        for key in ("records", "documents", "cases", "judgments", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                records = nested
                break
        else:
            records = [value]
    else:
        raise TypeError(f"Expected a JSON object or array in {path}")

    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"Expected every JSON record to be an object in {path}")
    return records


def read_records(path: str | Path) -> list[dict[str, Any]]:
    """Read one JSON, JSONL, or CSV file, or all supported files in a directory."""
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {source_path}")

    paths = (
        sorted(file for file in source_path.iterdir() if file.suffix.lower() in SUPPORTED_SUFFIXES)
        if source_path.is_dir()
        else [source_path]
    )
    if not paths:
        raise ValueError(f"No JSON, JSONL, or CSV files found at {source_path}")

    records: list[dict[str, Any]] = []
    for file_path in paths:
        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported dataset format: {file_path}")
        if suffix == ".csv":
            with file_path.open(encoding="utf-8-sig", newline="") as file:
                records.extend(dict(row) for row in csv.DictReader(file))
        elif suffix == ".jsonl":
            with file_path.open(encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise ValueError(
                            f"Invalid JSONL at {file_path}:{line_number}: {error}"
                        ) from error
                    if not isinstance(record, dict):
                        raise TypeError(f"Expected a JSON object at {file_path}:{line_number}")
                    records.append(record)
        else:
            with file_path.open(encoding="utf-8") as file:
                records.extend(_records_from_json(json.load(file), file_path))
    return records


def _first_value(record: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None and str(value).strip():
            return value
    return None


def load_documents(path: str | Path, source: str) -> list[LegalDocument]:
    documents: list[LegalDocument] = []
    for index, record in enumerate(read_records(path), start=1):
        document_id = _first_value(record, _ID_FIELDS)
        text = _first_value(record, _TEXT_FIELDS)
        if document_id is None or text is None:
            raise ValueError(
                f"Document record {index} in {path} must contain an ID "
                f"({_ID_FIELDS}) and text ({_TEXT_FIELDS})"
            )
        metadata = {
            key: value for key, value in record.items() if key not in {*_ID_FIELDS, *_TEXT_FIELDS}
        }
        documents.append(
            LegalDocument(
                doc_id=str(document_id).strip(),
                text=str(text),
                source=source,
                metadata=metadata,
            )
        )
    return documents


def load_queries(path: str | Path) -> list[LegalQuery]:
    queries: list[LegalQuery] = []
    for index, record in enumerate(read_records(path), start=1):
        query_id = _first_value(record, ("query_id", "topic_id", "id"))
        text = _first_value(record, ("query", "question", "text", "title"))
        if query_id is None or text is None:
            raise ValueError(f"Query record {index} in {path} must contain an ID and query text")
        query_type = _first_value(record, ("query_type", "type"))
        queries.append(
            LegalQuery(
                query_id=str(query_id).strip(),
                text=str(text).strip(),
                query_type=str(query_type).strip() if query_type is not None else None,
            )
        )
    return queries


def load_qrels(path: str | Path) -> dict[str, dict[str, int]]:
    records = read_records(path)
    qrels: dict[str, dict[str, int]] = {}
    for index, record in enumerate(records, start=1):
        query_id = _first_value(record, ("query_id", "topic_id", "qid"))
        document_id = _first_value(record, ("doc_id", "document_id", "judgment_id", "docno"))
        relevance = _first_value(record, ("relevance", "relevance_grade", "score", "label"))
        if query_id is None or document_id is None or relevance is None:
            raise ValueError(
                f"Qrel record {index} in {path} must contain query, document, and relevance"
            )
        qrels.setdefault(str(query_id).strip(), {})[str(document_id).strip()] = int(relevance)
    return qrels


def load_aila(
    corpus_path: str | Path,
    queries_path: str | Path | None = None,
    qrels_path: str | Path | None = None,
) -> AILADataset:
    documents = load_documents(corpus_path, source="aila")
    queries = load_queries(queries_path) if queries_path is not None else []
    qrels = load_qrels(qrels_path) if qrels_path is not None else {}
    return AILADataset(tuple(documents), tuple(queries), qrels)


def load_ildc(path: str | Path) -> list[LegalDocument]:
    return load_documents(path, source="ildc")


def load_legal_qa(path: str | Path) -> list[LegalQAExample]:
    examples: list[LegalQAExample] = []
    for index, record in enumerate(read_records(path), start=1):
        question = _first_value(record, ("question", "query", "prompt"))
        answer = _first_value(record, ("answer", "reference_answer", "response"))
        example_id = _first_value(record, ("example_id", "question_id", "id"))
        if question is None or answer is None:
            raise ValueError(f"QA record {index} in {path} must contain question and answer")
        metadata = {
            key: value
            for key, value in record.items()
            if key not in {"question", "query", "prompt", "answer", "reference_answer", "response"}
        }
        examples.append(
            LegalQAExample(
                example_id=str(example_id if example_id is not None else index),
                question=str(question).strip(),
                answer=str(answer).strip(),
                metadata=metadata,
            )
        )
    return examples
