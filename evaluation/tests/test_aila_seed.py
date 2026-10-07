from __future__ import annotations

import json

from backend.app.services.ingestion.chunker import LegalChunk
from evaluation.seed_aila_benchmark import seed_benchmark


def _write_jsonl(path, records) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_seeds_real_task_specific_bm25_metrics(tmp_path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    queries_path = tmp_path / "queries.jsonl"
    priorcase_qrels_path = tmp_path / "priorcase-qrels.jsonl"
    statute_qrels_path = tmp_path / "statute-qrels.jsonl"
    chunks = [
        LegalChunk(
            "C1", "C1:0", "section 482 criminal procedure", 0, 31, 4, {"document_type": "judgment"}
        ),
        LegalChunk("C2", "C2:0", "property transfer law", 0, 21, 3, {"document_type": "judgment"}),
        LegalChunk(
            "S1", "S1:0", "section 482 criminal procedure", 0, 31, 4, {"document_type": "statute"}
        ),
        LegalChunk("S2", "S2:0", "property transfer law", 0, 21, 3, {"document_type": "statute"}),
    ]
    _write_jsonl(
        chunks_path,
        [
            {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ],
    )
    _write_jsonl(
        queries_path,
        [
            {"query_id": "case1", "text": "section 482", "query_type": "priorcases"},
            {"query_id": "statute1", "text": "section 482", "query_type": "statutes"},
        ],
    )
    _write_jsonl(
        priorcase_qrels_path,
        [
            {"query_id": "case1", "doc_id": "C1", "relevance": 1},
            {"query_id": "case1", "doc_id": "C2", "relevance": 0},
        ],
    )
    _write_jsonl(
        statute_qrels_path,
        [
            {"query_id": "statute1", "doc_id": "S1", "relevance": 1},
            {"query_id": "statute1", "doc_id": "S2", "relevance": 0},
            {"query_id": "statute1", "doc_id": "S58", "relevance": 1},
        ],
    )

    metrics_path = seed_benchmark(
        chunks_path,
        queries_path,
        priorcase_qrels_path,
        statute_qrels_path,
        tmp_path / "results",
    )

    result = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert result["query_count"] == 2
    assert result["systems"]["bm25"]["mrr"] == 1.0
    assert result["tasks"]["priorcases"]["document_count"] == 2
    assert result["tasks"]["statutes"]["systems"]["bm25"]["map"] == 0.5
    assert result["tasks"]["statutes"]["missing_judged_document_ids"] == ["S58"]
    assert result["license"] == "CC BY 4.0"
