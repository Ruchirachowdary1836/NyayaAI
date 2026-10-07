# API reference

The FastAPI service publishes its interactive OpenAPI reference at `/docs` and its schema at `/openapi.json`.

## Research

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/search` | Search with `bm25`, `dense`, or `hybrid`; returns passage text, rank, and source scores. |
| `POST` | `/api/v1/compare` | Run one query through all three retrievers and report document-set overlap. |
| `POST` | `/api/v1/qa` | Answer from retrieved passages; always returns citations, audit flags, confidence, and disclaimer. |
| `GET` | `/api/v1/qa/stream` | Stream generated tokens via SSE (`token`, `complete`, `refusal`, or `error` events). |
| `GET` | `/api/v1/documents` | List indexed document metadata and short excerpts. |
| `GET` | `/api/v1/documents/{document_id}` | Fetch the full document and its chunk offsets. |
| `GET` | `/api/v1/experiments` | List completed runs in `evaluation/results/`. |
| `GET` | `/api/v1/experiments/{run_id}` | Read metrics for one validated run ID. |
| `POST` | `/api/v1/feedback` | Record an optional correctness score and helpfulness rating. |

Search and QA bodies contain `query`, a retriever name, and `k`. QA also accepts `query_type`: `auto`, `statute_lookup`, `conceptual`, or `fact_pattern`. Invalid inputs return standard FastAPI validation responses. Dense and hybrid retrieval require the configured sentence-transformer model. Local QA uses Ollama; Render QA uses the configured OpenAI-compatible provider. Render requires `GENERATOR_API_KEY`; absent credentials or provider failures are surfaced, never replaced with mock answers.

## Authentication and administration

- `POST /api/v1/auth/register` accepts a username and password (minimum 8 characters) and creates a `user` account.
- `POST /api/v1/auth/token` exchanges JSON username/password credentials for a signed JWT bearer token.
- `GET /api/v1/auth/me` returns the authenticated username and role.
- `PUT /api/v1/auth/me` updates the username and/or password after confirming the current password. It returns a replacement JWT and invalidates the old username-bound token.
- `GET /api/v1/admin/overview` and `GET /api/v1/admin/users` require the `admin` role.
- Bootstrap an initial administrator using `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD` before the backend's first start. The initial account is created only if that username does not already exist.
- Passwords are salted and hashed with PBKDF2-HMAC-SHA256. Use a unique high-entropy `JWT_SECRET_KEY` outside local development.

Every request receives an `X-Request-ID` response header. A process-local per-client sliding-window limiter defaults to 120 requests per minute and responds with HTTP 429 when exceeded. CORS is restricted to local Vite origins by default. In Compose, PostgreSQL stores accounts and feedback; direct local development defaults to SQLite. The single-process limiter is for local research; deploy behind production identity and a shared limiter for multi-instance use.

All QA payloads include the assistive-use disclaimer. Unsupported and invalid model citations are explicitly reported; answers containing nonexistent passage indices are withheld.
