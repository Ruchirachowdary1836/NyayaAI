from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1 import (
    admin,
    auth,
    compare,
    dashboard,
    documents,
    experiments,
    feedback,
    library,
    qa,
    search,
)
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging
from backend.app.core.rate_limit import global_limiter
from backend.app.db.database import Database
from backend.app.services.auth import initialize_auth_store
from backend.app.services.generation.llm import build_generator
from backend.app.services.retrieval.corpus import CorpusStore
from backend.app.services.retrieval.registry import RetrieverRegistry
from backend.app.services.retrieval.service import load_chunks

configure_logging(settings.log_level)
logger = logging.getLogger("nyayaai.api")

_UNGATED_PATHS = {"/health", "/ready", "/openapi.json", "/docs", "/redoc"}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_UPLOAD_PATH = f"{settings.api_prefix}/library/documents"
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
}


def _initialize_runtime(application: FastAPI) -> None:
    if settings.is_production:
        problems = settings.production_problems()
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
    chunks = load_chunks(settings.data_chunks_path)
    if settings.is_production:
        if not chunks:
            raise RuntimeError("Production startup requires a non-empty processed chunk index.")
        if not Path(settings.data_documents_path).is_file():
            raise RuntimeError("Production startup requires the processed source documents file.")
    retrievers = RetrieverRegistry(
        chunks,
        embedding_model=settings.embedding_model,
        alpha=settings.hybrid_alpha,
        fusion_method=settings.hybrid_method,
        rrf_k=settings.hybrid_rrf_k,
        enabled_retrievers=settings.enabled_retrievers,
        embedding_cache_dir=settings.index_dir,
    )
    corpus = CorpusStore(settings.data_documents_path)
    database = Database(settings.database_url)
    try:
        initialize_auth_store(database)
    except Exception:
        database.close()
        raise

    application.state.retrievers = retrievers
    application.state.corpus = corpus
    application.state.database = database
    logger.info(
        "runtime_initialized documents=%d chunks=%d retrievers=%s schema=%s",
        retrievers.document_count,
        retrievers.corpus_size,
        ",".join(retrievers.available),
        database.schema_revision(),
    )


async def _initialize_runtime_in_background(application: FastAPI) -> None:
    try:
        await asyncio.to_thread(_initialize_runtime, application)
    except Exception:
        application.state.initialization_status = "failed"
        application.state.initialization_error = (
            "NyayaAI initialization failed. Check the API service logs for details."
        )
        logger.exception("Application initialization failed")
    else:
        application.state.initialization_status = "ready"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.initialization_status = "initializing"
    application.state.initialization_error = None
    application.state.retrievers = None
    application.state.corpus = None
    application.state.database = None
    application.state.generator = build_generator(
        provider=settings.generator_provider,
        api_key=settings.generator_api_key,
        api_base_url=settings.generator_api_base_url,
        ollama_base_url=settings.ollama_base_url,
        model=settings.generator_model,
        timeout=settings.generator_timeout_seconds,
    )
    application.state.results_dir = Path(settings.results_dir)
    initialization_task = asyncio.create_task(_initialize_runtime_in_background(application))
    try:
        yield
    finally:
        if not initialization_task.done():
            initialization_task.cancel()
            await asyncio.gather(initialization_task, return_exceptions=True)
        database = application.state.database
        if database is not None:
            database.close()


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description=(
        "Evidence-first legal retrieval and grounded question answering over Indian case law "
        "and statutes. Authenticate with `POST /api/v1/auth/token` and send the returned "
        "bearer token on every `/api/v1` request."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Bearer tokens are sent in the Authorization header; no cookies are used.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept"],
    expose_headers=["X-Request-ID", "Retry-After", "Content-Disposition"],
)


def _json(status_code: int, content: dict, request_id: str, **headers: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={**content, "request_id": request_id},
        headers={"X-Request-ID": request_id, **_SECURITY_HEADERS, **headers},
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if _REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
    request.state.request_id = request_id
    path = request.url.path
    if request.method != "OPTIONS" and path not in _UNGATED_PATHS:
        initialization_status = getattr(request.app.state, "initialization_status", "initializing")
        if initialization_status != "ready":
            detail = (
                request.app.state.initialization_error
                if initialization_status == "failed"
                else "NyayaAI is initializing its corpus index and database. Retry shortly."
            )
            return _json(
                503,
                {"detail": detail, "status": initialization_status},
                request_id,
                **{"Retry-After": "5"},
            )
    if request.method == "POST" and path == _UPLOAD_PATH:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.upload_max_bytes + 65_536:
            return _json(
                413,
                {
                    "detail": f"Uploads are limited to {settings.upload_max_bytes // (1024 * 1024)} MB."
                },
                request_id,
            )
    client_ip = request.client.host if request.client else "unknown"
    if (
        request.method != "OPTIONS"
        and path not in {"/health", "/ready"}
        and not global_limiter.allow(f"ip:{client_ip}", settings.rate_limit_per_minute)
    ):
        return _json(429, {"detail": "Rate limit exceeded"}, request_id, **{"Retry-After": "60"})
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    # Query strings are omitted from logs because they can contain user input.
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, error: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    logger.exception("unhandled_error request_id=%s path=%s", request_id, request.url.path)
    return _json(500, {"detail": "Internal server error"}, request_id)


for route in (
    auth.router,
    dashboard.router,
    search.router,
    compare.router,
    qa.router,
    documents.router,
    library.router,
    experiments.router,
    feedback.router,
    admin.router,
):
    app.include_router(route, prefix=settings.api_prefix)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness: the process is up and serving HTTP."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"], response_model=None)
def ready(request: Request) -> dict[str, object] | JSONResponse:
    """Readiness: corpus index, database, and engine availability."""
    state = request.app.state
    generator = state.generator
    generation = {
        "generation_configured": bool(getattr(generator, "configured", False)),
        "generation_provider": getattr(generator, "provider", settings.generator_provider),
        "generation_model": getattr(generator, "model", None),
    }
    initialization_status = getattr(state, "initialization_status", "initializing")
    if initialization_status != "ready":
        return JSONResponse(
            status_code=503,
            content={
                "status": initialization_status,
                "detail": getattr(state, "initialization_error", None)
                or "NyayaAI is initializing its corpus index and database. Retry shortly.",
                "corpus_documents": 0,
                "corpus_chunks": 0,
                "available_retrievers": settings.enabled_retrievers,
                **generation,
            },
        )
    registry: RetrieverRegistry = state.retrievers
    database_ok = state.database.ping()
    body = {
        "status": "ready" if database_ok else "degraded",
        "database": "ok" if database_ok else "unreachable",
        "corpus_documents": registry.document_count,
        "corpus_chunks": registry.corpus_size,
        "available_retrievers": registry.available,
        "retrievers": registry.status(),
        **generation,
    }
    return body if database_ok else JSONResponse(status_code=503, content=body)
