"""
nexus_kb.py — Base de connaissance YAML pour Nexus-debug
Permet de stocker et rechercher les patterns de bugs résolus.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

# ── Version de la KB ──────────────────────────────────────────────────────────
KB_VERSION = 3  # incrémenter quand le schéma change


def migrate_kb(data: dict[str, Any]) -> dict[str, Any]:
    """Migre la KB vers la version courante."""
    version = data.get("version", 1)

    if version < 2:
        # v1 → v2 : ajout champs severity, langage
        for bug in data.get("bugs", []):
            bug.setdefault("severity", "medium")
            bug.setdefault("langage", "")
        data["version"] = 2
        logger.info("KB migrée v1 → v2")

    if version < 3:
        # v2 → v3 : ajout champs fix_confidence, reproduced
        for bug in data.get("bugs", []):
            bug.setdefault("fix_confidence", 0.0)
            bug.setdefault("reproduced", True)
            bug.setdefault("tags", [])
        # Re-indexer les patterns
        data["patterns"] = []
        for i, bug in enumerate(data.get("bugs", [])):
            data["patterns"].append(
                {
                    "pattern_id": f"PTN-{i + 1:04d}",
                    "keywords": bug.get("keywords", []),
                    "category": bug.get("category", "unknown"),
                    "root_cause_pattern": bug.get("root_cause", "")[:200],
                    "fix_pattern": bug.get("solution", "")[:200],
                    "ref_bug": bug.get("bug_id", ""),
                }
            )
        data["version"] = 3
        logger.info("KB migrée v2 → v3")

    return data


def get_kb_path() -> Path:
    """Retourne le chemin de la base de connaissance."""
    return Path(os.getenv("NEXUS_KB_PATH", os.path.expanduser("~/nexus_kb.yaml")))


def _load_kb() -> dict[str, Any]:
    """Charge la base de connaissance YAML."""
    path = get_kb_path()
    if not path.exists():
        return {"bugs": [], "patterns": [], "version": KB_VERSION}
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
            data = migrate_kb(data)
            data.setdefault("bugs", [])
            data.setdefault("patterns", [])
            return data
    except Exception as exc:
        logger.warning("Erreur lecture KB: {}", exc)
        return {"bugs": [], "patterns": [], "version": KB_VERSION}


def _save_kb(data: dict[str, Any]) -> None:
    """Sauvegarde la base de connaissance YAML."""
    path = get_kb_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def kb_store(
    bug_id: str,
    category: str,
    summary: str,
    root_cause: str,
    solution: str,
    langage: str = "",
    keywords: list[str] | None = None,
    severity: str = "medium",
) -> dict[str, Any]:
    """Stocke un bug résolu dans la base de connaissance."""
    data = _load_kb()
    entry = {
        "bug_id": bug_id,
        "timestamp": datetime.utcnow().isoformat(),
        "category": category,
        "summary": summary,
        "root_cause": root_cause,
        "solution": solution,
        "langage": langage,
        "keywords": keywords or [],
        "severity": severity,
    }
    data["bugs"].append(entry)

    pattern = {
        "pattern_id": f"PTN-{len(data['patterns']) + 1:04d}",
        "keywords": keywords or [],
        "category": category,
        "root_cause_pattern": root_cause[:200],
        "fix_pattern": solution[:200],
        "ref_bug": bug_id,
    }
    data["patterns"].append(pattern)
    _save_kb(data)

    logger.debug("KB stored: {} (pattern {})", bug_id, pattern["pattern_id"])
    return {"status": "stored", "bug_id": bug_id, "pattern_id": pattern["pattern_id"]}


def kb_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Recherche dans la base de connaissance par mots-clés."""
    data = _load_kb()
    query_lower = query.lower()
    query_words = set(query_lower.split())

    results: list[dict[str, Any]] = []
    for bug in data.get("bugs", []):
        score = 0
        bug_keywords = {k.lower() for k in bug.get("keywords", [])}
        score += len(query_words & bug_keywords) * 2

        summary_lower = bug.get("summary", "").lower()
        for w in query_words:
            if w in summary_lower:
                score += 1

        cause_lower = bug.get("root_cause", "").lower()
        for w in query_words:
            if w in cause_lower:
                score += 1

        if score > 0:
            results.append({"bug": bug, "score": score})

    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "status": "success",
        "query": query,
        "results": [r["bug"] for r in results[:max_results]],
        "count": len(results[:max_results]),
    }


def kb_stats() -> dict[str, Any]:
    """Statistiques de la base de connaissance."""
    data = _load_kb()
    bugs = data.get("bugs", [])
    patterns = data.get("patterns", [])

    categories: dict[str, int] = {}
    for bug in bugs:
        cat = bug.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "status": "success",
        "total_bugs": len(bugs),
        "total_patterns": len(patterns),
        "categories": categories,
        "kb_path": str(get_kb_path()),
    }
