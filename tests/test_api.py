"""Tests pour l'API REST nexus_api.py — endpoint coverage complet"""

from __future__ import annotations

import sys

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, ".")

from nexus_api import app


@pytest.mark.asyncio
async def test_health() -> None:
    """GET /health doit retourner OK avec version."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "nexus-debug"
        assert data["version"] == "2.2.1"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_structure() -> None:
    """Vérifie la structure complète du healthcheck."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        data = resp.json()
        required_keys = {
            "status",
            "version",
            "service",
            "db_connected",
            "deepseek",
            "api_key_configured",
            "timestamp",
            "metrics_enabled",
        }
        assert required_keys.issubset(data.keys()), f"Missing keys: {required_keys - data.keys()}"


@pytest.mark.asyncio
async def test_metrics_endpoint() -> None:
    """GET /metrics doit retourner des métriques Prometheus."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        body = resp.text
        assert "# HELP" in body
        assert "# TYPE" in body
        assert "nexus_" in body


@pytest.mark.asyncio
async def test_debug_invalid_empty_body() -> None:
    """POST /debug sans body doit retourner 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/debug", json={})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_debug_invalid_priority() -> None:
    """POST /debug avec priorité invalide doit retourner 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/debug",
            json={
                "description": "Test bug",
                "priority": "INVALID",
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_debug_valid_submission() -> None:
    """POST /debug valide doit retourner 202 et un task_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/debug",
            json={
                "description": "Test bug simple",
                "project": "test-project",
                "langage": "python",
                "priority": "P2",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "en_attente"
        assert len(data["task_id"]) == 8


@pytest.mark.asyncio
async def test_status_not_found() -> None:
    """GET /status/INEXISTANT doit retourner 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/status/INEXISTANT")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Tâche non trouvée"


@pytest.mark.asyncio
async def test_report_not_found() -> None:
    """GET /report/INEXISTANT doit retourner 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/report/INEXISTANT")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_kb_stats() -> None:
    """GET /kb/stats doit retourner les stats KB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/kb/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bugs" in data
        assert "total_patterns" in data
        assert "categories" in data


@pytest.mark.asyncio
async def test_kb_search_empty() -> None:
    """GET /kb/search sans q doit retourner les stats."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/kb/search")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bugs" in data


@pytest.mark.asyncio
async def test_kb_search_with_query() -> None:
    """GET /kb/search?q=test doit retourner des résultats."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/kb/search?q=null+reference")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "count" in data


@pytest.mark.asyncio
async def test_tasks_list() -> None:
    """GET /tasks doit retourner la liste des tâches."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "total" in data


@pytest.mark.asyncio
async def test_github_webhook_ping() -> None:
    """Webhook GitHub ping doit retourner pong."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhook/github",
            json={"zen": "test"},
            headers={"X-GitHub-Event": "ping"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pong"


@pytest.mark.asyncio
async def test_github_webhook_ignored_non_bug() -> None:
    """Webhook GitHub issue sans label bug doit être ignoré."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhook/github",
            json={
                "action": "opened",
                "issue": {
                    "title": "Feature request",
                    "body": "",
                    "labels": [{"name": "enhancement"}],
                },
                "repository": {"full_name": "test/repo"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_github_webhook_bug_accepted() -> None:
    """Webhook GitHub issue avec label bug doit être accepté."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhook/github",
            json={
                "action": "opened",
                "issue": {
                    "title": "Bug critique",
                    "body": "Crash sur login",
                    "labels": [{"name": "bug"}],
                    "number": 42,
                },
                "repository": {"full_name": "test/repo"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "en_attente"
        assert len(data["task_id"]) == 8


@pytest.mark.asyncio
async def test_jira_webhook_ignored_non_bug() -> None:
    """Webhook Jira sans type Bug doit être ignoré."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhook/jira",
            json={
                "webhookEvent": "jira:issue_created",
                "issue": {
                    "fields": {
                        "summary": "Nouvelle feature",
                        "issuetype": {"name": "Task"},
                        "project": {"key": "PROJ"},
                    },
                },
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_jira_webhook_bug_accepted() -> None:
    """Webhook Jira avec type Bug doit être accepté."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhook/jira",
            json={
                "webhookEvent": "jira:issue_created",
                "issue": {
                    "fields": {
                        "summary": "Bug en prod",
                        "description": "Erreur 500",
                        "issuetype": {"name": "Bug"},
                        "project": {"key": "PROJ"},
                    },
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "en_attente"
