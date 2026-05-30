# Nexus-Debug v2 — Documentation Complète 🧬

> Système agentique de débogage (ReAct + LangGraph + DeepSeek V4 Pro)
> Version 2.0.0 — 30 Mai 2026

---

## Table des matières

1. [Présentation](#1-présentation)
2. [Architecture](#2-architecture)
3. [Installation](#3-installation)
4. [Usage](#4-usage)
5. [API REST](#5-api-rest)
6. [Webhooks](#6-webhooks)
7. [Base de connaissance](#7-base-de-connaissance)
8. [Outils MCP](#8-outils-mcp)
9. [Tests](#9-tests)
10. [Amélioration continue](#10-amélioration-continue)
12. [Dépannage](#12-dépannage)

---

## 1. Présentation

**Nexus-debug** est un système agentique de débogage qui utilise **ReAct (Reason + Act)** pour résoudre les bugs de façon autonome et intelligente. Contrairement aux pipelines fixes, Nexus décide lui-même de l'ordre des étapes, peut sauter des phases inutiles et boucler si nécessaire.

### Philosophie

| Principe | Description |
|---|---|
| **Agentique** | Nexus raisonne, décide, agit et observe — pas de procédure figée |
| **Économique** | Tourne sur DeepSeek V4 Pro (pas de surcoût Claude/GPT) |
| **Complet** | API REST + KB + MCP + Webhooks + Tests |
| **Autonome** | Résout les bugs du début à la fin sans intervention humaine |

### Prérequis

- Python ≥ 3.10
- Clé API DeepSeek (obtenir sur [platform.deepseek.com](https://platform.deepseek.com/api_keys))
- pip (gestionnaire de paquets Python)

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Orchestrateur (orchestrateur humain)       │
└────────────────────┬────────────────────────────────────┘
                     │ brief structuré
                     ▼
┌─────────────────────────────────────────────────────────┐
│              nexus_orchestrator.py                        │
│                                                          │
│   ┌─ Vérification KB ──► si match → solution directe    │
│   │                      (cache, pas d'appel LLM)        │
│   └─ Sinon → nexus_agent.py                              │
└──────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  nexus_agent.py — Cerveau ReAct (LangGraph + DeepSeek)  │
│                                                          │
│  Boucle : Thought → Action → Observation → Repeat        │
│                                                          │
│  ┌─ tool_triage           (1er appel obligatoire)        │
│  ├─ tool_static_analysis  (linters, AST, compilation)    │
│  ├─ tool_security_scan    (bandit, OWASP, CVE)           │
│  ├─ tool_runtime_debug    (stack trace, reproduction)    │
│  ├─ tool_perf_analysis    (bottlenecks, mémoire)         │
│  ├─ tool_fix_bug          (patch minimal)                │
│  ├─ tool_generate_tests   (pytest/jest)                  │
│  └─ tool_write_postmortem (KB update)                    │
└──────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              nexus_api.py — API REST (port 9001)         │
│                                                          │
│  POST /debug          → Soumettre un bug                 │
│  GET  /status/{id}    → Statut de la tâche               │
│  GET  /report/{id}    → Rapport final                    │
│  GET  /health         → Healthcheck                      │
│  POST /feedback       → Noter la qualité                 │
│  GET  /kb/search      → Recherche KB                     │
│  GET  /kb/stats       → Stats KB                         │
│  POST /webhook/github → Recevoir issues GitHub           │
│  POST /webhook/jira   → Recevoir tickets Jira            │
│  GET  /tasks          → Lister les tâches                │
└──────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           nexus_mcp_server.py — 7 outils MCP             │
│                                                          │
│  search_code    → ripgrep dans le code source            │
│  sandbox_execute→ exécution isolée (python/bash/node)   │
│  run_diagnostic → pytest/bandit/semgrep                  │
│  git_blame      → auteur + commit d'une ligne           │
│  kb_search      → recherche base de connaissance        │
│  kb_store       → stockage base de connaissance         │
│  get_sentry_event→ événement Sentry (placeholder)       │
└──────────────────────────────────────────────────────────┘
```

### Fichiers du projet

```
~/nexus-debug/
├── nexus_agent.py          ← Cerveau ReAct (LangGraph + DeepSeek V4 Pro)
├── nexus_tools.py          ← 8 sous-agents comme outils @tool
├── nexus_kb.py             ← Base de connaissance YAML
├── nexus_api.py            ← API REST FastAPI (port 9001)
├── nexus_orchestrator.py   ← Orchestrateur avec cache KB
├── nexus_mcp_server.py     ← 7 outils MCP (FastMCP)
├── nexus_state.py          ← Schémas Pydantic partagés
├── nexus_improve.py        ← Amélioration continue
├── orchestrateur_integration.py  ← Interface Orchestrateur → Nexus
├── requirements.txt        ← Dépendances Python
├── .gitignore              ← Fichiers ignorés
├── SKILL.md                ← Skill Hermes
├── README.md               ← Ce fichier
├── tests/
│   ├── test_agent.py       ← Tests de l'agent
│   ├── test_kb.py          ← Tests de la KB
│   ├── test_tools.py       ← Tests des outils
│   ├── test_api.py         ← Tests de l'API REST
│   └── test_improve.py     ← Tests de l'amélioration continue
└── docs/
    └── architecture.md     ← Diagramme d'architecture détaillé
```

---

## 3. Installation

### 3.1 Cloner et installer

```bash
# Depuis GitHub
git clone https://github.com/nexus05/nexus-debug.git
cd nexus-debug

# Ou depuis le répertoire local
cd ~/nexus-debug

# Créer le venv et installer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.2 Configuration

```bash
# Clé API DeepSeek (obligatoire)
export DEEPSEEK_API_KEY="sk-votre_clé_ici"

# Optionnel : modèle (défaut: deepseek-chat)
export NEXUS_MODEL="deepseek-chat"
# ou export NEXUS_MODEL="deepseek-v4-pro"

# Optionnel : port API (défaut: 9001)
export NEXUS_API_PORT="9001"

# Optionnel : webhooks (pour notifications)
export GITHUB_WEBHOOK_SECRET="votre_secret"
export GITHUB_TOKEN="ghp_votre_token"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

Pour une persistance, ajouter ces variables à `~/.hermes/.env` ou `~/.bashrc`.

### 3.3 Vérification

```bash
# Vérifier que tout fonctionne
source .venv/bin/activate
python -m pytest tests/ -v

# Lancer l'API
python nexus_api.py &
curl http://localhost:9001/health
# → {"status":"ok","version":"2.0.0","service":"nexus-debug",...}
```

---

## 4. Usage

### 4.1 CLI direct

```bash
cd ~/nexus-debug && source .venv/bin/activate
python nexus_agent.py "Erreur: TypeError dans src/main.py ligne 23, variable 'user' est None"
```

### 4.2 Via l'orchestrateur (recommandé)

```bash
cd ~/nexus-debug && source .venv/bin/activate

# L'orchestrateur vérifie d'abord la KB (cache)
python nexus_orchestrator.py "AttributeError sur user.id"
```

### 4.3 Via l'API REST

```bash
# Démarrer l'API
cd ~/nexus-debug && source .venv/bin/activate
python nexus_api.py &

# Soumettre un bug
curl -X POST http://localhost:9001/debug \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Erreur dans le module auth",
    "project": "bellissima-site",
    "langage": "typescript",
    "fichier": "src/lib/auth.ts",
    "erreur": "TypeError: Cannot read properties of undefined",
    "priority": "P1"
  }'
# → {"task_id":"a1b2c3d4","status":"en_attente"}

# Voir le résultat
curl http://localhost:9001/status/a1b2c3d4
curl http://localhost:9001/report/a1b2c3d4
```

### 4.4 Via Python (Orchestrateur)

```python
from nexus_orchestrator import orchestrer_nexus
import asyncio

result = asyncio.run(orchestrer_nexus(
    brief="PROJET: bellissima\nLANGAGE: Python\nFICHIER: src/app.py\nERREUR: AttributeError: 'NoneType' object has no attribute 'id'",
    mission_id="DBG-001"
))
print(result)
```

---

## 5. API REST

L'API REST est disponible sur le port **9001** (configurable via `NEXUS_API_PORT`).

### 5.1 Endpoints

| Méthode | Endpoint | Description | Corps (JSON) |
|---|---|---|---|
| `GET` | `/health` | Healthcheck | — |
| `POST` | `/debug` | Soumettre un bug | `{description, project?, langage?, fichier?, erreur?, stack?, priority?}` |
| `GET` | `/status/{task_id}` | Statut d'une tâche | — |
| `GET` | `/report/{task_id}` | Rapport complet | — |
| `GET` | `/tasks` | Lister les tâches | — |
| `POST` | `/feedback` | Noter la qualité | `{task_id, rating(1-5), comment?, corrected_by_human?}` |
| `GET` | `/kb/search?q=mot` | Recherche KB | — |
| `GET` | `/kb/stats` | Statistiques KB | — |
| `POST` | `/webhook/github` | Webhook GitHub | — |
| `POST` | `/webhook/jira` | Webhook Jira | — |

### 5.2 Réponse type

```json
{
  "task_id": "a1b2c3d4",
  "status": "termine",
  "brief": "PROJET : test\n...",
  "created_at": "2026-05-30T12:00:00",
  "completed_at": "2026-05-30T12:05:00",
  "result": {
    "mission_id": "DBG-A1B2C3D4",
    "status": "fixed",
    "root_cause": "user=None quand pas authentifié",
    "files_modified": ["src/auth/user.py"],
    "fix_summary": "Ajout guard check if user is not None",
    "confidence": 0.95,
    "tools_used": ["tool_triage", "tool_static_analysis", "tool_runtime_debug", "tool_fix_bug"],
    "needs_human": false
  }
}
```

### 5.3 Codes d'erreur

| Code | Signification |
|---|---|
| `202` | Bug accepté, en attente de traitement |
| `200` | Requête réussie |
| `404` | Tâche non trouvée |
| `422` | Données invalides |
| `403` | Signature webhook invalide |

---

## 6. Webhooks

### 6.1 GitHub

Configurez le webhook dans votre repo GitHub :
- **URL** : `http://votre-serveur:9001/webhook/github`
- **Content type** : `application/json`
- **Secret** : votre `GITHUB_WEBHOOK_SECRET` (optionnel mais recommandé)
- **Events** : Issues (`issues`)

Fonctionnement :
1. Une issue est ouverte avec le label `bug`
2. GitHub POSTe sur `/webhook/github`
3. Nexus analyse le bug et poste un commentaire sur l'issue
4. Notification Slack envoyée (si configuré)

### 6.2 Jira

Configurez un webhook dans Jira :
- **URL** : `http://votre-serveur:9001/webhook/jira`
- **Events** : Issue created, Issue updated

Fonctionnement :
1. Un ticket est créé avec le type "Bug"
2. Jira POSTe sur `/webhook/jira`
3. Nexus analyse et traite le bug

### 6.3 Slack

Configurez une app Slack avec un webhook entrant, puis :
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T00/B00/xxxxx"
```

Les notifications sont envoyées automatiquement à chaque :
- ✅ Bug résolu
- ❌ Erreur / exception
- 📄 Lien vers le rapport complet

---

## 7. Base de connaissance

La KB stocke les bugs résolus pour éviter de les retraiter.

### 7.1 Stockage

```python
from nexus_kb import kb_store

kb_store(
    bug_id="BUG-001",
    category="null_reference",
    summary="AttributeError NoneType dans user.py",
    root_cause="user=None quand non authentifié",
    solution="Ajouter guard check `if user is not None`",
    langage="python",
    keywords=["null", "user", "auth"],
)
```

### 7.2 Recherche

```python
from nexus_kb import kb_search

results = kb_search("null user auth")
# → {"status":"success", "results": [...], "count": 1}
```

### 7.3 API

```bash
curl "http://localhost:9001/kb/search?q=null+pointer"
curl http://localhost:9001/kb/stats
```

---

## 8. Outils MCP

7 outils exposés via MCP (Model Context Protocol), utilisables par Hermes et l'API.

### 8.1 Lancement

```bash
cd ~/nexus-debug && source .venv/bin/activate
python nexus_mcp_server.py
```

### 8.2 Outils disponibles

| Outil | Description | Paramètres |
|---|---|---|
| `search_code` | Recherche regex dans le code | `query`, `path?` |
| `sandbox_execute` | Exécution isolée Python/JS/Bash | `code`, `language`, `timeout?` |
| `run_diagnostic` | pytest/bandit/semgrep | `command`, `workdir?` |
| `git_blame` | Auteur + commit d'une ligne | `file`, `line` |
| `kb_search` | Recherche KB | `query` |
| `kb_store` | Stockage KB | `bug_id, category, summary, root_cause, solution` |
| `get_sentry_event` | Événement Sentry (placeholder) | `event_id` |

---

## 9. Tests

### 9.1 Lancement

```bash
cd ~/nexus-debug && source .venv/bin/activate
python -m pytest tests/ -v
```

### 9.2 Résultat attendu

```
collected 17 items

test_improve.py::test_analyze_feedback_empty      ✅
test_improve.py::test_analyze_feedback_with_data   ✅
test_improve.py::test_analyze_kb_empty             ✅
test_improve.py::test_analyze_kb_with_data         ✅
test_kb.py::test_kb_store                          ✅
test_kb.py::test_kb_search                         ✅
test_kb.py::test_kb_search_no_results              ✅
test_kb.py::test_kb_stats_empty                    ✅
test_kb.py::test_kb_multiple_entries               ✅
test_api.py::test_health                           ✅
test_api.py::test_debug_invalid                    ✅
test_api.py::test_status_not_found                 ✅
test_api.py::test_kb_stats                         ✅
test_tools.py::test_tools_count                    ✅
test_tools.py::test_tools_names                    ✅
test_tools.py::test_tool_triage_called             ✅
test_tools.py::test_tool_fix_bug_file_not_found   ✅
========================= 17 passed in 4.22s =====================
```

---

## 10. Amélioration continue

Le script `nexus_improve.py` analyse les feedbacks et la KB pour suggérer des améliorations.

### 10.1 Générer un rapport

```bash
cd ~/nexus-debug && source .venv/bin/activate
python nexus_improve.py --report
```

### 10.2 Versionner les prompts

```bash
cd ~/nexus-debug && source .venv/bin/activate
python nexus_improve.py --init-git
```

### 10.3 Analyse des feedbacks

Le script détecte automatiquement :
- Notes moyennes (1-5)
- Issues fréquentes (lent, inutile, inefficace)
- Top catégories de bugs
- Top langages
- Suggestions d'amélioration du prompt system

---

```

---

## 12. Dépannage

| Problème | Cause | Solution |
|---|---|---|
| `DEEPSEEK_API_KEY not set` | Clé manquante | `export DEEPSEEK_API_KEY="sk-..."` |
| API ne répond pas | Port occupé | Changer `NEXUS_API_PORT` ou `kill $(lsof -ti:9001)` |
| Tests échouent | Dépendances manquantes | `pip install -r requirements.txt` |
| MCP Server erreur `FastMCP` | mcp version incorrecte | `pip install mcp>=1.0` |
| Tool fix_bug: `escalate: true` | Fichier non trouvé | Vérifier le chemin absolu |
| Webhook GitHub: 403 | Signature manquante | Configurer `GITHUB_WEBHOOK_SECRET` |
| Webhook ignoré | Label "bug" manquant | Ajouter le label `bug` à l'issue |
| `ModuleNotFoundError` | Pas dans le venv | `source .venv/bin/activate` |

### Logs

```bash
# Logs de l'API
tail -f ~/nexus-reports/nexus_api.log

# Voir les tâches en cours
curl http://localhost:9001/tasks

# Vider la KB de test
rm ~/nexus_kb.yaml
```

---

## Licence

