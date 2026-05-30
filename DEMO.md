# Nexus-Debug v2.1 — Interactive Demo 🧬

> **Système agentique de débogage** — ReAct + LangGraph + DeepSeek V4 Pro
> Demo enregistrée le **30 Mai 2026**

---

## Table des matières

1. [Environment & Preflight](#1-environment--preflight)
2. [Seeding the Knowledge Base](#2-seeding-the-knowledge-base)
3. [API Health Check](#3-api-health-check)
4. [Submitting a Bug via CLI](#4-submitting-a-bug-via-cli)
5. [Checking Task Status](#5-checking-task-status)
6. [Knowledge Base Search](#6-knowledge-base-search)
7. [Knowledge Base Statistics](#7-knowledge-base-statistics)
8. [Architecture Overview](#8-architecture-overview)

---

## 1. Environment & Preflight

```bash
╔══════════════════════════════════════════════════════════════╗
║  Step 0: Environment & Preflight                         ║
╚══════════════════════════════════════════════════════════════╝

Python version : Python 3.11.15
Virtual env    : /home/xalil05/nexus-debug/.venv
Nexus directory: /home/xalil05/nexus-debug

DEEPSEEK_API_KEY: <not set>
  → API calls will gracefully degrade (no LLM available)
  → KB operations and CLI still work with full functionality
```

> **Note:** Si `DEEPSEEK_API_KEY` n'est pas configurée, Nexus-debug continue de fonctionner pour les opérations hors-ligne (KB, CLI) et affiche des warnings explicites. L'agent ReAct nécessite la clé pour les appels LLM.

---

## 2. Seeding the Knowledge Base

La base de connaissance (KB) stocke les bugs résolus au format YAML. Elle permet de :
- **Éviter de retraiter** les mêmes bugs (cache)
- **Rechercher** par mots-clés
- **Générer des patterns** de résolution réutilisables

```bash
╔══════════════════════════════════════════════════════════════╗
║  Step 1: Seeding Knowledge Base (KB)                     ║
╚══════════════════════════════════════════════════════════════╝

KB path: /home/xalil05/nexus_kb.yaml

  ✓ Stored BUG-2025-001 -> pattern PTN-0001
  ✓ Stored BUG-2025-002 -> pattern PTN-0002
  ✓ Stored BUG-2025-003 -> pattern PTN-0003
  ✓ Stored BUG-2025-004 -> pattern PTN-0004

KB stats: 4 bugs, 4 patterns
Categories: {'null_reference': 1, 'type_error': 1, 'import_error': 1, 'performance': 1}
```

### Contenu de la KB

| Bug ID | Catégorie | Résumé |
|--------|-----------|--------|
| `BUG-2025-001` | `null_reference` | AttributeError: 'NoneType' object has no attribute 'id' |
| `BUG-2025-002` | `type_error` | TypeError: str vs int dans data_processor.py |
| `BUG-2025-003` | `import_error` | ModuleNotFoundError: pandas manquant |
| `BUG-2025-004` | `performance` | N+1 query avec SQLAlchemy |

---

## 3. API Health Check

L'API REST expose un endpoint `/health` qui vérifie tous les composants critiques :

```bash
╔══════════════════════════════════════════════════════════════╗
║  Step 2: API Health Check                                ║
╚══════════════════════════════════════════════════════════════╝

Starting API server on port 19001...

2026-05-30 15:59:23.031 | WARNING  | nexus_agent:<module>:88
  - DEEPSEEK_API_KEY non définie — l'agent échouera au runtime

GET /health
{
  "status": "ok",
  "version": "2.1.0",
  "service": "nexus-debug",
  "deepseek": {
    "status": "not_configured",
    "error": "DEEPSEEK_API_KEY manquante"
  },
  "db_connected": true,
  "github_webhook": false,
  "slack_webhook": false,
  "api_key_configured": false,
  "metrics_enabled": true,
  "timestamp": "2026-05-30T13:59:23.075153"
}
```

> **Graceful degradation :** Le service reste opérationnel même sans clé API. DeepSeek est marqué comme `not_configured`, l'API continue de répondre.

### Commandes équivalentes

```bash
# Démarrer l'API
cd ~/nexus-debug && source .venv/bin/activate
python nexus_api.py &

# Healthcheck
curl http://localhost:9001/health
```

---

## 4. Submitting a Bug via CLI

### Via l'orchestrateur (recommandé)

L'orchestrateur suit un flow intelligent :
1. **Vérifie la KB** — si un bug similaire existe déjà (cache hit), il retourne la solution directement
2. **Lance l'agent ReAct** — si cache miss, DeepSeek V4 Pro analyse et résout
3. **Stocke le résultat** — enrichit la KB pour les prochaines fois

```bash
╔══════════════════════════════════════════════════════════════╗
║  Step 3: Submitting a Bug via CLI                        ║
╚══════════════════════════════════════════════════════════════╝

┌─ Orchestrator Flow ──────────────────────────────────────────┐
│                                                              │
│  Brief: "AttributeError: 'NoneType' object has no attribute  │
│          'id' in src/main.py, line 42"                       │
│                                                              │
│  1. KB check...                                              │
│     → Found BUG-2025-001 (confidence: 0.95)                  │
│     → CACHED — using existing solution                       │
│                                                              │
│  2. Result from cache:                                       │
│     Mission: XAL-20250530-a1b2                              │
│     Status:  cached (KB hit)                                 │
│     Fix:     Add guard check `if user is not None:`          │
│     Files:   src/main.py:42                                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘

  KB search results for: "AttributeError NoneType object has no attribute id"
  → 3 match(es) found
    [BUG-2025-001] AttributeError: 'NoneType' object has no attribute 'id' in user.py
    Root cause: user is None when session token is invalid or expired
    Solution:   Add guard check `if user is not None:` before accessing `.id`

    [BUG-2025-004] Slow query performance in dashboard — N+1 problem in SQLAlchemy
    ...

    [BUG-2025-002] TypeError: can only concatenate str (not 'int') to str in data_processor.py
    ...
```

### Usage réel

```bash
# CLI direct
python nexus_orchestrator.py "AttributeError: 'NoneType' object has no attribute 'id'"

# Avec une description complète
python nexus_orchestrator.py "
PROJET   : bellissima-site
LANGAGE  : typescript
FICHIER  : src/lib/auth.ts
ERREUR   : TypeError: Cannot read properties of undefined
STACK    : File auth.ts:23
PRIORITÉ : P1
"
```

### Via l'API REST

```bash
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
```

---

## 5. Checking Task Status

Chaque soumission de bug retourne un `task_id` unique. L'API permet de suivre l'avancement :

```bash
╔══════════════════════════════════════════════════════════════╗
║  Step 4: Checking Task Status                            ║
╚══════════════════════════════════════════════════════════════╝

  POST /debug   → {"task_id": "a1b2c3d4", "status": "en_attente"}
  GET  /status/{task_id} → status of the task
  GET  /report/{task_id} → full report with result

┌─ Task Status Examples ────────────────────────────────────────┐
│                                                              │
│  GET /status/a1b2c3d4                                        │
│  → {"task_id": "a1b2c3d4", "status": "termine"}             │
│                                                              │
│  GET /status/e5f6g7h8                                        │
│  → {"task_id": "e5f6g7h8", "status": "en_cours"}            │
│                                                              │
│  GET /report/a1b2c3d4 (full report)                          │
│  → Task completed ✓                                          │
│    Status:      fixed                                        │
│    Root cause:  Undefined variable 'config' in auth module   │
│    Fix:         Import config from @app/config                │
│    Confidence:  0.95                                         │
│  → Full JSON report available                                │
└──────────────────────────────────────────────────────────────┘
```

### États possibles d'une tâche

| Statut | Signification |
|--------|--------------|
| `en_attente` | Bug soumis, en file d'attente |
| `en_cours` | Nexus est en train d'analyser |
| `termine` | Analyse terminée (consulter `/report/{id}`) |
| `erreur` | Une erreur est survenue |

### Exemple de rapport complet

```json
{
  "task_id": "a1b2c3d4",
  "status": "termine",
  "result": {
    "mission_id": "DBG-A1B2C3D4",
    "status": "fixed",
    "root_cause": "Undefined variable 'config' in auth module",
    "files_modified": ["src/lib/auth.ts"],
    "fix_summary": "Import config from @app/config",
    "confidence": 0.95,
    "tools_used": [
      "tool_triage",
      "tool_static_analysis",
      "tool_fix_bug",
      "tool_generate_tests"
    ],
    "needs_human": false
  }
}
```

---

## 6. Knowledge Base Search

La KB supporte la recherche par mots-clés avec scoring. Les résultats incluent le `bug_id`, le résumé, la cause racine et la solution.

```bash
╔══════════════════════════════════════════════════════════════╗
║  Step 5: Knowledge Base Search                           ║
╚══════════════════════════════════════════════════════════════╝

  🔍 Searching: "null user"
  → 1 result(s)
    [BUG-2025-001] AttributeError: 'NoneType' object has no attribute 'id' in user.py
    Cause:  user is None when session token is invalid or expired
    Fix:    Add guard check `if user is not None:` before accessing `.id`

  🔍 Searching: "import error dependency"
  → 3 result(s)
    [BUG-2025-003] ModuleNotFoundError: No module named 'pandas' in analysis.py
    Cause:  Missing dependency in requirements.txt
    Fix:    Add `pandas>=2.0.0` to requirements.txt and reinstall

    [BUG-2025-002] TypeError: can only concatenate str (not 'int') to str...
    ...

    [BUG-2025-001] AttributeError: 'NoneType' object has no attribute 'id'...
    ...

  🔍 Searching: "performance sql slow"
  → 1 result(s)
    [BUG-2025-004] Slow query performance — N+1 in SQLAlchemy
    Cause:  Eager loading not configured
    Fix:    Add `joinedload()` to the relationship query
```

### Utilisation programmatique

```python
from nexus_kb import kb_search

results = kb_search("null user auth", max_results=5)
print(f"Trouvé {results['count']} résultat(s)")
for bug in results['results']:
    print(f"[{bug['bug_id']}] {bug['summary']}")
    print(f"  Cause: {bug['root_cause']}")
    print(f"  Fix:   {bug['solution']}")
```

### API REST

```bash
curl "http://localhost:9001/kb/search?q=null+pointer"
curl "http://localhost:9001/kb/stats"
```

---

## 7. Knowledge Base Statistics

```bash
╔══════════════════════════════════════════════════════════════╗
║  Step 6: Knowledge Base Statistics                       ║
╚══════════════════════════════════════════════════════════════╝

  Total bugs stored:   4
  Total patterns:      4
  KB location:         /home/xalil05/nexus_kb.yaml
  By category:
    • null_reference: 1
    • type_error: 1
    • import_error: 1
    • performance: 1
```

---

## 8. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   Orchestrateur humain                    │
└─────────────────────┬────────────────────────────────────┘
                      │ brief structuré
                      ▼
┌──────────────────────────────────────────────────────────┐
│              nexus_orchestrator.py                       │
│   ┌─ KB check → cache hit? → solution directe           │
│   └─ cache miss → nexus_agent.py (ReAct loop)           │
└───────────────────┬──────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────┐
│   nexus_agent.py — ReAct (LangGraph + DeepSeek V4 Pro)   │
│                                                          │
│   Boucle : Thought → Action → Observation → Repeat       │
│   Outils : triage, static, security, runtime, perf,      │
│            fix_bug, tests, postmortem                    │
└───────────────────┬──────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────┐
│           nexus_api.py — API REST (port 9001)            │
│                                                          │
│  POST /debug     → Soumettre un bug                     │
│  GET  /status    → Statut de la tâche                   │
│  GET  /report    → Rapport complet                      │
│  GET  /health    → Healthcheck                          │
│  GET  /kb/search → Recherche KB                         │
│  POST /webhook   → GitHub / Jira                        │
└──────────────────────────────────────────────────────────┘
```

---

## Conclusion

Cette démo a montré les 4 fonctionnalités principales de **Nexus-Debug v2.1** :

1. ✅ **Health Check** — Vérification complète du service avec gestion gracieuse des dépendances manquantes
2. ✅ **Bug Submission** — CLI via l'orchestrateur avec cache KB intelligent
3. ✅ **Task Status** — Suivi en temps réel des missions de débogage
4. ✅ **KB Search** — Recherche multi-critères dans la base de connaissance

### Pour aller plus loin

- **Documentation complète** : [README.md](../README.md)
- **API Docs** : `http://localhost:9001/docs` (Swagger)
- **Changelog** : [CHANGELOG.md](../CHANGELOG.md)

---

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%20|%203.12-blue?style=flat&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat" alt="License">
  <img src="https://img.shields.io/badge/agent-LangGraph-purple?style=flat" alt="LangGraph">
  <img src="https://img.shields.io/badge/LLM-DeepSeek%20V4%20Pro-orange?style=flat" alt="DeepSeek">
  <img src="https://img.shields.io/badge/API-FastAPI-teal?style=flat&logo=fastapi" alt="FastAPI">
</p>
