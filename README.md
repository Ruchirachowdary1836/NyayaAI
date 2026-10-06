# NyayaAI

NyayaAI is a research-grade legal retrieval and question-answering system for Indian case law and statutes. The project compares BM25, dense retrieval, and hybrid retrieval in a controlled evaluation harness, then serves the best candidate through a retrieval-augmented generation pipeline with explicit source attribution.

## Phase 0 status

This repository is scoped for Phase 0: repository scaffolding, tooling, Docker orchestration, CI, configuration, and decision records. The core retriever, evaluation, RAG, and UI work continue in later phases.

## Quick start

```bash
make setup
make docker-up
```

Then visit:

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- MLflow UI: http://localhost:5000

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
