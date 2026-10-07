from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1 import admin, auth, compare, documents, experiments, feedback, qa, search
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging
from backend.app.db.database import Database
from backend.app.services.auth import initialize_auth_store
from backend.app.services.generation.llm import build_generator
from backend.app.services.retrieval.registry import RetrieverRegistry
from backend.app.services.retrieval.service import load_chunks

configure_logging()
logger = logging.getLogger("nyayaai.api")


def _initialize_runtime(application: FastAPI) -> None:
    chunks = load_chunks(settings.data_chunks_path)
    retrievers = RetrieverRegistry(
        chunks,
        embedding_model=settings.embedding_model,
    )
    database = Database(settings.database_url)
    try:
        initialize_auth_store(database)
    except Exception:
        database.close()
        raise

    application.state.retrievers = retrievers
    application.state.database = database
    application.state.feedback_db = database
    application.state.auth_db = database


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
        logger.info("Application initialization completed")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.initialization_status = "initializing"
    application.state.initialization_error = None
    application.state.retrievers = None
    application.state.database = None
    application.state.feedback_db = None
    application.state.auth_db = None
    application.state.generator = build_generator(
        provider=settings.generator_provider,
        api_key=settings.generator_api_key,
        api_base_url=settings.generator_api_base_url,
        ollama_base_url=settings.ollama_base_url,
        model=settings.generator_model,
    )
    application.state.documents_path = Path(settings.data_documents_path)
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
    version="0.2.0",
    description="Hybrid legal retrieval and QA for Indian case law and statutes.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_requests: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    if request.method != "OPTIONS" and request.url.path not in {
        "/health",
        "/ready",
        "/openapi.json",
        "/docs",
        "/redoc",
    }:
        initialization_status = getattr(request.app.state, "initialization_status", "initializing")
        if initialization_status != "ready":
            detail = (
                request.app.state.initialization_error
                if initialization_status == "failed"
                else "NyayaAI is initializing its corpus index and database. Retry shortly."
            )
            return JSONResponse(
                status_code=503,
                content={"detail": detail, "status": initialization_status},
                headers={"X-Request-ID": request_id, "Retry-After": "5"},
            )
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = _requests[client_ip]
    while recent and recent[0] < now - 60:
        recent.popleft()
    if (
        request.url.path not in {"/health", "/ready"}
        and len(recent) >= settings.rate_limit_per_minute
    ):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded", "request_id": request_id},
            headers={"X-Request-ID": request_id, "Retry-After": "60"},
        )
    recent.append(now)
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.monotonic() - started) * 1000,
    )
    return response


for route in (
    search.router,
    compare.router,
    qa.router,
    documents.router,
    experiments.router,
    feedback.router,
    auth.router,
    admin.router,
):
    app.include_router(route, prefix=settings.api_prefix)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["health"], response_model=None)
def ready(request: Request) -> dict[str, str | int | bool] | JSONResponse:
    initialization_status = getattr(request.app.state, "initialization_status", "initializing")
    if initialization_status != "ready":
        return JSONResponse(
            status_code=503,
            content={
                "status": initialization_status,
                "detail": getattr(request.app.state, "initialization_error", None)
                or "NyayaAI is initializing its corpus index and database. Retry shortly.",
                "corpus_documents": 0,
                "corpus_chunks": 0,
                "generation_configured": getattr(request.app.state.generator, "configured", True),
                "generation_provider": settings.generator_provider,
            },
        )
    registry: RetrieverRegistry = app.state.retrievers
    generator = app.state.generator
    return {
        "status": "ready",
        "corpus_documents": registry.document_count,
        "corpus_chunks": registry.corpus_size,
        "generation_configured": generator.configured if hasattr(generator, "configured") else True,
        "generation_provider": settings.generator_provider,
    }
