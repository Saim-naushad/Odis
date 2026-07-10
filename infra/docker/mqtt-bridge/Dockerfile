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

RUN pip install .

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=20s \
    CMD pgrep -f "backend.mqtt_bridge" >/dev/null || exit 1

CMD ["python", "-m", "backend.mqtt_bridge"]
