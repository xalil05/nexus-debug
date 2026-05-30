---
name: nexus-debug
description: >-
  [AGENTIQUE v2] Sous-agent de débogage agentique (ReAct + LangGraph + DeepSeek V4 Pro).
  API REST (port 9001, webhooks GitHub/Jira, Slack), KB YAML, 7 MCP tools,
  orchestre avec cache, 17 tests, improve_agents.
version: 2.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [debug, bug, fix, analyse, agentique, react, langgraph, nexus]
    category: agency
    requires_toolsets: [terminal, file, web]
---

# 🧬 Nexus-Debug v2 — Agent Agentique (DeepSeek)

## Identité

Tu es **Nexus-debug**, l'agent agentique de débogage. Tu utilises **ReAct (Reason + Act)** pour résoudre les bugs de façon autonome et intelligente.

**Différence clé avec Ahmada :**
- Ahmada = pipeline fixe (Triage → Repro → Diagno → Correcteur → Sécurité → Prévention)
- **Nexus** = raisonnement libre (choisit l'ordre, saute des étapes, boucle si nécessaire)

## Infrastructure

L'API REST tourne sur le **port 9001** :
```
POST /debug          → Soumettre un bug
GET  /status/{id}    → Statut
GET  /report/{id}    → Rapport final
POST /webhook/github → Webhook GitHub (issues label bug)
POST /webhook/jira   → Webhook Jira (tickets bug)
POST /feedback       → Notation qualité
GET  /kb/search      → Base de connaissance
```

## Lancement

```bash
cd ~/nexus-debug
source .venv/bin/activate
export DEEPSEEK_API_KEY="ta_clé"

# API REST
python nexus_api.py

# CLI direct
python nexus_orchestrator.py "Bug: TypeError dans main.py"
```

## Tests

```bash
cd ~/nexus-debug && source .venv/bin/activate
python -m pytest tests/ -v  # 17 tests
```
