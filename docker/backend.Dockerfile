FROM python:3.11-slim

# Optional dependency groups, e.g. --build-arg EXTRAS=dense to enable dense/hybrid retrieval.
ARG EXTRAS=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY pyproject.toml README.md alembic.ini ./
COPY backend ./backend
COPY evaluation ./evaluation
COPY configs/render-data.yaml ./configs/render-data.yaml
COPY scripts ./scripts

# The AILA 2019 corpus (CC BY 4.0) is fetched with checksum verification, normalized,
# chunked, and baked into the image so the index never depends on an ephemeral disk.
RUN pip install --upgrade pip && \
    if [ -n "$EXTRAS" ]; then pip install -e ".[$EXTRAS]"; else pip install -e .; fi && \
    python scripts/fetch_aila_corpus.py \
      --output data/raw/aila_corpus.jsonl \
      --evaluation-output-dir data/processed/aila_evaluation && \
    python -m backend.app.services.ingestion.cli --config configs/render-data.yaml && \
    python -m evaluation.seed_aila_benchmark && \
    rm -f data/raw/aila_corpus.jsonl && \
    rmdir data/raw && \
    useradd --create-home --uid 10001 nyaya && \
    mkdir -p data/indices && chown -R nyaya:nyaya data evaluation/results

USER nyaya

EXPOSE 10000

# Database migrations run automatically at startup (idempotent Alembic upgrade to head).
# --proxy-headers makes rate limits use the real client IP behind Render's proxy.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
