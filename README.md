# NyayaAI

NyayaAI is a research-grade legal retrieval and question-answering system for Indian case law and statutes. The project compares BM25, dense retrieval, and hybrid retrieval in a controlled evaluation harness, then serves the best candidate through a retrieval-augmented generation pipeline with explicit source attribution.

## Phase 0 status

Phase 0 established the repository scaffold, tooling, Docker orchestration, CI, configuration, and decision records. Phase 1 adds license-conscious loaders, document cleaning, paragraph-aware chunking, corpus statistics, and an ingestion CLI. Retrieval, evaluation, RAG, and the complete UI continue in later phases.

## Quick start

```bash
make setup
make docker-up
```

Then visit:

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- MLflow UI: http://localhost:5000

## Ingesting a corpus

Place licensed or otherwise authorized source files under `data/raw/` (the directory is gitignored). Supported inputs are JSON, JSONL, and CSV. Set the `corpus` source and paths in `configs/data.yaml`, then run:

```bash
python -m backend.app.services.ingestion.cli --config configs/data.yaml
```

AILA expects a corpus file or directory containing supported files and optionally a queries file and qrels file. ILDC expects judgment records. `legal_qa` expects question/answer records and writes normalized QA examples without indexing answers as case documents. The adapters accept documented common field aliases; source-specific exports can be converted to these formats without changing the ingestion pipeline. Raw and derived corpus contents remain gitignored. Check dataset terms before downloading, processing, or redistributing any source.

## Repository structure

```text
nyayaai/
  README.md
  docker-compose.yml
  Makefile
  pyproject.toml
  docs/
  configs/
  data/
  backend/
  evaluation/
  frontend/
  .github/
```

## Core principles

- Only the retriever changes across experiments.
- Every answer must cite evidence from retrieved passages.
- Generated answers are assistive and must include a legal-use disclaimer.
- All experiments are reproducible with fixed seeds and pinned dependencies.

## Roadmap

- Phase 0: scaffold repo, tooling, Docker, CI, config system, decisions log.
- Phase 1: ingestion and chunking.
- Phase 2: BM25 baseline.
- Phase 3: dense retrieval.
- Phase 4: hybrid retrieval and ablations.
- Phase 5: legal QA with citation-backed generation.
- Phase 6: evaluation and statistics.
- Phase 7: API service and security.
- Phase 8: UI and end-to-end tests.
- Phase 9: polish, documentation, and paper skeleton.
