# Nexus Watch — Monitoring Intelligent 🧬

> **Capture d'erreurs automatique + Diagnostic IA + Correction via DeepSeek**
> Version **3.0.0** — Juin 2026

> ⚠️ **SÉCURITÉ** : Ne jamais exposer sans API_KEY configurée,
> sans CORS restrictif, et sans user non-root dans le conteneur.
> Les tokens d'accès (Telegram, API keys) sont stockés en base chiffrée.

---

## 🚀 Quick Start

```bash
# Docker (recommandé)
git clone https://github.com/xalil05/nexus-debug.git
cd nexus-debug
cp .env.example .env   # Configurer DEEPSEEK_API_KEY
docker compose up -d

# Vérifier
curl http://localhost:9000/health        # via Caddy
curl http://localhost:9001/health        # direct API
```

---

## 📊 Services

| Service | URL | Accès |
|---|---|---|
| 🔵 **Nexus API** | `http://localhost:9001` | API REST |
| 🔵 **Caddy proxy** | `http://localhost:9000` | Reverse proxy + dashboard |
| 🖥️ **Dashboard** | `http://localhost:9000/dashboard/` | UI agents |
| 📈 **Prometheus** | `http://localhost:9090` | Métriques |
| 📉 **Grafana** | `http://localhost:3000` | `admin` / mot de passe dans `.env` |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      NEXUS WATCH                                 │
│                                                                  │
│  ┌──────────────────────┐    ┌──────────────────────────────┐   │
│  │   watch-py           │    │   Nexus Hub (multi-tenant)    │   │
│  │   (chez le client)   │───►│   /hub/capture               │   │
│  │                      │    │   /hub/register              │   │
│  │   pip install watch  │    │   /hub/login                 │   │
│  │   + 3 lignes de code │    │   /hub/{id}/notifications    │   │
│  └──────────────────────┘    │   /hub/{id}/ssh-key          │   │
│                               │   /hub/{id}/diagnose         │   │
│                               └──────────────┬───────────────┘   │
│                                              │                    │
│                                              ▼                    │
│                               ┌──────────────────────────────┐   │
│                               │   Notification Engine         │   │
│                               │   ┌─────────┐ ┌──────────┐   │   │
│                               │   │Telegram │ │WhatsApp  │   │   │
│                               │   │@xalil.. │ │(Twilio)  │   │   │
│                               │   │3 boutons│ │          │   │   │
│                               │   └─────────┘ └──────────┘   │   │
│                               │   ┌─────────┐                 │   │
│                               │   │ Slack   │                 │   │
│                               │   └─────────┘                 │   │
│                               └──────────────────────────────┘   │
│                                              │                    │
│                                DeepSeek IA ◄─┘                    │
│                                (diagnostic + correctif)          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Notifications Telegram

Quand une erreur est capturée, tu reçois un message avec **3 boutons** :

| Bouton | Comportement |
|---|---|
| ✅ **Corriger** | DeepSeek génère un fix → notification de fin |
| 📄 **Rapport** | DeepSeek diagnostique la cause racine → notification de fin |
| 🔍 **Détails** | Affiche les infos brutes de la capture |

Le bot : **@xaliln8nbot**
Lier un client : envoyer `/start VOTRE_CLIENT_ID` au bot

---

## 📡 Endpoints Hub

### Clients
| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/hub/register` | Créer un compte client |
| `POST` | `/hub/login` | Authentification |
| `PUT` | `/hub/{id}/notifications` | Configurer Telegram/WhatsApp/Slack |
| `GET` | `/hub/{id}/stats` | Statistiques du client |

### Capture d'erreurs
| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/hub/capture` | Recevoir une erreur (watch-py) |
| `GET` | `/hub/{id}/captures` | Historique des erreurs |
| `GET` | `/hub/{id}/captures/{cid}` | Détail d'une capture |
| `POST` | `/hub/{id}/captures/{cid}/report` | Rapport IA (DeepSeek) |

### Diagnostic SSH (Option B)
| Méthode | Endpoint | Description |
|---|---|---|
| `PUT` | `/hub/{id}/ssh-key` | Enregistrer clé SSH |
| `GET` | `/hub/{id}/ssh-status` | Vérifier accès SSH |
| `POST` | `/hub/{id}/diagnose` | Diagnostic complet du serveur |
| `POST` | `/hub/{id}/diagnose/command` | Commande personnalisée |

### Administration
| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/hub/admin/config` | Configurer (token Telegram, clé DeepSeek, etc.) |
| `GET` | `/hub/admin/config` | Voir la config (valeurs masquées) |

---

## 🐍 watch-py — Middleware Client

Package Python à installer chez le client pour capturer les erreurs automatiquement.

```bash
pip install watch-py
```

### Flask
```python
from watch import flask as watch
app = watch.init(app, api_key="sk-watch-...")
```

### FastAPI
```python
from watch import fastapi as watch
app = watch.init(app, api_key="sk-watch-...")
```

3 lignes suffisent. Le middleware capture les 5xx et les envoie au Hub.

---

## 🔐 Sécurité

| Mesure | Statut |
|---|---|
| Mots de passe | **bcrypt** (avec sel, recommandé OWASP) |
| Clés SSH au repos | **Chiffrement Fernet** (AES-128-CBC) |
| SSH host key | **WarningPolicy** (refuse les inconnues) |
| API Key | Bearer token / body (capture) |
| Webhooks GitHub | **HMAC-SHA256** (vérifié) |
| SQL injection | **Requêtes paramétrées** |
| Grafana | Mot de passe unique (plus `CHANGE_ME`) |
| Conteneur | User **non-root** (gosu) |

---

## 🗂️ Structure du projet

```
nexus-debug/
├── nexus_hub/                  ← Nexus Watch Hub (multi-tenant)
│   ├── routes.py               ← API endpoints
│   ├── notify.py               ← Moteur de notifications
│   ├── telegram_utils.py       ← Utilitaires Telegram partagés
│   ├── db.py                   ← Base de données (SQLite)
│   └── ssh.py                  ← Diagnostic SSH (Option B)
├── nexus_agent.py              ← Agent ReAct (LangGraph)
├── nexus_api.py                ← API REST + dashboard
├── nexus_tools.py              ← Outils sous-agents
├── nexus_kb.py                 ← Base de connaissance YAML
├── nexus_config.py             ← Config loader (gardé pour futur)
├── nexus_mcp_server.py         ← Outils MCP
├── nexus_orchestrator.py       ← Orchestrateur
├── nexus_improve.py            ← Amélioration continue
├── nexus_capture/              ← Auto-capture (legacy)
├── watch/                      ← watch-py (package pip)
├── frontend/                   ← Dashboard
├── test_callback.py            ← Test pipeline callbacks
├── test_log.py                 ← Test logging
├── .env.example                ← Variables d'environnement
├── Dockerfile                  ← Multi-stage Docker
├── docker-compose.yml          ← 4 services
├── docker/
│   ├── caddy/                  ← Reverse proxy
│   ├── prometheus/             ← Métriques
│   └── grafana/                ← Dashboard Grafana
└── tests/                      ← Tests pytest
```

---

## ⚙️ Configuration

```bash
# Obligatoire
export DEEPSEEK_API_KEY="sk-votre_clé"

# Optionnel
export NEXUS_API_KEY="nexus-secret-key"
export NEXUS_MODEL="deepseek-chat"
```

**Token Telegram** : à configurer via l'API admin après déploiement :
```bash
curl -X POST http://localhost:9001/hub/admin/config \
  -H "Content-Type: application/json" \
  -d '{"key": "telegram_bot_token", "value": "VOTRE_TOKEN"}'
```

---

## 📦 Dépendances

- **Python ≥3.11** : bcrypt, FastAPI, LangGraph, paramiko, cryptography
- **Services** : Caddy, Prometheus, Grafana
- **LLM** : DeepSeek (par défaut), OpenAI, Anthropic, Ollama (fallback)

---

## 📜 Licence

MIT — AMICO TECH / Ibrahima Xaliloulah NDIAYE
