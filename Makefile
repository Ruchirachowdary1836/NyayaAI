.PHONY: setup install lint test format docker-up docker-down experiment ingest

PYTHON ?= python
PIP ?= $(PYTHON) -m pip

setup:
	$(PYTHON) -m venv .venv
	. .venv/Scripts/activate && $(PIP) install --upgrade pip setuptools wheel
	. .venv/Scripts/activate && $(PIP) install -e .
	cd frontend && npm install

install:
	. .venv/Scripts/activate && $(PIP) install -e .
	cd frontend && npm install

lint:
	. .venv/Scripts/activate && ruff check backend/app
	cd frontend && npm run build

test:
	. .venv/Scripts/activate && pytest -q
	cd frontend && npm test -- --run

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v

experiment:
	$(PYTHON) -m evaluation.run_experiment --config configs/experiment.yaml

ingest:
	$(PYTHON) -m backend.app.services.ingestion.cli --config configs/data.yaml
