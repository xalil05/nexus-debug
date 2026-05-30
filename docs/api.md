# API REST Nexus-Debug v2 — Documentation Technique

> Base URL : `http://<host>:9001`
> Port par défaut : 9001 (configurable via `NEXUS_API_PORT`)

---

## `GET /health`

Healthcheck du service.

### Réponse

```json
{
  "status": "ok",
  "version": "2.0.0",
  "service": "nexus-debug",
  "github_webhook": false,
  "slack_webhook": true
}
```

**Codes** : `200`

---

## `POST /debug`

Soumet un bug à Nexus pour analyse et correction. La tâche est lancée en arrière-plan.

### Corps de la requête

```json
{
  "description": "Erreur dans le module auth (texte libre)",
  "project": "bellissima-site",
  "langage": "typescript",
  "fichier": "src/lib/auth.ts",
  "erreur": "TypeError: Cannot read properties of undefined",
  "stack": "at getUser (auth.ts:42:15)",
  "priority": "P1"
}
```

### Champs

| Champ | Type | Obligatoire | Défaut | Description |
|---|---|---|---|---|
| `description` | string | **Oui** | — | Description complète du bug |
| `project` | string | Non | `""` | Nom du projet |
| `langage` | string | Non | `""` | Langage de programmation |
| `fichier` | string | Non | `""` | Chemin du fichier suspect |
| `erreur` | string | Non | `""` | Message d'erreur exact |
| `stack` | string | Non | `""` | Stack trace |
| `priority` | string | Non | `"P2"` | P0-Bloquant / P1-Majeur / P2-Mineur / P3-Cosmétique |

### Réponse (202)

```json
{
  "task_id": "a1b2c3d4",
  "status": "en_attente"
}
```

**Codes** : `202` (accepté), `422` (validation error)

---

## `GET /status/{task_id}`

Récupère le statut d'une tâche de débogage.

### Réponse

```json
{
  "task_id": "a1b2c3d4",
  "status": "termine"
}
```

### Statuts possibles

| Statut | Signification |
|---|---|
| `en_attente` | Dans la file, pas encore traité |
| `en_cours` | Nexus analyse le bug |
| `termine` | Bug traité, rapport disponible |
| `erreur` | Erreur lors du traitement |

**Codes** : `200`, `404` (tâche inconnue)

---

## `GET /report/{task_id}`

Récupère le rapport complet d'une tâche terminée.

### Réponse

```json
{
  "task_id": "a1b2c3d4",
  "status": "termine",
  "priority": "P1",
  "brief": "PROJET : bellissima-site\nLANGAGE : typescript\n...",
  "created_at": "2026-05-30T12:00:00",
  "completed_at": "2026-05-30T12:03:15",
  "result": {
    "mission_id": "DBG-A1B2C3D4",
    "status": "fixed",
    "root_cause": "Variable 'user' non définie quand token manquant",
    "files_modified": ["src/lib/auth.ts"],
    "fix_summary": "Ajout vérification du token avant accès à user.id",
    "tests_added": ["tests/test_auth.ts::test_no_token_returns_error"],
    "confidence": 0.95,
    "tools_used": ["tool_triage", "tool_static_analysis", "tool_runtime_debug", "tool_fix_bug", "tool_generate_tests"],
    "reasoning_summary": "Triage → null reference → analyse statique ligne 42 → runtime confirme → fix guard check → tests",
    "prevention": "Toujours vérifier les params avant accès. Ajouter un middleware auth.",
    "needs_human": false
  }
}
```

**Codes** : `200`, `404` (tâche inconnue)

---

## `GET /tasks`

Liste toutes les tâches soumises (résumé).

### Réponse

```json
{
  "tasks": [
    {"task_id": "a1b2c3d4", "status": "termine", "priority": "P1", "created_at": "2026-05-30T12:00:00"},
    {"task_id": "e5f6g7h8", "status": "en_attente", "priority": "P2", "created_at": "2026-05-30T12:05:00"}
  ]
}
```

**Codes** : `200`

---

## `POST /feedback`

Permet à un humain de noter la qualité du traitement (1-5). Les feedbacks sont utilisés par `nexus_improve.py`.

### Corps de la requête

```json
{
  "task_id": "a1b2c3d4",
  "rating": 4,
  "comment": "Bon diagnostic mais correction un peu lourde",
  "corrected_by_human": "J'ai simplifié le fix"
}
```

### Champs

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `task_id` | string | **Oui** | ID de la tâche notée |
| `rating` | integer | **Oui** | Note de 1 (inutile) à 5 (parfait) |
| `comment` | string | Non | Commentaire libre |
| `corrected_by_human` | string | Non | Correction humaine apportée |

### Réponse

```json
{
  "status": "recorded",
  "task_id": "a1b2c3d4"
}
```

**Codes** : `200`, `404` (tâche inconnue), `422` (rating hors limites)

---

## `GET /kb/search`

Recherche dans la base de connaissance des bugs résolus.

### Paramètres

| Paramètre | Type | Obligatoire | Description |
|---|---|---|---|
| `q` | string | Non | Requête textuelle. Si vide → retourne les stats. |

### Réponse

```json
{
  "status": "success",
  "query": "null pointer user",
  "results": [
    {
      "bug_id": "BUG-A1B2",
      "timestamp": "2026-05-30T12:03:15",
      "category": "null_reference",
      "summary": "AttributeError NoneType dans user.py",
      "root_cause": "user=None quand pas authentifié",
      "solution": "Ajouter guard check",
      "keywords": ["null", "user"]
    }
  ],
  "count": 1
}
```

**Codes** : `200`

---

## `GET /kb/stats`

Statistiques de la base de connaissance.

### Réponse

```json
{
  "status": "success",
  "total_bugs": 15,
  "total_patterns": 12,
  "categories": {
    "null_reference": 5,
    "type_error": 3,
    "runtime_crash": 2,
    "security_vuln": 3,
    "perf_degradation": 2
  },
  "kb_path": "/home/nexus05/nexus_kb.yaml"
}
```

**Codes** : `200`

---

## `POST /webhook/github`

Reçoit les webhooks de GitHub. Ne traite que les **issues** avec le **label `bug`**.

### Configuration GitHub

| Champ | Valeur |
|---|---|
| Payload URL | `http://<votre-ip>:9001/webhook/github` |
| Content type | `application/json` |
| Secret | `GITHUB_WEBHOOK_SECRET` (optionnel) |
| Events | Issues |

### Comportement

1. Issue ouverte avec label `bug`
2. Nexus analyse le bug
3. Un commentaire est posté sur l'issue avec le diagnostic
4. Notification Slack envoyée

**Codes** : `200` (traité), `202` (bug accepté), `403` (signature invalide)

---

## `POST /webhook/jira`

Reçoit les webhooks de Jira. Ne traite que les **tickets de type `Bug`**.

### Configuration Jira

| Champ | Valeur |
|---|---|
| URL | `http://<votre-ip>:9001/webhook/jira` |
| Events | Issue created, Issue updated |

### Comportement

1. Ticket créé avec issuetype = "Bug"
2. Nexus analyse le bug
3. Notification Slack envoyée

**Codes** : `200`, `202`

---

## Schéma de l'API (OpenAPI)

L'API est auto-documentée avec Swagger UI à l'adresse :
```
http://localhost:9001/docs
```

Ou Redoc :
```
http://localhost:9001/redoc
```
