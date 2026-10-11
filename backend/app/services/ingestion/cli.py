from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from backend.app.services.ingestion.chunker import chunk_documents
from backend.app.services.ingestion.cleaner import clean_document, deduplicate_documents
from backend.app.services.ingestion.loaders import (
    LegalDocument,
    load_aila,
    load_ildc,
    load_legal_qa,
)
from backend.app.services.ingestion.metadata import enrich_document
from backend.app.services.ingestion.statistics import corpus_statistics

logger = logging.getLogger("nyayaai.ingestion")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")


def _drop_duplicate_ids(
    documents: list[LegalDocument],
) -> tuple[list[LegalDocument], list[str]]:
    """Keep the first record for each document ID so re-ingestion is deterministic."""
    seen: set[str] = set()
    retained: list[LegalDocument] = []
    duplicates: list[str] = []
    for document in documents:
        if document.doc_id in seen:
            duplicates.append(document.doc_id)
            continue
        seen.add(document.doc_id)
        retained.append(document)
    return retained, duplicates


def run_ingestion(config_path: str | Path) -> dict[str, Any]:
    with Path(config_path).open(encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    corpus_config = config.get("corpus", {})
    paths_config = config.get("paths", {})
    source = str(corpus_config.get("source", "aila")).lower()
    input_path = corpus_config.get("input_path")
    if not input_path:
        raise ValueError("corpus.input_path must be set in the data configuration")

    if source == "aila":
        dataset = load_aila(
            input_path,
            queries_path=corpus_config.get("queries_path"),
            qrels_path=corpus_config.get("qrels_path"),
        )
        documents = list(dataset.documents)
        output_dir = Path(paths_config.get("processed_dir", "data/processed"))
        if corpus_config.get("queries_path"):
            _write_jsonl(output_dir / "queries.jsonl", [asdict(query) for query in dataset.queries])
        if corpus_config.get("qrels_path"):
            _write_jsonl(
                output_dir / "qrels.jsonl",
                [
                    {"query_id": query_id, "doc_id": doc_id, "relevance": relevance}
                    for query_id, judgments in dataset.qrels.items()
                    for doc_id, relevance in judgments.items()
                ],
            )
    elif source == "ildc":
        documents = load_ildc(input_path)
        output_dir = Path(paths_config.get("processed_dir", "data/processed"))
    elif source in {"legal_qa", "qa"}:
        examples = load_legal_qa(input_path)
        output_dir = Path(paths_config.get("processed_dir", "data/processed"))
        _write_jsonl(output_dir / "legal_qa.jsonl", [asdict(example) for example in examples])
        summary = {"qa_example_count": len(examples), "processed_dir": str(output_dir)}
        print(json.dumps(summary, indent=2))
        return summary
    else:
        raise ValueError(f"Unsupported corpus source {source!r}; choose aila, ildc, or legal_qa")

    loaded_count = len(documents)
    logger.info("Loaded %d source documents from %s", loaded_count, input_path)
    documents, duplicate_ids = _drop_duplicate_ids(documents)
    documents = [enrich_document(clean_document(document)) for document in documents]
    empty_ids = [document.doc_id for document in documents if not document.text.strip()]
    documents = [document for document in documents if document.text.strip()]
    before_dedup = len(documents)
    if corpus_config.get("deduplicate_near_duplicates", True):
        documents = deduplicate_documents(documents)
    logger.info("Chunking %d documents", len(documents))
    chunks = chunk_documents(
        documents,
        chunk_size=int(corpus_config.get("chunk_size", 512)),
        overlap=float(corpus_config.get("overlap", 0.15)),
    )

    _write_jsonl(output_dir / "documents.jsonl", [asdict(document) for document in documents])
    _write_jsonl(output_dir / "chunks.jsonl", [asdict(chunk) for chunk in chunks])
    summary = corpus_statistics(documents, chunks)
    statistics_path = Path(
        paths_config.get("statistics_path", output_dir / "corpus_statistics.json")
    )
    statistics_path.parent.mkdir(parents=True, exist_ok=True)
    statistics_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report = {
        "completed_at": datetime.now(UTC).isoformat(),
        "config": str(config_path),
        "source": source,
        "input_records": loaded_count,
        "skipped_duplicate_ids": duplicate_ids,
        "skipped_empty_documents": empty_ids,
        "removed_duplicate_texts": before_dedup - len(documents),
        "documents_written": len(documents),
        "chunks_written": len(chunks),
        "documents_with_judgment_date": sum(
            1 for document in documents if document.metadata.get("judgment_date")
        ),
        "documents_with_case_number": sum(
            1 for document in documents if document.metadata.get("case_number")
        ),
    }
    (output_dir / "ingestion_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    summary["ingestion_report"] = report
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean and chunk a configured legal corpus.")
    parser.add_argument("--config", default="configs/data.yaml", help="Path to data YAML config")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_ingestion(args.config)


if __name__ == "__main__":
    main()
