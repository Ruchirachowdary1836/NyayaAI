# Architecture and product decisions

This document captures the default choices made during Phase 0 and later phases for reproducibility.

## Phase 0 decisions

1. Repository layout follows the project proposal exactly: backend, frontend, evaluation, configs, docs, and data directories.
2. Python 3.11 is chosen as the backend runtime to align with the requested ecosystem and compatibility requirements.
3. FastAPI is adopted as the API layer with Pydantic v2 and SQLAlchemy 2 for typed, async service boundaries.
4. PostgreSQL is the system-of-record database for metadata and experiment logging, with Docker Compose orchestrating the local environment.
5. Frontend uses React 18 + TypeScript + Vite + Tailwind CSS to satisfy the design and UI requirements while keeping production builds fast.
6. Retrieval experiments are configured through YAML files and environment variables, so the same corpus and query set can be re-used while swapping only the retriever.
7. All generated answers are assistive-only and must always include a visible legal disclaimer in both the UI and API payloads.
8. Reproducibility is enforced through pinned dependency versions, fixed seeds, and reproducible config hashes.

## Future phase governance

- Any later decision that materially changes the architecture or the permitted model set must be documented here.
- The retriever remains the only controlled variable across legal retrieval experiments; all other pipeline components remain frozen.

## Phase 1 decisions

1. Corpus loaders accept JSON, JSONL, and CSV through shared normalized record adapters. AILA queries and relevance judgments are optional inputs and kept separate from corpus documents.
2. Loader field aliases cover common exports without claiming a canonical upstream schema; source-specific transformations should be recorded and versioned when added.
3. Cleaning normalizes Unicode and whitespace, removes page-number-only lines and repeated short headers, and preserves legal numbering and citation content.
4. Chunk sizes are measured in whitespace-delimited tokens for deterministic, dependency-light offsets; chunks retain parent document IDs and character offsets.
5. Raw datasets, processed corpus text, and generated indices remain excluded from version control due to licensing and privacy requirements.

## Full-stack decisions

1. BM25 uses Okapi scoring with a compact postings index to avoid retaining duplicate tokenized corpora in memory; matching chunks remain eligible when small-corpus IDF scores are zero.
2. Dense retrieval normalizes embeddings, prefers an exact FAISS inner-product index, and falls back to exact NumPy cosine search when FAISS is unavailable.
3. Hybrid retrieval uses deterministic RRF or weighted score fusion; evaluation conditions keep retriever configuration fixed.
4. Docker Compose uses PostgreSQL for auth and feedback; direct local development and tests default to file-backed SQLite.
5. Authentication uses salted PBKDF2-HMAC-SHA256 password hashes, signed role-bearing JWTs, user-only self-registration, and an administrator provisioned by environment variables.
6. The UI shares a typed API client and presents an explicit empty-index state rather than seeding synthetic or unlicensed case law.

## Platform completion decisions (2026-10)

1. **Schema migrations.** Alembic owns the schema. Revision `0001_baseline` adopts databases created by the earlier `create_all` path without altering data; `0002_platform_tables` adds account status, token revocation, user documents, experiments, and usage events. Migrations run automatically (idempotently) at API startup and via `alembic upgrade head`.
2. **Usernames stay the user primary key** for compatibility with existing deployments. Foreign keys use `ON UPDATE CASCADE` so renames carry owned rows; SQLite enforces them via `PRAGMA foreign_keys=ON`.
3. **Bearer tokens, not cookies.** The static site and API are on different `onrender.com` subdomains, which browsers treat as cross-site, so cookie sessions would be unreliable. Tokens are short-lived JWTs with `jti`/`iat`; logout revokes the `jti`, and password/role/status changes invalidate every earlier token through `tokens_valid_after`.
4. **All `/api/v1` data routes require authentication**, including search, so expensive retrieval and generation are attributable and rate-limited. `/health` and `/ready` stay public.
5. **Uploads live in the database** (bytes and extracted text), because Render's disk is ephemeral. Files are limited to 5 MB and validated by content (PDF signature, UTF-8 text without binary signatures), not by extension.
6. **No silent fallbacks.** A dense model that cannot load is reported as `failed`; compare and experiments list unavailable engines instead of substituting BM25; generation failures map to explicit 502/503/504 errors.
7. **Usage analytics are anonymized**: event type, engine, outcome, result count, and latency only — never query text.
8. **Grounding enforcement.** Common citation variants (`[1, 2]`, `[Passage 1]`) are normalized before auditing; answers with invalid or no citations are withheld, and interpretation is separated from sourced text.
9. **Dependencies split into extras** (`dense`, `tracking`, `dev`) so the default API image does not ship PyTorch, MLflow, or unused packages.
