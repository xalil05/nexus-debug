"""Tests pour l'API REST nexus_api.py"""
import pytest
from httpx import AsyncClient, ASGITransport

# Importer l'application FastAPI
import sys
sys.path.insert(0, ".")

from nexus_api import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "nexus-debug"


@pytest.mark.asyncio
async def test_debug_invalid():
    """POST /debug sans body valide."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/debug", json={})
        assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_status_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/status/INEXISTANT")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_kb_stats():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/kb/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bugs" in data
