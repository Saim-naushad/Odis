FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# procps provides pgrep, used by the container healthcheck below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY backend ./backend
COPY artifacts ./artifacts

RUN pip install ".[ml]"

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=20s \
    CMD pgrep -f "backend.simulator.inference_worker" >/dev/null || exit 1

CMD ["python", "-m", "backend.simulator.inference_worker"]
