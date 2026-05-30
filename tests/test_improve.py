"""Tests pour nexus_improve.py"""

import os
from pathlib import Path

import pytest
import yaml

os.environ["NEXUS_FEEDBACK_PATH"] = "/tmp/nexus_test_feedback.yaml"
os.environ["NEXUS_KB_PATH"] = "/tmp/nexus_test_kb.yaml"

from nexus_improve import analyze_feedback, analyze_kb


def setup_function():
    Path("/tmp/nexus_test_feedback.yaml").unlink(missing_ok=True)
    Path("/tmp/nexus_test_kb.yaml").unlink(missing_ok=True)


def test_analyze_feedback_empty():
    result = analyze_feedback()
    assert result["status"] == "no_feedback"


def test_analyze_feedback_with_data():
    # Créer un fichier de feedback
    fb = [
        {"task_id": "001", "rating": 5, "comment": "Parfait"},
        {"task_id": "002", "rating": 2, "comment": "Trop lent"},
        {"task_id": "003", "rating": 1, "comment": "Bug non résolu"},
    ]
    Path("/tmp/nexus_test_feedback.yaml").write_text(yaml.dump(fb))

    result = analyze_feedback()
    assert result["status"] == "analyzed"
    assert result["total_feedback"] == 3
    assert result["average_rating"] == pytest.approx(2.67, 0.01)
    assert result["low_ratings_count"] == 2


def test_analyze_kb_empty():
    result = analyze_kb()
    assert result["total_bugs"] == 0


def test_analyze_kb_with_data():
    kb = {
        "bugs": [
            {"category": "null", "langage": "python"},
            {"category": "type", "langage": "python"},
        ],
        "patterns": [{"pattern_id": "PTN-001"}],
        "version": 2,
    }
    Path("/tmp/nexus_test_kb.yaml").write_text(yaml.dump(kb))

    result = analyze_kb()
    assert result["total_bugs"] == 2
    assert result["total_patterns"] == 1
    assert ("null", 1) in result["top_categories"]
