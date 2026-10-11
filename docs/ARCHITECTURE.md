# Architecture overview

NyayaAI is a React single-page app talking to a FastAPI service over a JSON API. The API owns
all retrieval, generation, persistence, and authorization; the browser never sees provider
credentials or other users' data.

```
Browser (React SPA) ──HTTPS + Bearer JWT──▶ FastAPI ──▶ RetrieverRegistry (BM25 · dense · hybrid)
                                              │       ├─▶ CorpusStore (documents.jsonl, offset index)
                                              │       ├─▶ Generator (Ollama | OpenAI-compatible)
                                              │       └─▶ Database (SQLAlchemy Core + Alembic)
                                              └─ /health, /ready
```

## Backend layers (`backend/app`)

| Layer | Modules | Responsibility |
|---|---|---|
| API | `api/v1/*.py`, `api/deps.py` | Routing, validation (Pydantic), auth dependencies, rate limits, usage logging |
| Core | `core/config.py`, `core/security.py`, `core/rate_limit.py` | Settings from env/.env, JWT issue/verify, sliding-window limiters |
| Data | `db/tables.py`, `db/database.py`, `db/migrations/` | Schema (Alembic-managed), repository methods, SQLite FK enforcement |
| Retrieval | `services/retrieval/*` | BM25 postings index, dense embeddings (+ on-disk cache), RRF/weighted fusion, filtered search, excerpts |
| Generation | `services/generation/*` | Provider abstraction with typed errors, grounded prompt, citation normalization and audit |
| Library | `services/library.py` | Upload validation (content sniffing), PDF/text extraction, per-user BM25 search |
| Experiments | `services/experiments.py` | Same-corpus multi-engine runs, document-level rankings, IR metrics |
| Ingestion | `services/ingestion/*` | Load → clean → dedupe → enrich metadata → chunk → write JSONL + report |

### Request lifecycle

1. Middleware assigns/validates `X-Request-ID`, returns 503 until initialization completes,
   applies the per-IP limit, adds security headers, and logs method/path/status/duration
   (never query strings or bodies).
2. Route dependencies authenticate the bearer token: signature, expiry, required claims,
   account active, role unchanged, token not revoked, and issued after the account's
   `tokens_valid_after` cutoff (set on password change, role change, or deactivation).
3. Handlers call services and record an anonymized usage event (type, engine, outcome, latency).

### Startup

`/health` answers immediately. In the background the app loads chunks, builds BM25, indexes
`documents.jsonl` offsets, runs `alembic upgrade head`, and bootstraps the optional admin.
`/ready` then reports database status, corpus counts, and per-engine state. In production the
app refuses to start with a default JWT secret, wildcard CORS, SQLite, or an empty corpus.

## Retrieval

- **BM25**: Okapi BM25 (k1 = 1.5, b = 0.75) with a legal tokenizer that keeps references such as
  `section 482` and `article 21` as single tokens.
- **Dense**: either an in-process sentence-transformer (`EMBEDDING_PROVIDER=local`) or an
  OpenAI-compatible embeddings API (`EMBEDDING_PROVIDER=openai`, built in the background and stored
  in the database). Local mode uses sentence-transformer embeddings, L2-normalized, exact FAISS inner-product search
  (NumPy fallback). Embeddings are cached in `INDEX_DIR` keyed by model + chunk fingerprint, so
  restarts reuse them and any corpus change triggers a rebuild. Load failures are reported as
  `failed` with the reason; nothing falls back silently.
- **Hybrid**: reciprocal-rank fusion (default, `k = 60`) or min–max weighted fusion
  (`HYBRID_ALPHA` = dense share) over each engine's top `3k` candidates.
- **Search API**: retrieves a candidate pool, applies filters (document type, court, judgment
  year), optionally keeps one passage per document, sorts, and paginates. When filters shrink
  the pool, it is widened (up to 6,400 chunks) before a short page is returned.

## Grounded QA

question → retrieval → passage selection (top 5, at most 2 per document) → query-focused passage
windows in a numbered prompt → generation → citation normalization and audit → response.
Answers that cite non-existent passages or cite nothing are withheld; "insufficient evidence"
replies are reported as such. An optional trailing `Interpretation:` section is returned
separately and labelled as not directly sourced.

## Persistence

| Data | Store | Survives redeploys on Render |
|---|---|---|
| Users, sessions revoked, uploads (bytes + text), experiments, usage, feedback | PostgreSQL (SQLite locally) | Yes (managed database) |
| Corpus documents/chunks, ingestion report, AILA benchmark | Baked into the API image at build time | Rebuilt reproducibly from the checksummed source |
| Dense vectors, local provider | `INDEX_DIR` (.npy cache) | No on ephemeral disks; rebuilt on first dense use or via `scripts/build_dense_index.py` |
| Dense vectors, API provider | PostgreSQL `embedding_batches` (float16) | Yes; built once in the background, resumable |
