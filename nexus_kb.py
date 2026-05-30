"""
nexus_kb.py — Base de connaissance YAML pour Nexus-debug
Permet de stocker et rechercher les patterns de bugs résolus.
"""
import os
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional

def get_kb_path() -> Path:
    """Retourne le chemin de la base de connaissance (lit la variable d'env à chaque appel)."""
    return Path(os.getenv("NEXUS_KB_PATH", os.path.expanduser("~/nexus_kb.yaml")))


def _load_kb() -> dict:
    """Charge la base de connaissance YAML."""
    path = get_kb_path()
    if not path.exists():
        return {"bugs": [], "patterns": [], "version": 2}
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
            if "version" not in data:
                data["version"] = 2
            data.setdefault("bugs", [])
            data.setdefault("patterns", [])
            return data
    except Exception:
        return {"bugs": [], "patterns": [], "version": 2}


def _save_kb(data: dict) -> None:
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
    keywords: Optional[list[str]] = None,
    severity: str = "medium",
) -> dict:
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

    # Extraire et indexer le pattern
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

    return {"status": "stored", "bug_id": bug_id, "pattern_id": pattern["pattern_id"]}


def kb_search(query: str, max_results: int = 5) -> dict:
    """Recherche dans la base de connaissance par mots-clés."""
    data = _load_kb()
    query_lower = query.lower()
    query_words = set(query_lower.split())

    results = []
    for bug in data.get("bugs", []):
        score = 0
        # Score basé sur les mots-clés
        bug_keywords = set(k.lower() for k in bug.get("keywords", []))
        score += len(query_words & bug_keywords) * 2

        # Score basé sur le résumé
        summary_lower = bug.get("summary", "").lower()
        for w in query_words:
            if w in summary_lower:
                score += 1

        # Score basé sur la cause racine
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


def kb_stats() -> dict:
    """Statistiques de la base de connaissance."""
    data = _load_kb()
    bugs = data.get("bugs", [])
    patterns = data.get("patterns", [])

    categories = {}
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
