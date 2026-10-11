.PHONY: setup install fetch-data ingest dense-index migrate api web lint test experiment docker-up docker-down

# On Windows the virtualenv uses Scripts/; elsewhere bin/.
VENV_BIN ?= $(if $(wildcard .venv/Scripts),.venv/Scripts,.venv/bin)
PY := $(VENV_BIN)/python

setup:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	npm --prefix frontend ci

install:
	$(PY) -m pip install -e ".[dev]"
	npm --prefix frontend ci

fetch-data:
	$(PY) scripts/fetch_aila_corpus.py --output data/raw/aila_corpus.jsonl --evaluation-output-dir data/processed/aila_evaluation

ingest:
	$(PY) -m backend.app.services.ingestion.cli --config configs/render-data.yaml
	$(PY) -m evaluation.seed_aila_benchmark

dense-index:
	$(PY) scripts/build_dense_index.py

migrate:
	$(VENV_BIN)/alembic upgrade head

api:
	$(PY) -m uvicorn backend.app.main:app --reload --port 8000

web:
	npm --prefix frontend run dev

lint:
	$(PY) -m ruff check backend/app backend/tests evaluation scripts
	$(PY) -m ruff format --check backend/app backend/tests evaluation scripts

test:
	$(PY) -m pytest -q
	npm --prefix frontend test
	npm --prefix frontend run build

experiment:
	$(PY) -m evaluation.run_experiment --config configs/experiment.yaml

docker-up:
	docker compose up --build

docker-down:
	docker compose down
