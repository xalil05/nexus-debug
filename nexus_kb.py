"""
nexus_kb.py — Base de connaissance YAML avec validation Pydantic
Stocke les bugs résolus pour éviter de les retraiter.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import aiofiles
import yaml
from loguru import logger
from pydantic import BaseModel, Field


# ── Modèle Pydantic strict pour les entrées KB ──────────────────────────────

class KBEntry(BaseModel):
    """Schéma validé pour une entrée dans la base de connaissance."""

    bug_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    category: str = Field(default="unknown", max_length=100)
    summary: str = Field(default="", max_length=500)
    root_cause: str = Field(default="", max_length=1000)
    solution: str = Field(default="", max_length=2000)
    langage: str = Field(default="", max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    severity: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")


# ── Chemins ──────────────────────────────────────────────────────────────────

DEFAULT_KB_PATH = "/data/nexus/kb/nexus_kb.yaml"


def get_kb_path() -> str:
    """Retourne le chemin vers le fichier KB, avec fallback sécurisé."""
    path = os.getenv("NEXUS_KB_PATH", DEFAULT_KB_PATH)
    # Empêcher les chemins dangereux
    resolved = os.path.realpath(path)
    if not resolved.startswith("/data/nexus") and not resolved.startswith("/tmp"):
        logger.warning("Chemin KB hors de /data/nexus, fallback sur défaut: {}", DEFAULT_KB_PATH)
        return DEFAULT_KB_PATH
    return resolved


def _load_kb() -> dict[str, Any]:
    """Charge la KB depuis le fichier YAML."""
    path = Path(get_kb_path())
    if not path.exists():
        return {"bugs": [], "patterns": [], "version": 2}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "bugs" in data:
            return data
        return {"bugs": [], "patterns": [], "version": 2}
    except Exception as exc:
        logger.warning("Erreur lecture KB: {}", exc)
        return {"bugs": [], "patterns": [], "version": 2}


def _save_kb(data: dict[str, Any]) -> None:
    """Sauvegarde la KB dans le fichier YAML avec limite de taille."""
    path = Path(get_kb_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    # Limite de taille : 500 KB max
    if len(yaml_text.encode("utf-8")) > 500_000:
        raise ValueError("KB trop volumineuse (> 500 KB)")
    path.write_text(yaml_text, encoding="utf-8")


# ── API publique ─────────────────────────────────────────────────────────────


def kb_store(
    bug_id: str,
    category: str = "unknown",
    summary: str = "",
    root_cause: str = "",
    solution: str = "",
    langage: str = "",
    keywords: list[str] | None = None,
    severity: str = "medium",
) -> dict[str, Any]:
    """Stocke un bug résolu dans la KB avec validation stricte."""
    try:
        entry = KBEntry(
            bug_id=bug_id,
            category=category,
            summary=summary,
            root_cause=root_cause,
            solution=solution,
            langage=langage,
            keywords=keywords or [],
            severity=severity,
        )
    except Exception as exc:
        logger.warning("KB store: validation échouée: {}", exc)
        return {"status": "error", "error": str(exc)[:200]}

    try:
        data = _load_kb()
        data.setdefault("bugs", []).append(entry.model_dump())
        _save_kb(data)
        logger.info("KB: bug {} stocké", bug_id)
        return {"status": "stored", "bug_id": bug_id}
    except Exception as exc:
        logger.warning("KB store: erreur écriture: {}", exc)
        return {"status": "error", "error": str(exc)[:200]}


def kb_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Recherche dans la KB par mots-clés."""
    if not query.strip():
        return {"status": "success", "results": [], "count": 0}

    data = _load_kb()
    bugs = data.get("bugs", [])
    query_words = set(query.lower().split())
    scored: list[tuple[int, dict]] = []

    for bug in bugs:
        text = " ".join(
            str(v) for v in [
                bug.get("summary", ""),
                bug.get("root_cause", ""),
                bug.get("solution", ""),
                " ".join(bug.get("keywords", [])),
            ]
        ).lower()
        score = sum(1 for w in query_words if w in text)
        if score > 0:
            scored.append((score, bug))

    scored.sort(key=lambda x: -x[0])
    results = [{"bug": b, "score": s} for s, b in scored[:max_results]]
    return {"status": "success", "results": results, "count": len(results)}


def kb_stats() -> dict[str, Any]:
    """Retourne les statistiques de la KB."""
    data = _load_kb()
    bugs = data.get("bugs", [])
    categories: dict[str, int] = {}
    severities: dict[str, int] = {}

    for bug in bugs:
        cat = bug.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1
        sev = bug.get("severity", "medium")
        severities[sev] = severities.get(sev, 0) + 1

    return {
        "total_bugs": len(bugs),
        "total_patterns": len(data.get("patterns", [])),
        "categories": categories,
        "severities": severities,
        "version": data.get("version", 2),
    }


# ── API asynchrone ────────────────────────────────────────────────────────────


async def kb_load_async() -> dict[str, Any]:
    """Version async de _load_kb avec aiofiles."""
    path = Path(get_kb_path())
    if not path.exists():
        return {"bugs": [], "patterns": [], "version": 2}
    try:
        async with aiofiles.open(str(path), encoding="utf-8") as f:
            raw = await f.read()
        data = yaml.safe_load(raw)
        if isinstance(data, dict) and "bugs" in data:
            return data
        return {"bugs": [], "patterns": [], "version": 2}
    except Exception as exc:
        logger.warning("Erreur lecture KB async: {}", exc)
        return {"bugs": [], "patterns": [], "version": 2}


async def kb_save_async(data: dict[str, Any]) -> None:
    """Version async de _save_kb avec aiofiles."""
    path = Path(get_kb_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    if len(yaml_text.encode("utf-8")) > 500_000:
        raise ValueError("KB trop volumineuse (> 500 KB)")
    async with aiofiles.open(str(path), "w", encoding="utf-8") as f:
        await f.write(yaml_text)


async def kb_store_async(
    bug_id: str,
    category: str = "unknown",
    summary: str = "",
    root_cause: str = "",
    solution: str = "",
    langage: str = "",
    keywords: list[str] | None = None,
    severity: str = "medium",
) -> dict[str, Any]:
    """Version async de kb_store."""
    try:
        entry = KBEntry(
            bug_id=bug_id, category=category, summary=summary,
            root_cause=root_cause, solution=solution, langage=langage,
            keywords=keywords or [], severity=severity,
        )
    except Exception as exc:
        logger.warning("KB store async: validation échouée: {}", exc)
        return {"status": "error", "error": str(exc)[:200]}
    try:
        data = await kb_load_async()
        data.setdefault("bugs", []).append(entry.model_dump())
        await kb_save_async(data)
        logger.info("KB async: bug {} stocké", bug_id)
        return {"status": "stored", "bug_id": bug_id}
    except Exception as exc:
        logger.warning("KB store async: erreur: {}", exc)
        return {"status": "error", "error": str(exc)[:200]}
