"""Tests pour nexus_kb.py"""

import os
from pathlib import Path

# Surcharger le chemin KB pour les tests
os.environ["NEXUS_KB_PATH"] = "/tmp/nexus_test_kb.yaml"

from nexus_kb import get_kb_path, kb_search, kb_stats, kb_store


def setup_function():
    """Nettoie la KB avant chaque test."""
    Path(get_kb_path()).unlink(missing_ok=True)


def test_kb_store():
    result = kb_store(
        bug_id="BUG-001",
        category="null_reference",
        summary="AttributeError NoneType dans user.py",
        root_cause="user=None quand non authentifié",
        solution="Ajouter guard check if user is not None",
        langage="python",
        keywords=["null", "user", "auth"],
    )
    assert result["status"] == "stored"
    assert result["bug_id"] == "BUG-001"


def test_kb_search():
    kb_store(
        bug_id="BUG-001",
        category="null_reference",
        summary="AttributeError NoneType",
        root_cause="user=None",
        solution="Guard check",
        keywords=["null", "user"],
    )
    results = kb_search("null user")
    assert results["status"] == "success"
    assert results["count"] >= 1


def test_kb_search_no_results():
    results = kb_search("xyznonexistent12345")
    assert results["count"] == 0


def test_kb_stats_empty():
    stats = kb_stats()
    assert stats["total_bugs"] == 0


def test_kb_multiple_entries():
    kb_store(bug_id="B1", category="null", summary="Null ref", root_cause="null", solution="fix")
    kb_store(bug_id="B2", category="type", summary="Type error", root_cause="type", solution="fix")
    kb_store(
        bug_id="B3", category="null", summary="Another null", root_cause="null", solution="fix"
    )

    stats = kb_stats()
    assert stats["total_bugs"] == 3
    assert stats["categories"]["null"] == 2
    assert stats["categories"]["type"] == 1
