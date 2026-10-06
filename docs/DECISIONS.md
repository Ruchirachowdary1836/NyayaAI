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
