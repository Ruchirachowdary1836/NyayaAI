# API reference

Interactive OpenAPI documentation is served at `/docs` (Swagger UI) and `/redoc`; the schema is at
`/openapi.json`.

## Conventions

- Base path: `/api/v1`. Every route below except `auth/register` and `auth/token` requires
  `Authorization: Bearer <access_token>`.
- Errors return `{"detail": ...}`. Validation errors (HTTP 422) return FastAPI's list of
  `{loc, msg}` items. Unexpected errors return HTTP 500 with a generic message and `request_id`.
- Every response carries `X-Request-ID` (a valid client-supplied ID is echoed back).
- Status codes: 401 missing/invalid/expired/revoked token · 403 insufficient role · 404 missing
  or not owned (private resources never reveal existence) · 409 conflict · 413 upload too large ·
  422 validation · 429 rate limited (`Retry-After`) · 502/503/504 dependency failure.

## Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness; available during startup. |
| GET | `/ready` | Readiness: `status`, `database`, corpus counts, `available_retrievers`, per-engine `retrievers` state (`ready`, `not_loaded`, `loading`, `building` with `progress`, `failed` with `retrying`, `disabled`), generation provider/model/configured. 503 while initializing or if the database is unreachable. |

## Authentication

| Method | Path | Body / notes |
|---|---|---|
| POST | `/auth/register` | `{username, password}`; username `[A-Za-z0-9_.-]{3,80}`, password ≥ 8. Returns a token (201). Rate limited per IP. |
| POST | `/auth/token` | `{username, password}` → `{access_token, token_type, role, username, expires_in}`. Rate limited per IP. |
| POST | `/auth/logout` | Revokes the presented token (204). |
| GET | `/auth/me` | Profile: username, role, is_active, created_at, last_login_at. |
| PUT | `/auth/me` | `{current_password, username, new_password?}`; returns a new token. A password change signs out all other sessions. |

## Research

| Method | Path | Description |
|---|---|---|
| GET | `/dashboard` | The caller's library/experiment counts, recent items, 30-day activity, corpus and engine status. |
| POST | `/search` | `{query, retriever: bm25\|dense\|hybrid, k (page size ≤ 50), page ≤ 10, document_type?, court?, year_from?, year_to?, group_by_document=true, sort: relevance\|newest\|oldest\|title\|document}` → hits with `title`, `excerpt`, full passage `text`, scores, metadata; `total`, `total_is_capped`, `latency_ms`. |
| POST | `/compare` | `{query, k ≤ 20, retrievers?}` → per-engine top-k documents (best passage each) and latency, Jaccard document overlap, and `unavailable` engines with reasons. |
| POST | `/qa` | `{query, retriever, k ≤ 20, query_type}` → `answer`, `citations`, `invalid_citations`, `unsupported_sentences`, `interpretation`, `passages` (with doc IDs/titles/metadata), `confidence`, `refused`, `refusal_reason` (`no_evidence`, `insufficient_evidence`, `invalid_citations`, `uncited_answer`), `disclaimer`, `model`, `provider`. Rate limited per user. |
| POST | `/qa/stream` | Same body; server-sent events `token`, then `complete` (audited payload), `refusal`, or `error`. The question is sent in the body, never the URL. |
| POST | `/feedback` | `{query, rating: up\|down, correctness?, comment?}`. |

## Corpus

| Method | Path | Description |
|---|---|---|
| GET | `/documents` | `q`, `document_type`, `court`, `sort=id\|title`, `limit ≤ 100`, `offset` → summaries and `facets`. |
| GET | `/documents/{doc_id}` | Full text, metadata (court, judgment date, case number, source, licence), and chunk offsets. |

## Private document library

| Method | Path | Description |
|---|---|---|
| POST | `/library/documents` | Multipart `file` (PDF, TXT, MD; ≤ 5 MB) and optional `title`. Content is validated and text extracted; `status` is `ready` or `failed` with `error`. Duplicate files → 409. |
| GET | `/library/documents` | Caller's documents; `q`, `status`, `limit`, `offset`. |
| GET | `/library/documents/{id}` | Metadata and extracted text. |
| GET | `/library/documents/{id}/download` | Original bytes as an attachment. |
| DELETE | `/library/documents/{id}` | Permanently deletes the document (204). |
| POST | `/library/search` | `{query, k}` → BM25 matches within the caller's ready documents. |

## Experiments

| Method | Path | Description |
|---|---|---|
| POST | `/experiments/runs` | `{name, retrievers[], k ≤ 50, queries: [{query ≤ 8,000 chars, relevant_doc_ids[]}]}` (≤ 25 queries). Runs real searches, stores document rankings, latency, and — for judged queries — precision/recall@k, MAP, MRR, nDCG@10. |
| GET | `/experiments/runs` | Caller's runs (paginated). |
| GET/DELETE | `/experiments/runs/{id}` | Full results / delete. |
| GET | `/experiments/benchmarks` | Offline benchmark runs from `evaluation/results` (e.g. the AILA 2019 BM25 baseline). |
| GET | `/experiments/benchmarks/{run_id}` | One benchmark run. |

## Administration (admin role)

| Method | Path | Description |
|---|---|---|
| GET | `/admin/overview` | Users, uploads, experiments, feedback, anonymized usage (24 h / 7 d), engine state, ingestion report, database/schema/provider status. |
| GET | `/admin/users` | `q`, `limit`, `offset`. |
| PATCH | `/admin/users/{username}` | `{role?, is_active?}`. Admins cannot demote or disable themselves, and the last active admin cannot be removed. Changes end the user's existing sessions. |
