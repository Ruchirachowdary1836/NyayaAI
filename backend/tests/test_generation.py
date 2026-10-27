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


import httpx  # noqa: E402
import pytest  # noqa: E402
from backend.app.services.generation.citation_checker import split_interpretation  # noqa: E402
from backend.app.services.generation.llm import GenerationError, OllamaGenerator  # noqa: E402


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_transport(monkeypatch, handler) -> None:
    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.parametrize(
    ("status", "kind", "http_status"),
    [
        (401, "auth", 503),
        (404, "model", 503),
        (429, "rate_limit", 503),
        (500, "provider_error", 502),
    ],
)
async def test_provider_http_errors_are_classified(monkeypatch, status, kind, http_status) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(status, json={"error": "x"}))
    generator = OpenAICompatibleGenerator("sk-test", model="m")
    with pytest.raises(GenerationError) as caught:
        await generator.generate("prompt")
    assert caught.value.kind == kind
    assert caught.value.status_code == http_status
    assert "sk-test" not in str(caught.value)


async def test_provider_timeouts_and_malformed_responses(monkeypatch) -> None:
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    _patch_transport(monkeypatch, timeout)
    with pytest.raises(GenerationError) as caught:
        await OllamaGenerator("http://ollama.test", "m").generate("prompt")
    assert (caught.value.kind, caught.value.status_code) == ("timeout", 504)

    _patch_transport(monkeypatch, lambda request: httpx.Response(200, content=b"not json"))
    with pytest.raises(GenerationError) as caught:
        await OpenAICompatibleGenerator("key", "m").generate("prompt")
    assert caught.value.kind == "malformed"

    _patch_transport(monkeypatch, lambda request: httpx.Response(200, json={"choices": []}))
    with pytest.raises(GenerationError) as caught:
        await OpenAICompatibleGenerator("key", "m").generate("prompt")
    assert caught.value.kind == "empty"


def test_seed_is_omitted_only_for_gemini() -> None:
    gemini = OpenAICompatibleGenerator(
        "key", "m", "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    assert "seed" not in gemini._payload("prompt", 42, False)
    assert OpenAICompatibleGenerator("key", "m")._payload("prompt", 42, False)["seed"] == 42


async def test_openai_stream_parses_tokens(monkeypatch) -> None:
    body = (
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" world [1]."}}]}\n\n'
        "data: [DONE]\n\n"
    )
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, content=body.encode()))
    tokens = [token async for token in OpenAICompatibleGenerator("key", "m").stream("prompt")]
    assert "".join(tokens) == "Hello world [1]."


def test_interpretation_is_split_from_sourced_answer() -> None:
    sourced, interpretation = split_interpretation("Fact [1].\n\nInterpretation: An opinion.")
    assert sourced == "Fact [1]."
    assert interpretation == "An opinion."
    audit = audit_citations("Fact [1].\n\nInterpretation: An uncited opinion.", 1)
    assert audit.unsupported_sentences == ()
    assert audit.interpretation == "An uncited opinion."


def test_citation_variants_are_normalized() -> None:
    from backend.app.services.generation.citation_checker import normalize_citations

    assert normalize_citations("A [1, 2]. B [Passage 3]. C [passages 1 and 4].") == (
        "A [1][2]. B [3]. C [1][4]."
    )
    assert normalize_citations("Not a citation [see above].") == "Not a citation [see above]."


@pytest.mark.parametrize(
    "answer",
    [
        "The available evidence is insufficient to answer this question",
        "the available evidence is insufficient to answer this question.",
        '"The available evidence is insufficient to answer this question."',
    ],
)
def test_insufficient_evidence_variants_are_recognised(answer) -> None:
    from backend.app.services.generation.pipeline import is_insufficient_evidence

    assert is_insufficient_evidence(answer)
