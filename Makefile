# =============================================================================
# Nexus-Debug — Makefile
# =============================================================================
.PHONY: install dev lint format typecheck test test-cov run docker-build docker-up clean

# ── Installation ──────────────────────────────────────────────────────────────
install:
	pip install -e ".[dev]"

dev:
	pip install -e ".[dev]"

# ── Qualité ───────────────────────────────────────────────────────────────────
lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy nexus_*.py

precommit:
	pre-commit run --all-files

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ --cov=nexus --cov-report=term --cov-report=html

# ── Docker ────────────────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Run ───────────────────────────────────────────────────────────────────────
run:
	uvicorn nexus_api:app --host 0.0.0.0 --port 9001 --reload

run-agent:
	python nexus_orchestrator.py "$(BRIEF)"

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache
	rm -rf *.egg-info dist build
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
