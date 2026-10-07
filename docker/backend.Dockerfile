FROM python:3.11-slim

WORKDIR /workspace

COPY pyproject.toml ./
COPY README.md ./
COPY backend ./backend
COPY configs/render-data.yaml ./configs/render-data.yaml
COPY scripts/fetch_aila_corpus.py ./scripts/fetch_aila_corpus.py

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e . && \
    python scripts/fetch_aila_corpus.py --output data/raw/aila_corpus.jsonl && \
    python -m backend.app.services.ingestion.cli --config configs/render-data.yaml && \
    rm -f data/raw/aila_corpus.jsonl && \
    rmdir data/raw

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
