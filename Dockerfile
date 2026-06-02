# =============================================================================
# Nexus-Debug — Multi-stage Docker build
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .

# Generate frozen requirements from pyproject.toml (production only — pas de pytest/ruff dans l'image)
RUN pip install --no-cache-dir pip && \
    pip install --no-cache-dir "." && \
    pip freeze | grep -v nexus-debug > /build/requirements-frozen.txt


# ── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Dépendances système légères
# gosu: alternative légère à sudo pour le user-switch
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSL "https://github.com/tianon/gosu/releases/download/1.17/gosu-$(dpkg --print-architecture)" -o /usr/local/bin/gosu \
    && chmod +x /usr/local/bin/gosu

# Python dependencies (frozen)
COPY --from=builder /build/requirements-frozen.txt .
RUN pip install --no-cache-dir -r requirements-frozen.txt

# App
COPY . .

# Créer user non-root (reste root pour permettre le chown des volumes)
RUN useradd -m nexus && mkdir -p /data/nexus && chown -R nexus:nexus /app
# NE PAS faire USER nexus — on reste root pour corriger les permissions des volumes au démarrage
# USER nexus

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

CMD chown -R nexus:nexus /data/nexus 2>/dev/null; exec gosu nexus uvicorn nexus_api:app --host 0.0.0.0 --port 9001 --log-level info
