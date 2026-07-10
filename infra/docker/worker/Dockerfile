FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 procps \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY backend ./backend

RUN pip install .

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=20s \
    CMD pgrep -f "backend.app.worker_main" >/dev/null || exit 1

CMD ["python", "-m", "backend.app.worker_main"]
