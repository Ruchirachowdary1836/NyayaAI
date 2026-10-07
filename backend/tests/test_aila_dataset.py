from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from scripts.fetch_aila_corpus import _normalize_archive, _normalize_evaluation_data


def test_normalizes_aila_cases_and_statutes_with_attribution():
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("Object_casedocs/C1.txt", "Example v State\nSupreme Court of India\nText")
        archive.writestr("Object_statutes/S1.txt", "Title: Example Act\nDesc: Example provision")

    documents = _normalize_archive(archive_buffer.getvalue(), 1, 1)

    assert [document["doc_id"] for document in documents] == ["C1", "S1"]
    assert documents[0]["document_type"] == "judgment"
    assert documents[0]["title"] == "Example v State"
    assert documents[1]["document_type"] == "statute"
    assert documents[1]["title"] == "Example Act"
    assert all(document["license"] == "CC BY 4.0" for document in documents)
    assert all("attribution" in document and "source_url" in document for document in documents)


def test_rejects_unexpected_dataset_counts():
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("Object_casedocs/C1.txt", "Example judgment")

    with pytest.raises(ValueError, match="Unexpected AILA archive contents"):
        _normalize_archive(archive_buffer.getvalue(), 2, 0)


def test_normalizes_official_aila_queries_and_task_qrels():
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("Query_doc.txt", "AILA_Q1||case facts\nAILA_Q2||statute facts\n")
        archive.writestr(
            "relevance_judgments_priorcases.txt",
            "AILA_Q1 Q0 C1 1\nAILA_Q1 Q0 C2 0\nAILA_Q2 Q0 C1 0\n",
        )
        archive.writestr(
            "relevance_judgments_statutes.txt",
            "AILA_Q1 Q0 S1 0\nAILA_Q2 Q0 S2 1\n",
        )

    queries, qrels = _normalize_evaluation_data(
        archive_buffer.getvalue(),
        expected_query_count=2,
    )

    assert len(queries) == 4
    assert queries[0] == {
        "query_id": "AILA_Q1_priorcases",
        "text": "case facts",
        "query_type": "priorcases",
    }
    assert qrels["priorcases"][0] == {
        "query_id": "AILA_Q1_priorcases",
        "doc_id": "C1",
        "relevance": 1,
    }
    assert qrels["statutes"][1]["doc_id"] == "S2"
