# =============================================================================
# Nexus-Debug — Multi-stage Docker build
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .

# Generate frozen requirements from pyproject.toml
RUN pip install --no-cache-dir pip && \
    pip install --no-cache-dir ".[dev]" && \
    pip freeze --exclude-editable > /build/requirements-frozen.txt


# ── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Dépendances système légères
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (frozen)
COPY --from=builder /build/requirements-frozen.txt .
RUN pip install --no-cache-dir -r requirements-frozen.txt

# App
COPY . .

# Volumes persistants
VOLUME ["/data/nexus/kb", "/data/nexus/reports", "/data/nexus/feedback"]

EXPOSE 9001

ENV \
    NEXUS_KB_PATH=/data/nexus/kb/nexus_kb.yaml \
    NEXUS_REPORTS_DIR=/data/nexus/reports \
    NEXUS_FEEDBACK_PATH=/data/nexus/feedback/nexus_feedback.yaml \
    NEXUS_DB_PATH=/data/nexus/nexus.db \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:9001/health').raise_for_status()"

CMD ["uvicorn", "nexus_api:app", "--host", "0.0.0.0", "--port", "9001", "--log-level", "info"]
