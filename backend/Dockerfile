# ---- runtime image ---------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/opt/models/fastembed \
    TIKTOKEN_CACHE_DIR=/opt/models/tiktoken \
    HF_HUB_OFFLINE=0

# OCR for the scanned document uses RapidOCR (PP-OCR on ONNX Runtime); OpenCV-headless needs libglib.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Bake the embedding model + tokenizer into the image and warm up RapidOCR (no downloads at startup)
COPY scripts ./scripts
RUN python scripts/prefetch_models.py
ENV HF_HUB_OFFLINE=1

COPY app ./app
RUN mkdir -p /app/state /app/data

EXPOSE 8000
# Runs as root so it can write the bind-mounted ./data/veltrix.db whatever the host file owner is.
# Model-written code never runs as root: the Code Mode sandbox child drops to uid 65534.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]

# ---- test image: `docker compose --profile test run --rm tests` -------------------------------
FROM runtime AS test
RUN uv sync --frozen --no-install-project
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q"]
