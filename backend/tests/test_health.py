from backend.app.core.config import DEFAULT_JWT_SECRET, Settings


def test_default_retriever_configuration_is_safe() -> None:
    assert Settings(_env_file=None).enabled_retrievers == ["bm25"]


def test_production_configuration_problems_are_detected() -> None:
    unsafe = Settings(_env_file=None, jwt_secret_key=DEFAULT_JWT_SECRET, cors_origins=["*"])
    problems = unsafe.production_problems()
    assert any("JWT_SECRET_KEY" in problem for problem in problems)
    assert any("CORS_ORIGINS" in problem for problem in problems)
    assert any("DATABASE_URL" in problem for problem in problems)
    safe = Settings(
        _env_file=None,
        jwt_secret_key="s" * 48,
        cors_origins=["https://app.example.org"],
        database_url="postgresql://user:pw@db/nyaya",
    )
    assert safe.production_problems() == []


def test_empty_embedding_dimensions_is_treated_as_unset() -> None:
    assert Settings(_env_file=None, embedding_dimensions="").embedding_dimensions is None
    assert Settings(_env_file=None, embedding_dimensions="768").embedding_dimensions == 768
