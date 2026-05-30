"""Tests pour nexus_tools.py"""
import json
import pytest

from nexus_tools import NEXUS_TOOLS


def test_tools_count():
    """Vérifie qu'on a 8 outils."""
    assert len(NEXUS_TOOLS) == 8


def test_tools_names():
    """Vérifie les noms des outils."""
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


def test_tool_triage_called():
    """Vérifie que tool_triage retourne du JSON valide."""
    from nexus_tools import tool_triage
    result = tool_triage.invoke({"brief": "Test bug simple"})
    parsed = json.loads(result)
    assert "status" in parsed
    assert "summary" in parsed


def test_tool_fix_bug_file_not_found():
    """Vérifie le comportement quand le fichier n'existe pas."""
    from nexus_tools import tool_fix_bug
    result = tool_fix_bug.invoke({
        "file_to_fix": "/tmp/fichier_inexistant_12345.py",
        "root_cause": "Test",
        "fix_description": "Test fix",
    })
    parsed = json.loads(result)
    assert parsed["status"] == "error"
    assert parsed["escalate"] is True
