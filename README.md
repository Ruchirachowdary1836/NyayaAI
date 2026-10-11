# NyayaAI

NyayaAI is an evidence-first research platform for Indian case law and statutes. Researchers
sign in, search judgments with BM25, dense, or hybrid retrieval, compare those engines side by
side, ask questions that are answered only from cited source passages, keep a private library of
their own documents, and run reproducible retrieval experiments.

**Research use only.** NyayaAI is assistive and is not a substitute for professional legal advice.

## Contents

- [Architecture](#architecture) · [Prerequisites](#prerequisites) · [Local setup](#local-setup)
- [Configuration](#configuration) · [Data and indexes](#data-and-indexes) · [AI provider](#ai-provider)
- [Testing](#testing) · [Deployment](#deploy-to-render) · [Troubleshooting](#troubleshooting)

## Architecture

| Part | Stack |
|---|---|
| Frontend (`frontend/`) | React 18, TypeScript, Vite, TanStack Query, React Router, Recharts |
| API (`backend/app/`) | FastAPI, Pydantic v2, SQLAlchemy 2 Core, Alembic, PyJWT |
| Retrieval | Okapi BM25 (built in), sentence-transformers + FAISS (optional `dense` extra), RRF/weighted fusion |
| Generation | Ollama locally, or any OpenAI-compatible chat-completions API |
| Database | SQLite for local development, PostgreSQL in Compose and production |
| Corpus | AILA 2019 cases and statutes (CC BY 4.0), fetched with checksum verification |

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), design decisions:
[`docs/DECISIONS.md`](docs/DECISIONS.md), API: [`docs/API.md`](docs/API.md) and `/docs` on a running API.

### Pages

Landing · Sign in / Create account · Dashboard · Search & ask (filters, sorting, pagination,
streamed grounded answers) · Compare engines · Experiments (create, history, detail, AILA
benchmark) · Legal corpus browser and judgment viewer · My documents (upload, search, view,
download, delete) · Profile & security · Administration (health, ingestion, usage, user
management) · Not found.

## Prerequisites

- Python 3.11 or 3.12
- Node.js 20+ and npm
- About 400 MB of disk for the processed corpus; ~2 GB more for the optional dense extra (PyTorch)
- Optional: [Ollama](https://ollama.com) for local answer generation, Docker for Compose

## Local setup

Commands are shown for PowerShell on Windows; on macOS/Linux use `.venv/bin/` instead of
`.venv\Scripts\`.

```powershell
git clone https://github.com/Ruchirachowdary1836/NyayaAI.git
cd NyayaAI
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"          # add ,dense for dense/hybrid retrieval
npm --prefix frontend ci
Copy-Item .env.example .env
```

Edit `.env`: set `JWT_SECRET_KEY` (any long random string), and optionally
`INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` (≥ 12 characters) to create an administrator
on first start.

Fetch and index the corpus (downloads the AILA archive from Zenodo, verifies its checksum, and writes
`data/processed/`):

```powershell
.venv\Scripts\python scripts\fetch_aila_corpus.py --output data\raw\aila_corpus.jsonl --evaluation-output-dir data\processed\aila_evaluation
.venv\Scripts\python -m backend.app.services.ingestion.cli --config configs\render-data.yaml
.venv\Scripts\python -m evaluation.seed_aila_benchmark
```

Start the API (migrations run automatically on startup):

```powershell
.venv\Scripts\python -m uvicorn backend.app.main:app --reload --port 8000
```

Start the web app in a second terminal. If the API is not on port 8000, create
`frontend/.env.local` containing `VITE_API_BASE_URL=http://127.0.0.1:<port>`.

```powershell
npm --prefix frontend run dev
```

Open http://localhost:5173, create an account, and start searching. The API reference is at
http://localhost:8000/docs.

With `make` available, `make setup`, `make fetch-data`, `make ingest`, `make api`, and `make web`
do the same.

### Docker Compose

```powershell
docker compose up --build
```

This starts PostgreSQL, the API (corpus baked into the image), the Vite dev server, and Ollama.
Pull a model once with `docker compose exec ollama ollama pull llama3.1:8b`. Build with dense
support via `$env:BACKEND_EXTRAS="dense"; docker compose up --build`.

## Configuration

All settings are environment variables (or `.env`); see [`.env.example`](.env.example) for the
full list with comments.

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `production` enables startup safety checks | `development` |
| `DATABASE_URL` | SQLAlchemy URL; `postgres://` URLs are accepted | `sqlite:///data/processed/nyayaai.db` |
| `JWT_SECRET_KEY` | Token signing key (≥ 32 chars in production) | insecure placeholder |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Session length | `60` |
| `INITIAL_ADMIN_USERNAME` / `_PASSWORD` | Bootstrap administrator | empty |
| `CORS_ORIGINS` | JSON list of allowed web origins | local Vite origins |
| `ENABLED_RETRIEVERS` | JSON list from `bm25`, `dense`, `hybrid` | `["bm25"]` |
| `EMBEDDING_MODEL` | Sentence-transformer for dense retrieval | `BAAI/bge-m3` (set a smaller model such as `sentence-transformers/all-MiniLM-L6-v2` on modest hardware) |
| `HYBRID_METHOD`, `HYBRID_ALPHA`, `HYBRID_RRF_K` | Fusion strategy | `rrf`, `0.7`, `60` |
| `GENERATOR_PROVIDER` | `ollama` or `openai` | `ollama` |
| `GENERATOR_MODEL`, `GENERATOR_API_KEY`, `GENERATOR_API_BASE_URL`, `OLLAMA_BASE_URL` | Provider settings (server-side only) | see `.env.example` |
| `GENERATOR_TIMEOUT_SECONDS`, `QA_PASSAGE_CHARS` | Generation timeout, prompt passage window | `120`, `1200` |
| `RATE_LIMIT_PER_MINUTE`, `AUTH_RATE_LIMIT_PER_MINUTE`, `QA_RATE_LIMIT_PER_MINUTE` | Limits | `120`, `10`, `10` |
| `UPLOAD_MAX_BYTES`, `UPLOAD_MAX_DOCUMENTS_PER_USER`, `EXPERIMENT_MAX_QUERIES` | Quotas | 5 MB, `200`, `25` |
| `VITE_API_BASE_URL` | API origin compiled into the frontend | `http://localhost:8000` |

## Database migrations

Migrations live in `backend/app/db/migrations` and run automatically at API startup. To run them
manually (for example before a deploy), with `DATABASE_URL` set:

```powershell
.venv\Scripts\alembic upgrade head
.venv\Scripts\alembic current
```

The baseline revision adopts databases created by earlier NyayaAI versions without changing data.
Downgrading below the baseline is refused because it would delete user data.

## Data and indexes

- **Ingestion** (`backend/app/services/ingestion`) loads JSON/JSONL/CSV, removes duplicate IDs and
  exact/near-duplicate texts, extracts judgment date and case number from each judgment's header,
  adds a SHA-256 checksum, chunks on paragraph boundaries, and writes `documents.jsonl`,
  `chunks.jsonl`, `corpus_statistics.json`, and `ingestion_report.json` (skipped/removed counts).
  Re-running it produces identical output. See [`data/README.md`](data/README.md) for accepted
  fields and [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) for licensing.
- **BM25** is rebuilt in memory from `chunks.jsonl` at startup (a few seconds).
- **Dense embeddings** are cached in `INDEX_DIR` under a key derived from the model and every chunk,
  and reused until either changes. Precompute them with
  `.venv\Scripts\python scripts\build_dense_index.py` (CPU: roughly an hour for the full corpus
  with MiniLM); otherwise they are built on the first dense/hybrid request.
- Only add datasets you are licensed to use and redistribute.

## AI provider

- **Local (Ollama):** install Ollama, `ollama pull llama3.1:8b` (or a smaller model such as
  `qwen2.5:3b`), and set `GENERATOR_PROVIDER=ollama`, `GENERATOR_MODEL=<model>`. CPU-only machines
  may need `GENERATOR_TIMEOUT_SECONDS=300`.
- **Hosted (OpenAI-compatible):** set `GENERATOR_PROVIDER=openai`, `GENERATOR_API_KEY`,
  `GENERATOR_MODEL`, and `GENERATOR_API_BASE_URL`.

Without a working provider, questions return an explicit configuration or provider error;
search, comparison, documents, and experiments keep working. Answers whose citations are invalid
or missing are withheld rather than shown.

## Testing

```powershell
.venv\Scripts\python -m pytest -q                       # backend + evaluation (SQLite)
.venv\Scripts\python -m ruff check backend/app backend/tests evaluation scripts
.venv\Scripts\python -m ruff format --check backend/app backend/tests evaluation scripts
npm --prefix frontend test                              # Vitest + Testing Library
npm --prefix frontend run build                         # type-check + production build
```

PostgreSQL repository tests run when `NYAYAAI_TEST_POSTGRES_URL` points to a disposable database
(CI provides one); never point it at real data. Tests use temporary databases and files only.

## Deploy to Render

[`render.yaml`](render.yaml) is a Render Blueprint: **New + → Blueprint**, connect the repository,
and deploy. It creates:

- `nyayaai-api` — Docker web service. The image fetches, verifies, and indexes the AILA corpus at
  build time, so the index never depends on Render's ephemeral disk. It binds to `$PORT`, runs
  migrations on startup, and uses `/health` as its health check.
- `nyayaai-web` — static site with SPA rewrites (nested routes survive refresh).
- `nyayaai-db` — managed PostgreSQL for users, uploads, experiments, and usage.

When prompted, set `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`, and set
`GENERATOR_API_KEY` on `nyayaai-api` to enable answers. `JWT_SECRET_KEY` is generated
automatically. Two values must match your actual service URLs: `CORS_ORIGINS` on the API (the web
origin) and `VITE_API_BASE_URL` on the static site (the API origin, which requires a rebuild when
changed).

The free plans have limits: the API sleeps when idle (the web app retries through cold starts),
512 MB memory restricts it to BM25, and free PostgreSQL instances expire — choose paid plans for
durable production data. Dense embeddings on an ephemeral disk are rebuilt after each deploy;
use a persistent disk mounted at `INDEX_DIR` if you enable dense retrieval.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Web app shows "Could not reach the NyayaAI API" | `VITE_API_BASE_URL` is wrong or the API is down; check `/health`. |
| Browser console shows CORS errors | Add the exact web origin to `CORS_ORIGINS` and restart the API. |
| API returns 503 "initializing" | Startup is still loading the corpus; `/ready` shows progress. |
| `/ready` reports `failed` | Read the API logs. In production, unsafe settings (default JWT secret, SQLite, wildcard CORS) or a missing corpus stop startup. |
| Search says no documents are indexed | Run the fetch and ingestion commands; check `DATA_CHUNKS_PATH`. |
| Dense/hybrid "unavailable" | Install `.[dense]`, ensure the model can download, and add the engine to `ENABLED_RETRIEVERS`. |
| Answers fail with a timeout | Increase `GENERATOR_TIMEOUT_SECONDS` or use a faster model/provider. |
| Answers are withheld | The model cited nothing or a non-existent passage; review the listed passages or use a stronger model. |
| Admin account missing | `INITIAL_ADMIN_PASSWORD` must be ≥ 12 characters; the account is only created if the username is new. |

## Known limitations

See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md): the corpus is a research snapshot, filters act
on a ranked candidate pool, rate limits are per process, citation audits check structure rather
than meaning, and OCR is not performed on scanned PDFs.

## Licence and attribution

Code: see [`LICENSE`](LICENSE). Corpus: AILA 2019 Precedent & Statute Retrieval Task by Paheli
Bhattacharya, Kripabandhu Ghosh, Saptarshi Ghosh, Arindam Pal, Parth Mehta, Arnab Bhattacharya,
and Prasenjit Majumder ([CC BY 4.0](https://doi.org/10.5281/zenodo.4063986)).
