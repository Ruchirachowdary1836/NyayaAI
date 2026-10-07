from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.app.services.ingestion.chunker import chunk_document, chunk_documents
from backend.app.services.ingestion.cleaner import clean_document, clean_text, deduplicate_documents
from backend.app.services.ingestion.cli import run_ingestion
from backend.app.services.ingestion.loaders import (
    LegalDocument,
    load_aila,
    load_ildc,
    load_legal_qa,
    read_records,
)
from backend.app.services.ingestion.statistics import corpus_statistics


def test_read_records_supports_json_jsonl_and_csv(tmp_path: Path) -> None:
    json_file = tmp_path / "records.json"
    json_file.write_text(json.dumps([{"id": "1"}, {"id": "2"}]), encoding="utf-8")
    jsonl_file = tmp_path / "records.jsonl"
    jsonl_file.write_text('{"id":"3"}\n\n{"id":"4"}\n', encoding="utf-8")
    csv_file = tmp_path / "records.csv"
    csv_file.write_text("id,text\n5,case\n", encoding="utf-8")

    assert [record["id"] for record in read_records(json_file)] == ["1", "2"]
    assert [record["id"] for record in read_records(jsonl_file)] == ["3", "4"]
    assert read_records(csv_file) == [{"id": "5", "text": "case"}]


def test_dataset_loaders_normalize_aila_ildc_and_legal_qa(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps([{"case_id": 17, "judgment_text": "A judgment", "year": 2020}]))
    queries = tmp_path / "queries.csv"
    queries.write_text("topic_id,title,type\nq1,Test query,conceptual\n")
    qrels = tmp_path / "qrels.csv"
    qrels.write_text("qid,docno,score\nq1,17,2\n")
    qa = tmp_path / "qa.jsonl"
    qa.write_text('{"question":"What?","answer":"A response"}\n')

    aila = load_aila(corpus, queries, qrels)
    assert aila.documents[0].doc_id == "17"
    assert aila.documents[0].source == "aila"
    assert aila.queries[0].query_type == "conceptual"
    assert aila.qrels == {"q1": {"17": 2}}
    assert load_ildc(corpus)[0].source == "ildc"
    assert load_legal_qa(qa)[0].question == "What?"


def test_loader_rejects_records_missing_required_fields(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text(json.dumps([{"id": "doc-1"}]), encoding="utf-8")

    with pytest.raises(ValueError, match="must contain an ID"):
        load_ildc(source)


def test_cleaning_normalizes_whitespace_page_numbers_and_repeated_headers() -> None:
    text = "COURT HEADER\n\nPage 1\nSection 482 CrPC\nCOURT HEADER\nCOURT HEADER\n"

    assert clean_text(text) == "Section 482 CrPC"


def test_deduplicate_documents_removes_repeated_text() -> None:
    documents = [
        LegalDocument("first", "Section 482 permits relief.", "aila"),
        LegalDocument("duplicate", "Section 482 permits relief.", "aila"),
    ]

    assert [document.doc_id for document in deduplicate_documents(documents)] == ["first"]


def test_chunking_preserves_offsets_parent_ids_and_overlap() -> None:
    text = "one two three four five six seven eight nine ten"
    document = LegalDocument("case-1", text, "aila", {"license": "CC BY 4.0"})
    chunks = chunk_document(document, chunk_size=4, overlap=0.25)

    assert chunks[0].text == "one two three four"
    assert chunks[0].start_char == 0
    assert text[chunks[1].start_char : chunks[1].end_char] == chunks[1].text
    assert chunks[1].doc_id == "case-1"
    assert chunks[0].metadata == {"license": "CC BY 4.0"}
    assert chunks[1].text.startswith("four")
    assert all(chunk.token_count <= 4 for chunk in chunks)


def test_chunking_prefers_paragraph_boundaries() -> None:
    document = LegalDocument("case-2", "one two three four\n\nfive six seven eight", "aila")

    chunks = chunk_document(document, chunk_size=5, overlap=0)

    assert chunks[0].text == "one two three four"
    assert " ".join(chunk.text for chunk in chunks) == "one two three four five six seven eight"


def test_chunking_rejects_invalid_parameters_and_handles_empty_documents() -> None:
    empty = LegalDocument("empty", "", "aila")
    nonempty = LegalDocument("case", "one two", "aila")

    assert chunk_document(empty) == []
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_document(nonempty, chunk_size=0)
    with pytest.raises(ValueError, match="overlap"):
        chunk_document(nonempty, overlap=1)


def test_clean_document_and_corpus_statistics() -> None:
    document = clean_document(
        LegalDocument("case", "Judgment text\nPage 4", "ildc", {"court": "SC", "year": 2021})
    )
    chunks = chunk_documents([document], chunk_size=20)
    stats = corpus_statistics([document], chunks)

    assert document.text == "Judgment text"
    assert stats["document_count"] == 1
    assert stats["chunk_count"] == 1
    assert stats["documents_by_court"] == {"SC": 1}
    assert stats["documents_by_year"] == {"2021": 1}


def test_ingestion_cli_writes_processed_corpus_and_statistics(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.json"
    raw_path.write_text(
        json.dumps([{"id": "case-1", "text": "Section 482 CrPC", "court": "SC"}]),
        encoding="utf-8",
    )
    processed_path = tmp_path / "processed"
    stats_path = tmp_path / "stats.json"
    config_path = tmp_path / "data.yaml"
    config_path.write_text(
        "\n".join(
            [
                "corpus:",
                "  source: ildc",
                f"  input_path: {raw_path.as_posix()}",
                "  chunk_size: 10",
                "  overlap: 0.15",
                "paths:",
                f"  processed_dir: {processed_path.as_posix()}",
                f"  statistics_path: {stats_path.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )

    result = run_ingestion(config_path)

    assert result["document_count"] == 1
    assert result["chunk_count"] == 1
    assert json.loads(stats_path.read_text(encoding="utf-8"))["documents_by_court"] == {"SC": 1}
    assert (processed_path / "documents.jsonl").exists()
    assert (processed_path / "chunks.jsonl").exists()
