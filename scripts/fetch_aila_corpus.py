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
    return _normalize_archive(_download_archive())


def _download_archive() -> bytes:
    request = urllib.request.Request(
        ARCHIVE_URL, headers={"User-Agent": "NyayaAI/0.1 (AILA CC BY 4.0 corpus ingestion)"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        archive_bytes = response.read()
    checksum = hashlib.md5(archive_bytes, usedforsecurity=False).hexdigest()
    if checksum != ARCHIVE_MD5:
        raise ValueError(f"AILA archive checksum mismatch: got {checksum}")
    return archive_bytes


def _normalize_evaluation_data(
    archive_bytes: bytes,
    expected_query_count: int = 50,
) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        queries: list[dict[str, object]] = []
        for line in archive.read("Query_doc.txt").decode("utf-8").splitlines():
            query_id, separator, text = line.partition("||")
            if not separator or not query_id.strip() or not text.strip():
                raise ValueError(f"Invalid AILA query record: {line[:80]}")
            for task in ("priorcases", "statutes"):
                queries.append(
                    {
                        "query_id": f"{query_id.strip()}_{task}",
                        "text": text.strip(),
                        "query_type": task,
                    }
                )
        if len(queries) != expected_query_count * 2:
            raise ValueError(
                f"Expected {expected_query_count} AILA queries, found {len(queries) // 2}"
            )

        qrels_by_task: dict[str, list[dict[str, object]]] = {}
        for task, filename in (
            ("priorcases", "relevance_judgments_priorcases.txt"),
            ("statutes", "relevance_judgments_statutes.txt"),
        ):
            qrels: list[dict[str, object]] = []
            for line in archive.read(filename).decode("utf-8").splitlines():
                fields = line.split()
                if len(fields) != 4:
                    raise ValueError(f"Invalid AILA relevance judgment: {line[:80]}")
                query_id, _, document_id, relevance = fields
                qrels.append(
                    {
                        "query_id": f"{query_id}_{task}",
                        "doc_id": document_id,
                        "relevance": int(relevance),
                    }
                )
            if not qrels:
                raise ValueError(f"AILA relevance judgments are empty: {filename}")
            qrels_by_task[task] = qrels
    return queries, qrels_by_task


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and normalize the AILA 2019 corpus.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    parser.add_argument(
        "--evaluation-output-dir",
        type=Path,
        help="Optional directory for licensed official queries and relevance judgments",
    )
    args = parser.parse_args()

    archive_bytes = _download_archive()
    records = _normalize_archive(archive_bytes)
    _write_jsonl(args.output, records)
    print(f"Wrote {len(records)} AILA documents to {args.output}")
    if args.evaluation_output_dir:
        queries, qrels_by_task = _normalize_evaluation_data(archive_bytes)
        _write_jsonl(args.evaluation_output_dir / "queries.jsonl", queries)
        for task, qrels in qrels_by_task.items():
            _write_jsonl(args.evaluation_output_dir / f"qrels_{task}.jsonl", qrels)
        print(
            f"Wrote {len(queries)} task queries and "
            f"{sum(map(len, qrels_by_task.values()))} relevance judgments "
            f"to {args.evaluation_output_dir}"
        )


if __name__ == "__main__":
    main()
