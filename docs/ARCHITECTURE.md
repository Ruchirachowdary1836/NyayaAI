# Architecture overview

NyayaAI follows a layered architecture designed around reproducible legal retrieval and answer generation.

## System layers

1. User interfaces
   - React + TypeScript + Vite client for search, QA, comparison, and experiment dashboards.
2. API layer
   - FastAPI endpoints expose retrieval, comparison, QA, document lookup, and admin services.
3. Retrieval services
   - BM25, dense embedding, and hybrid fusion are implemented behind a common interface.
4. Generation services
   - A locally hosted open-source LLM produces answers from retrieved passages only.
5. Explainability layer
   - Citation auditing, confidence estimation, and provenance are surfaced in the API and UI.
6. Data layer
   - PostgreSQL (Compose) or local SQLite stores user and feedback records; normalized corpus text and chunk indices live in gitignored data directories.
   - MLflow tracks configured offline retrieval experiments.

## Design goals

- Controlled experiments with a single changing variable: the retriever.
- Explainable outputs with exact passage provenance.
- Reproducible metrics and exportable evaluation artifacts.
- Assistive legal guidance rather than definitive legal advice.
- Authentication uses signed user/admin JWTs, salted PBKDF2 password hashes, and an environment-bootstrapped administrator.
- The current request limiter is process-local and intended for single-instance local research, not horizontally scaled production deployment.
