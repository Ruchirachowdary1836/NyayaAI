FROM python:3.11-slim

WORKDIR /workspace

COPY pyproject.toml ./
COPY README.md ./
COPY backend ./backend
COPY evaluation ./evaluation
COPY configs/render-data.yaml ./configs/render-data.yaml
COPY scripts ./scripts

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e . && \
    python scripts/fetch_aila_corpus.py \
      --output data/raw/aila_corpus.jsonl \
      --evaluation-output-dir data/processed/aila_evaluation && \
    python -m backend.app.services.ingestion.cli --config configs/render-data.yaml && \
    python -m evaluation.seed_aila_benchmark && \
    rm -f data/raw/aila_corpus.jsonl && \
    rmdir data/raw

EXPOSE 10000

CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
