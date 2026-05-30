# Changelog

## 2.2.0 (2026-05-30) — Monitoring Stack 📊

### 📈 Monitoring
- Prometheus service avec scrape config (scrape nexus:9001/metrics toutes les 10s)
- Grafana service (auto-provisioning dashboard + datasource)
- Dashboard 10 panneaux : requêtes HTTP (rate, endpoint, status), tâches, durée p50/p90/p99, heatmap, KB
- Accès : Grafana http://localhost:3000 — `admin / nexus2026`
- Rétention Prometheus : 30 jours

### 📖 Documentation
- Badge CI workflow dans README
- Section Monitoring dans README (tableau des services)
- Architecture projet : docker/prometheus/ + docker/grafana/

## 2.1.0 (2026-05-27) — Refonte Pro

### 🐳 Infra
- Dockerfile multi-stage + docker-compose.yml (1 commande pour lancer)
- .dockerignore propre
- .env.example avec toutes les variables documentées
- Makefile (make test, make lint, make run, make docker-up)
- CI/CD complet : GitHub Actions (lint + typecheck + test + Docker)

### 🛠️ Qualité
- pyproject.toml (remplace requirements.txt — tout centralisé)
- Ruff (lint + format auto) + pre-commit hooks
- mypy (type hints stricts)
- badges CI prêts (build / coverage / python)

### 🔐 Sécurité
- API Key auth middleware (Bearer token optionnel)
- Rate limiting (slowapi, 10 requêtes/min par défaut)
- Validation Pydantic renforcée (patterns regex, max_length)
- CORS verrouillé (origine configurable)

### 📊 Observabilité
- loguru remplace tous les print() — logs structurés
- Rotation des logs (10 MB, rétention 3-7 jours)
- Healthcheck enrichi (DB, webhooks, auth status)

### 💾 Persistance
- SQLite (aiosqlite) pour le tasks_store — plus de perte au redémarrage
- Migration automatique des tables au démarrage
- Index sur status pour requêtes rapides

### 🧪 Tests
- 27 tests (vs 17 avant) — coverage API, webhooks, KB, outils
- Tests nominaux + edge cases (p0 crash, non-bug, validation)
- Format asyncio standard

### 🔧 Autres
- timeout sur tous les subprocess (anti-bloquage)
- Limite de taille sur les briefs (anti-DoS)
- Logging d'erreur enrichi (avertissement si DEEPSEEK_API_KEY manquante)

## 2.0.0 (2026-05-26) — Switch DeepSeek + API REST
- Switch Anthropic → DeepSeek V4 Pro
- FastAPI REST endpoints
- Webhooks GitHub/Jira + Slack
- KB YAML + improve_agents
- nexus-debug v2 complet

## 1.0.0 (2026-05-25) — Création
- Première version xalil-debug → nexus-debug
- Pipeline agentique ReAct + LangGraph
- 8 sous-agents outils
