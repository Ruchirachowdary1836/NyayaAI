from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.base import Hit, legal_tokenize
from backend.app.services.retrieval.bm25 import BM25Retriever
from backend.app.services.retrieval.dense import DenseRetriever
from backend.app.services.retrieval.hybrid import HybridRetriever
from backend.app.services.retrieval.registry import RetrieverRegistry
from backend.app.services.retrieval.service import load_chunks


def chunk(doc_id: str, text: str) -> LegalChunk:
    return LegalChunk(doc_id, f"{doc_id}:0", text, 0, len(text), len(text.split()))


class StubRetriever:
    def __init__(self, name: str, hits: list[Hit]) -> None:
        self.name = name
        self.hits = hits

    def search(self, query: str, k: int = 10) -> list[Hit]:
        return self.hits[:k]


def hit(doc_id: str, rank: int, score: float, source: str) -> Hit:
    return Hit(
        doc_id=doc_id,
        chunk_id=f"{doc_id}:0",
        text=doc_id,
        score=score,
        rank=rank,
        source_scores={source: score},
    )


def test_legal_tokenizer_preserves_statute_and_section_numbers() -> None:
    assert legal_tokenize("Section 482 CrPC, Article 21 and IPC 302") == [
        "section 482",
        "crpc",
        "article 21",
        "and",
        "ipc 302",
    ]


def test_bm25_retrieves_matching_legal_provision_and_validates_k() -> None:
    retriever = BM25Retriever(
        [
            chunk("quashing", "Section 482 CrPC permits High Court inherent powers."),
            chunk("privacy", "Article 21 protects life and personal liberty."),
        ]
    )

    results = retriever.search("Section 482 CrPC", k=1)

    assert results[0].doc_id == "quashing"
    assert results[0].rank == 1
    assert results[0].source_scores["bm25"] == results[0].score
    with pytest.raises(ValueError, match="k"):
        retriever.search("Section 482", k=0)


def test_bm25_preserves_source_metadata_and_chunk_loader_round_trips(tmp_path) -> None:
    metadata = {
        "document_type": "statute",
        "title": "Example Act",
        "license": "CC BY 4.0",
    }
    text = "Example statute provision."
    original_chunk = LegalChunk("S1", "S1:0", text, 0, len(text), 3, metadata)
    chunk_path = tmp_path / "chunks.jsonl"
    chunk_path.write_text(
        json.dumps(
            {
                "doc_id": original_chunk.doc_id,
                "chunk_id": original_chunk.chunk_id,
                "text": original_chunk.text,
                "start_char": original_chunk.start_char,
                "end_char": original_chunk.end_char,
                "token_count": original_chunk.token_count,
                "metadata": original_chunk.metadata,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    loaded_chunk = load_chunks(chunk_path)[0]
    result = BM25Retriever([loaded_chunk]).search("statute provision")[0]

    assert loaded_chunk.metadata == metadata
    assert result.metadata == metadata


def test_dense_retrieval_with_injected_encoder() -> None:
    vectors = {
        "privacy": np.array([1.0, 0.0], dtype=np.float32),
        "contract": np.array([0.0, 1.0], dtype=np.float32),
        "privacy query": np.array([0.9, 0.1], dtype=np.float32),
    }
    retriever = DenseRetriever(
        [chunk("privacy", "privacy"), chunk("contract", "contract")],
        encoder=lambda texts: np.array([vectors[text] for text in texts]),
    )

    results = retriever.search("privacy query")

    assert [result.doc_id for result in results] == ["privacy", "contract"]
    assert results[0].source_scores["dense"] == pytest.approx(0.9939, rel=1e-3)


def test_rrf_fusion_matches_hand_calculated_example() -> None:
    sparse = StubRetriever(
        "bm25",
        [hit("a", 1, 4.0, "bm25"), hit("b", 2, 3.0, "bm25")],
    )
    dense = StubRetriever(
        "dense",
        [hit("b", 1, 0.9, "dense"), hit("a", 2, 0.8, "dense")],
    )

    results = HybridRetriever(sparse, dense, method="rrf", rrf_k=60).search("query")

    assert results[0].doc_id == "a"
    assert results[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert results[1].score == pytest.approx(1 / 62 + 1 / 61)
    assert results[0].source_scores["bm25_rank"] == 1
    assert results[0].source_scores["dense_rank"] == 2


def test_weighted_hybrid_fusion_respects_alpha() -> None:
    sparse = StubRetriever(
        "bm25",
        [hit("lexical", 1, 10.0, "bm25"), hit("semantic", 2, 0.0, "bm25")],
    )
    dense = StubRetriever(
        "dense",
        [hit("semantic", 1, 1.0, "dense"), hit("lexical", 2, 0.0, "dense")],
    )

    results = HybridRetriever(sparse, dense, method="weighted", alpha=0.75).search("query")

    assert [result.doc_id for result in results] == ["semantic", "lexical"]
    assert results[0].score == pytest.approx(0.75)
    assert results[1].score == pytest.approx(0.25)


def test_registry_loads_bm25_without_eagerly_loading_dense_model() -> None:
    registry = RetrieverRegistry([])

    assert registry.get("bm25").search("no corpus") == []
    assert registry.document_count == 0
    assert registry.available == ["bm25", "dense", "hybrid"]


def test_registry_disables_unconfigured_retrievers_before_model_loading(monkeypatch) -> None:
    from backend.app.services.retrieval import registry as registry_module

    def fail_if_loaded(*args, **kwargs):
        raise AssertionError("Disabled dense model must not be loaded")

    monkeypatch.setattr(registry_module, "DenseRetriever", fail_if_loaded)
    registry = RetrieverRegistry([], enabled_retrievers=["bm25"])

    assert registry.available == ["bm25"]
    with pytest.raises(RuntimeError, match="Dense retrieval is disabled"):
        registry.get("dense")
    with pytest.raises(RuntimeError, match="Hybrid retrieval is disabled"):
        registry.get("hybrid")


def test_registry_initializes_dense_engine_once_for_concurrent_requests(monkeypatch) -> None:
    from backend.app.services.retrieval import registry as registry_module

    calls = 0

    class FakeDense:
        def __init__(self, chunks, model_name, **kwargs) -> None:
            nonlocal calls
            calls += 1
            time.sleep(0.02)

        def search(self, query: str, k: int = 10) -> list[Hit]:
            return []

    monkeypatch.setattr(registry_module, "DenseRetriever", FakeDense)
    registry = RetrieverRegistry([])

    with ThreadPoolExecutor(max_workers=8) as executor:
        retrievers = list(executor.map(lambda _: registry.get("hybrid"), range(16)))

    assert calls == 1
    assert all(retriever is retrievers[0] for retriever in retrievers)


def test_dense_embeddings_are_cached_and_reused(tmp_path) -> None:
    calls = []

    def encoder(texts):
        calls.append(len(texts))
        return np.array([[float(len(text)), 1.0] for text in texts])

    chunks = [chunk("a", "short text"), chunk("b", "a much longer passage of text")]
    first = DenseRetriever(chunks, model_name="test-model", encoder=encoder, cache_dir=tmp_path)
    assert first.loaded_from_cache is False and first.cache_path.is_file()
    second = DenseRetriever(chunks, model_name="test-model", encoder=encoder, cache_dir=tmp_path)
    assert second.loaded_from_cache is True
    assert calls == [
        2,
    ]  # The corpus was embedded once; the second load reused the cache.
    changed = DenseRetriever(
        [chunk("a", "edited text"), chunks[1]],
        model_name="test-model",
        encoder=encoder,
        cache_dir=tmp_path,
    )
    assert changed.loaded_from_cache is False


def test_registry_reports_dense_load_failure_explicitly(monkeypatch) -> None:
    from backend.app.services.retrieval import registry as registry_module

    def broken(*args, **kwargs):
        raise OSError("model download failed")

    monkeypatch.setattr(registry_module, "DenseRetriever", broken)
    registry = RetrieverRegistry(
        [chunk("a", "text")], enabled_retrievers=["bm25", "dense", "hybrid"]
    )
    with pytest.raises(RuntimeError, match="Dense retrieval is unavailable"):
        registry.get("hybrid")
    assert registry.status()["dense"]["state"] == "failed"
    assert registry.get("bm25").search("text")


def test_filtered_search_widens_the_candidate_pool() -> None:
    from backend.app.services.retrieval.search import SearchFilters, run_search

    chunks = [
        LegalChunk(
            f"C{i}", f"C{i}:0", "murder appeal murder", 0, 20, 3, {"document_type": "judgment"}
        )
        for i in range(150)
    ] + [LegalChunk("S1", "S1:0", "murder", 0, 6, 1, {"document_type": "statute"})]
    registry = RetrieverRegistry(chunks, enabled_retrievers=["bm25"])
    page = run_search(registry, "bm25", "murder", SearchFilters(document_type="statute"))
    assert [hit.doc_id for hit in page.hits] == ["S1"]


def test_best_excerpt_centres_on_query_terms() -> None:
    from backend.app.services.retrieval.search import best_excerpt

    text = "filler " * 200 + "the doctrine of res judicata applies" + " filler" * 200
    excerpt = best_excerpt(text, "res judicata", width=120)
    assert "res judicata" in excerpt
    assert excerpt.startswith("…") and excerpt.endswith("…")


def test_bm25_scores_are_positive_for_single_document_collections() -> None:
    results = BM25Retriever([chunk("only", "notice period landlord")]).search("landlord notice")
    assert len(results) == 1
    assert results[0].score > 0
