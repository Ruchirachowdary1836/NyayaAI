from __future__ import annotations

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
from backend.app.api.v1.feedback import initialize_feedback_store
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging
from backend.app.db.database import Database
from backend.app.services.auth import initialize_auth_store
from backend.app.services.generation.llm import OllamaGenerator
from backend.app.services.retrieval.registry import RetrieverRegistry
from backend.app.services.retrieval.service import load_chunks

configure_logging()
logger = logging.getLogger("nyayaai.api")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    chunks = load_chunks(settings.data_chunks_path)
    application.state.retrievers = RetrieverRegistry(
        chunks,
        embedding_model=settings.embedding_model,
    )
    application.state.generator = OllamaGenerator(
        base_url=settings.ollama_base_url,
        model=settings.generator_model,
    )
    application.state.documents_path = Path(settings.data_documents_path)
    application.state.results_dir = Path(settings.results_dir)
    application.state.database = Database(settings.database_url)
    application.state.feedback_db = application.state.database
    application.state.auth_db = application.state.database
    initialize_feedback_store(application.state.database)
    initialize_auth_store(application.state.database)
    yield
    application.state.database.close()


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Hybrid legal retrieval and QA for Indian case law and statutes.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_requests: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
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


@app.get("/ready", tags=["health"])
def ready() -> dict[str, str | int]:
    registry: RetrieverRegistry = app.state.retrievers
    return {
        "status": "ready",
        "corpus_documents": registry.document_count,
        "corpus_chunks": registry.corpus_size,
    }
