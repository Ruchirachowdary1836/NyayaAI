from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from scripts.fetch_aila_corpus import _normalize_archive


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
