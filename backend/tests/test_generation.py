from backend.app.services.explain.confidence import confidence_score
from backend.app.services.generation.citation_checker import audit_citations
from backend.app.services.generation.llm import OpenAICompatibleGenerator, build_generator
from backend.app.services.retrieval.base import Hit


def test_citation_audit_detects_valid_invalid_and_uncited_statements() -> None:
    audit = audit_citations("Supported legal statement [1]. Unsupported extra claim. Wrong [3].", 2)

    assert audit.valid_citations == (1,)
    assert audit.invalid_citations == (3,)
    assert audit.unsupported_sentences == ("Unsupported extra claim.",)
    assert audit.citation_precision == 0.5


def test_confidence_is_bounded_and_rewards_fusion_agreement() -> None:
    hits = [
        Hit("a", "a:0", "evidence", 0.04, 1, {"bm25_rank": 1, "dense_rank": 1}),
        Hit("b", "b:0", "evidence", 0.02, 2, {"bm25_rank": 2, "dense_rank": 2}),
    ]

    confidence = confidence_score(hits, [1])

    assert 0 <= confidence <= 1
    assert confidence > confidence_score(hits, [])


def test_generation_configuration_fails_explicitly_without_provider_key():
    generator = build_generator(
        provider="openai",
        api_key="",
        api_base_url="https://api.openai.com/v1",
        ollama_base_url="http://localhost:11434",
        model="gpt-4o-mini",
    )

    assert isinstance(generator, OpenAICompatibleGenerator)
    assert generator.configured is False


def test_generation_provider_rejects_unknown_provider():
    import pytest

    with pytest.raises(ValueError, match="Unsupported generation provider"):
        build_generator("random", "", "", "", "")
