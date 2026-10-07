from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

ARCHIVE_URL = "https://zenodo.org/api/records/4063986/files/AILA_2019_dataset.zip/content"
ARCHIVE_MD5 = "07f9621e385ff0d4540ce8dfd76b0c21"
SOURCE_URL = "https://doi.org/10.5281/zenodo.4063986"
ATTRIBUTION = (
    "Paheli Bhattacharya, Kripabandhu Ghosh, Saptarshi Ghosh, Arindam Pal, "
    "Parth Mehta, Arnab Bhattacharya, and Prasenjit Majumder"
)
_DOCUMENT_PATH = re.compile(r"Object_(casedocs|statutes)/([CS])(\d+)\.txt$")
_TITLE = re.compile(r"^Title:\s*(.+)$", re.MULTILINE)


def _normalize_archive(
    archive_bytes: bytes, expected_case_count: int = 2914, expected_statute_count: int = 197
) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    case_count = 0
    statute_count = 0
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        for path in sorted(archive.namelist()):
            match = _DOCUMENT_PATH.fullmatch(path)
            if match is None:
                continue
            folder, doc_prefix, _ = match.groups()
            text = archive.read(path).decode("utf-8").strip()
            if not text:
                raise ValueError(f"AILA document is empty: {path}")
            is_case = folder == "casedocs"
            if is_case:
                case_count += 1
                title = text.splitlines()[0].strip()
                document_type = "judgment"
            else:
                statute_count += 1
                title_match = _TITLE.search(text)
                title = title_match.group(1).strip() if title_match else f"Statute {doc_prefix}"
                document_type = "statute"
            documents.append(
                {
                    "doc_id": f"{doc_prefix}{match.group(3)}",
                    "text": text,
                    "document_type": document_type,
                    "title": title,
                    "court": "Supreme Court of India" if is_case else "Indian statute",
                    "source_name": "AILA 2019 Precedent & Statute Retrieval Task",
                    "source_url": SOURCE_URL,
                    "license": "CC BY 4.0",
                    "attribution": ATTRIBUTION,
                }
            )
    if (case_count, statute_count) != (expected_case_count, expected_statute_count):
        raise ValueError(
            "Unexpected AILA archive contents: "
            f"found {case_count} cases and {statute_count} statutes"
        )
    return documents


def fetch_documents() -> list[dict[str, object]]:
    request = urllib.request.Request(
        ARCHIVE_URL, headers={"User-Agent": "NyayaAI/0.1 (AILA CC BY 4.0 corpus ingestion)"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        archive_bytes = response.read()
    checksum = hashlib.md5(archive_bytes, usedforsecurity=False).hexdigest()
    if checksum != ARCHIVE_MD5:
        raise ValueError(f"AILA archive checksum mismatch: got {checksum}")
    return _normalize_archive(archive_bytes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and normalize the AILA 2019 corpus.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    output_path = parser.parse_args().output

    records = fetch_documents()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} AILA documents to {output_path}")


if __name__ == "__main__":
    main()
