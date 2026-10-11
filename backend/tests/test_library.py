from __future__ import annotations

from backend.app.core.config import settings
from conftest import register


def minimal_pdf(text: str) -> bytes:
    """Build a one-page PDF whose text pypdf can extract."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def upload(client, headers, name, content, content_type="text/plain", title=None):
    data = {"title": title} if title else {}
    return client.post(
        "/api/v1/library/documents",
        headers=headers,
        files={"file": (name, content, content_type)},
        data=data,
    )


def test_upload_text_and_pdf_then_list_view_download_search_delete(client) -> None:
    headers = register(client)
    text = upload(
        client, headers, "lease.txt", b"Tenancy agreement.\r\nRent is due monthly.", title="Lease"
    )
    assert text.status_code == 201, text.text
    assert text.json()["status"] == "ready"
    assert text.json()["title"] == "Lease"
    pdf = upload(
        client,
        headers,
        "notice.pdf",
        minimal_pdf("Notice of eviction under the Rent Act"),
        "application/pdf",
    )
    assert pdf.status_code == 201, pdf.text
    assert pdf.json()["status"] == "ready"
    assert pdf.json()["page_count"] == 1

    listing = client.get("/api/v1/library/documents", headers=headers).json()
    assert listing["total"] == 2
    assert (
        client.get("/api/v1/library/documents", headers=headers, params={"q": "lease"}).json()[
            "total"
        ]
        == 1
    )

    document_id = pdf.json()["document_id"]
    detail = client.get(f"/api/v1/library/documents/{document_id}", headers=headers).json()
    assert "eviction" in detail["text"]

    download = client.get(
        f"/api/v1/library/documents/{text.json()['document_id']}/download", headers=headers
    )
    assert download.status_code == 200
    assert download.content == b"Tenancy agreement.\r\nRent is due monthly."
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"

    search = client.post(
        "/api/v1/library/search", headers=headers, json={"query": "eviction"}
    ).json()
    assert [hit["document_id"] for hit in search["hits"]] == [document_id]

    assert (
        client.delete(f"/api/v1/library/documents/{document_id}", headers=headers).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/library/documents/{document_id}", headers=headers).status_code == 404
    )
    assert (
        client.post("/api/v1/library/search", headers=headers, json={"query": "eviction"}).json()[
            "hits"
        ]
        == []
    )


def test_documents_are_private_to_their_owner(client) -> None:
    owner = register(client, "owner")
    other = register(client, "intruder")
    document_id = upload(client, owner, "private.txt", b"Confidential brief").json()["document_id"]
    for method, path in (
        ("get", f"/api/v1/library/documents/{document_id}"),
        ("get", f"/api/v1/library/documents/{document_id}/download"),
        ("delete", f"/api/v1/library/documents/{document_id}"),
    ):
        assert getattr(client, method)(path, headers=other).status_code == 404
    assert client.get("/api/v1/library/documents", headers=other).json()["total"] == 0
    assert (
        client.post("/api/v1/library/search", headers=other, json={"query": "confidential"}).json()[
            "hits"
        ]
        == []
    )
    assert client.get(f"/api/v1/library/documents/{document_id}", headers=owner).status_code == 200


def test_upload_validation_checks_content_not_just_extensions(client) -> None:
    headers = register(client)
    assert upload(client, headers, "fake.pdf", b"just text", "application/pdf").status_code == 422
    assert upload(client, headers, "binary.txt", b"MZ\x90\x00executable").status_code == 422
    assert upload(client, headers, "latin1.txt", "café".encode("latin-1")).status_code == 422
    assert upload(client, headers, "script.exe", b"hello").status_code == 422
    assert upload(client, headers, "empty.txt", b"").status_code == 422


def test_upload_size_limit_duplicates_and_failed_extraction(client, monkeypatch) -> None:
    headers = register(client)
    monkeypatch.setattr(settings, "upload_max_bytes", 1024)
    too_big = upload(client, headers, "big.txt", b"a" * 2048)
    assert too_big.status_code == 413
    first = upload(client, headers, "same.txt", b"identical content")
    assert first.status_code == 201
    duplicate = upload(client, headers, "copy.txt", b"identical content")
    assert duplicate.status_code == 409
    empty_pdf = upload(client, headers, "scan.pdf", minimal_pdf(""), "application/pdf")
    assert empty_pdf.status_code == 201
    assert empty_pdf.json()["status"] == "failed"
    assert "OCR" in empty_pdf.json()["error"]


def test_path_traversal_filenames_are_sanitised(client) -> None:
    headers = register(client)
    response = upload(client, headers, "../../etc/passwd.txt", b"root")
    assert response.status_code == 201
    assert response.json()["filename"] == "passwd.txt"


def test_library_documents_persist_across_restarts(tmp_path) -> None:
    from backend.app.main import app
    from conftest import wait_until_ready, write_corpus
    from fastapi.testclient import TestClient

    write_corpus(tmp_path)
    with TestClient(app) as first:
        wait_until_ready(first)
        headers = register(first)
        upload(first, headers, "kept.txt", b"Persistent document")
    with TestClient(app) as second:
        wait_until_ready(second)
        assert second.get("/api/v1/library/documents", headers=headers).json()["total"] == 1
