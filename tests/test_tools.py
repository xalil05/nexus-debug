"""Tests pour nexus_tools.py — complet et robuste"""

from __future__ import annotations

import json
import pytest

from nexus_tools import NEXUS_TOOLS


SCHEMA_TOOL_RESULT = {"status", "summary", "confidence", "needs_more", "escalate"}


def test_tools_count() -> None:
    """Vérifie qu'on a exactement 8 outils."""
    assert len(NEXUS_TOOLS) == 8, "Le nombre d'outils a changé"


def test_tools_names() -> None:
    """Vérifie les noms des outils contre la liste attendue."""
    names = [t.name for t in NEXUS_TOOLS]
    expected = [
        "tool_triage",
        "tool_static_analysis",
        "tool_security_scan",
        "tool_runtime_debug",
        "tool_perf_analysis",
        "tool_fix_bug",
        "tool_generate_tests",
        "tool_write_postmortem",
    ]
    assert names == expected


def test_tools_all_have_descriptions() -> None:
    """Vérifie que chaque outil a une description non vide."""
    for tool_fn in NEXUS_TOOLS:
        assert tool_fn.description, f"{tool_fn.name} n'a pas de description"


def test_tool_triage_returns_valid_json() -> None:
    """Vérifie que tool_triage retourne toujours du JSON valide avec les champs requis."""
    from nexus_tools import tool_triage

    result = tool_triage.invoke({"brief": "Test bug simple"})
    parsed = json.loads(result)

    assert "status" in parsed
    assert "summary" in parsed
    assert "bug_category" in parsed
    assert "priority" in parsed
    assert "confidence" in parsed


def test_tool_triage_classifies_null_reference() -> None:
    """Vérifie que le triage détecte une null reference."""
    from nexus_tools import tool_triage

    result = json.loads(tool_triage.invoke({
        "brief": "AttributeError: 'NoneType' object has no attribute 'id' in user.py:42",
    }))
    assert result["bug_category"] in ("null_reference", "type_error", "runtime_crash")
    assert "confidence" in result
    assert 0 <= result["confidence"] <= 1


def test_tool_triage_p0_detected() -> None:
    """Vérifie qu'un P0 (crash prod) est classé haute priorité."""
    from nexus_tools import tool_triage

    result = json.loads(tool_triage.invoke({
        "brief": "CRASH PROD: Segmentation fault dans le module de paiement",
    }))
    assert result["priority"] in ("P0", "P1"), f"Devrait être haute priorité, got {result['priority']}"


def test_tool_fix_bug_file_not_found() -> None:
    """Vérifie le comportement quand le fichier n'existe pas — doit escalate."""
    from nexus_tools import tool_fix_bug

    result = json.loads(tool_fix_bug.invoke({
        "file_to_fix": "/tmp/fichier_inexistant_12345.py",
        "root_cause": "Test",
        "fix_description": "Test fix",
    }))
    assert result["status"] == "error"
    assert result["escalate"] is True


def test_tool_static_analysis_valid_json() -> None:
    """Vérifie que tool_static_analysis retourne du JSON valide."""
    from nexus_tools import tool_static_analysis

    result = json.loads(tool_static_analysis.invoke({
        "files": "/nonexistent/file.py",
        "langage": "python",
    }))
    assert "status" in result


def test_tool_runtime_debug_valid_json() -> None:
    """Vérifie que tool_runtime_debug retourne du JSON valide."""
    from nexus_tools import tool_runtime_debug

    result = json.loads(tool_runtime_debug.invoke({
        "files": "/nonexistent/file.py",
        "error_message": "Test error",
    }))
    assert "status" in result
    assert "root_cause" in result or "confidence" in result


def test_tool_generate_tests_valid_json() -> None:
    """Vérifie que tool_generate_tests retourne du JSON valide."""
    from nexus_tools import tool_generate_tests

    result = json.loads(tool_generate_tests.invoke({
        "bug_summary": "Test bug",
        "fix_description": "Test fix",
        "module_path": "src/test.py",
    }))
    assert "status" in result
    assert "test_code" in result or "summary" in result


def test_tool_write_postmortem_valid_json() -> None:
    """Vérifie que tool_write_postmortem retourne du JSON valide."""
    from nexus_tools import tool_write_postmortem

    result = json.loads(tool_write_postmortem.invoke({
        "mission_id": "DBG-001",
        "bug_summary": "Test bug",
        "root_cause": "Null check manquant",
        "fix_description": "Ajout guard",
        "priority": "P1",
    }))
    assert "status" in result
    assert "postmortem_text" in result or "summary" in result


def test_tool_security_scan_valid_json() -> None:
    """Vérifie que tool_security_scan retourne du JSON valide."""
    from nexus_tools import tool_security_scan

    result = json.loads(tool_security_scan.invoke({
        "files": "/nonexistent/file.py",
        "langage": "python",
    }))
    assert "status" in result


def test_tool_perf_analysis_valid_json() -> None:
    """Vérifie que tool_perf_analysis retourne du JSON valide."""
    from nexus_tools import tool_perf_analysis

    result = json.loads(tool_perf_analysis.invoke({
        "files": "/nonexistent/file.py",
        "symptom": "lent au démarrage",
    }))
    assert "status" in result
