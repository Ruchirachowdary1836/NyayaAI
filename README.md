# NyayaAI

NyayaAI is an evidence-first research system for retrieval and question answering over Indian legal documents. It compares lexical BM25, sentence-embedding dense retrieval, and hybrid fusion; generated answers cite the retrieved passages and show their provenance.

**Research use only.** NyayaAI is assistive and is not a substitute for professional legal advice. The repository does not include licensed case-law datasets or model weights.

## Start the local stack

Requirements: Docker Desktop with Compose, and a machine with enough disk space for the backend ML dependencies and any local language/embedding models you choose.

```powershell
Copy-Item .env.example .env
```

Before starting, set a unique `JWT_SECRET_KEY`, `INITIAL_ADMIN_USERNAME`, and `INITIAL_ADMIN_PASSWORD` in `.env`. The bootstrap administrator is created only on first startup if that username does not already exist.

```powershell
docker compose up --build
```

Open [the web app](http://localhost:5173), [the API reference](http://localhost:8000/docs), or [MLflow](http://localhost:5000). To enable local answer generation, download the configured model after the services start:

```powershell
docker compose exec ollama ollama pull llama3.1:8b
```

BM25 search works without an LLM. Dense or hybrid search loads the configured sentence-transformer model on its first use and may require a substantial model download. QA reports an explicit error if Ollama or its model is not available; it does not switch to an ungrounded fallback.

The application starts with an empty index. Search and comparison return honest empty states until you add a legally authorized corpus.

## Deploy to Render

The repository includes [`render.yaml`](render.yaml) as a Render Blueprint. In Render, choose **New + → Blueprint**, connect this repository, and deploy the `main` branch. The Blueprint creates a static frontend, Docker-based API, and PostgreSQL database. Set `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD` when prompted; `JWT_SECRET_KEY` is generated automatically.

The API image fetches and indexes the AILA 2019 precedent-and-statute corpus at build time, verifying the Zenodo archive checksum. It also extracts the dataset's official 50 queries and relevance judgments for both retrieval tasks, then records an actual BM25 baseline in the experiment dashboard. The source dataset and benchmark are CC BY 4.0; see [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) for attribution and limitations. At runtime, the API binds its port before building the BM25 index and connecting to the database in the background; `/health` reports liveness, `/ready` reports initialization progress and enabled retrieval engines, and API operations return HTTP 503 until initialization completes. BM25 is the enabled Render search engine and needs no language model. Dense/hybrid retrieval download and apply an embedding model to the full corpus on first use, which exceeded the free instance's memory/latency budget during live testing; those engines are disabled in the Render Blueprint to prevent API restarts. They remain available in local deployments and can be enabled by setting `ENABLED_RETRIEVERS` after providing adequate resources. Grounded QA uses the configured OpenAI-compatible provider on Render; set `GENERATOR_API_KEY` in the `nyayaai-api` service's environment settings to a valid provider key. The Blueprint does not contain or generate an AI provider credential. Requests fail explicitly until a key is configured; no mock answer is returned. Direct local development continues to use Ollama by default.

The Blueprint uses Render's free plans where supported to avoid automatic charges. Free web services can spin down when idle, and free PostgreSQL has limited lifetime/storage; choose an appropriate paid plan for persistent production use. The API image binds to Render's assigned `PORT` (falling back to port 10000 for local container runs). The AILA archive is fetched during image builds and the resulting index is included in the API image, so it does not depend on an ephemeral service disk. The Render Blueprint enables BM25 only; dense and hybrid are not initialized or exposed on the free API instance. The frontend reads enabled engines from `/ready`, so it doesn't offer retrieval methods the deployment cannot run. The frontend's `VITE_API_BASE_URL` must match the API service's actual public URL. The current Render API hostname is configured directly in the Blueprint; if Render assigns a different host later, update that value and redeploy the static site. Do not add restricted legal data without authorization.

## Ingest authorized data

Raw sources, normalized documents, chunks, model files, and local database files are excluded from git. Place permitted JSON, JSONL, or CSV inputs under `data/raw/` and configure `configs/data.yaml`. Supported source modes are `aila`, `ildc`, and `legal_qa`; see [`data/README.md`](data/README.md) for the normalized input fields.

With Python 3.11 installed:

```powershell
py -3.11 -m pip install -e .
py -3.11 -m backend.app.services.ingestion.cli --config configs/data.yaml
```

Ingestion cleans text, removes near-duplicate judgments, chunks on token and paragraph boundaries, preserves parent IDs and character offsets, and writes local JSONL plus corpus statistics. Check upstream license and attribution terms before download, processing, or redistribution. The pipeline does not fetch datasets automatically.

## Run the retrieval experiment

The Render image includes an official AILA 2019 BM25 baseline computed from relevance judgments. For additional local experiments, configure query and qrels inputs in `configs/experiment.yaml`, then run:

```powershell
py -3.11 -m evaluation.run_experiment --config configs/experiment.yaml
```

The experiment compares BM25, dense, and RRF/weighted hybrid retrieval on the same queries, writes per-query and summary metrics, and computes paired significance tests and bootstrap confidence intervals. Results are read by the experiments dashboard. The precomputed Render baseline reports BM25 only; dense and hybrid metrics appear only after a real experiment evaluates those systems.

## Develop and test

```powershell
py -3.11 -m pytest -q
py -3.11 -m ruff check backend/app backend/tests evaluation
py -3.11 -m ruff format --check backend/app backend/tests evaluation
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend test
```

The Vite development server is included in Compose; for local-only frontend work, run `npm --prefix frontend run dev`. Backend Python dependencies are pinned in `pyproject.toml`, and the frontend lockfile is `frontend/package-lock.json`.

## Product areas

- **Research workspace:** deployment-enabled retrieval, highlighted matches, source score details, evidence panel, grounded QA, streamed answers, citation audits, and feedback.
- **Engine comparison:** side-by-side rankings and document-set overlap when multiple engines are enabled.
- **Source library:** searchable index metadata, full document view, and exact chunk offsets.
- **Experiments:** MAP/MRR/nDCG and precision charts from recorded runs, with significance and reproducibility metadata.
- **Administration:** health checks, JWT user/admin roles, corpus readiness, and access-controlled user listing.
- **Future extensions:** explicitly non-functional roadmap cards outside the core research scope.

## Architecture and decisions

- React 18, TypeScript, Vite, Tailwind, React Router, TanStack Query, Framer Motion, and Recharts frontend.
- FastAPI/Pydantic backend; retrieval code is framework-independent and generators use a local Ollama endpoint.
- Data/config inputs and retrieval fusion settings are tracked in `configs/`; local legal text and database files stay out of git.
- Auth and feedback use PostgreSQL in Compose and SQLite in direct local development. The in-process rate limiter is intended for single-instance local research only.
- Full experiment protocol and API contract: [`docs/EVALUATION.md`](docs/EVALUATION.md), [`docs/API.md`](docs/API.md), and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

See [`docs/DECISIONS.md`](docs/DECISIONS.md) for recorded design choices and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the service layout.
