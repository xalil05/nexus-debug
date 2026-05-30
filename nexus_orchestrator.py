"""
nexus_orchestrator.py — Orchestrateur automatisé de la cellule Nexus
Remplace la pipeline fixe par une agentique
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

NEXUS_SKILLS_DIR = os.path.expanduser("~/.hermes/skills/agency")
REPORTS_DIR = Path(os.getenv("NEXUS_REPORTS_DIR", os.path.expanduser("~/nexus-reports")))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = 3


def run_hermes_skill(skill_name: str, input_text: str, timeout: int = 300) -> str:
    """Lance un skill Hermes en mode non-interactif et retourne sa sortie."""
    tmp_path = f"/tmp/nexus_query_{os.getpid()}.txt"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(input_text)

        cmd = [
            "hermes",
            "chat",
            "--skills",
            skill_name,
            "-q",
            f"@{tmp_path}",
            "-Q",
            "--yolo",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "NO_COLOR": "1"},
        )
        output = proc.stdout.strip() or proc.stderr.strip()
        logger.debug("Hermes skill '{}' returned {} chars", skill_name, len(output))
        return output
    except subprocess.TimeoutExpired:
        logger.warning("Hermes skill '{}' timed out ({}s)", skill_name, timeout)
        return f"TIMEOUT après {timeout}s"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def orchestrer_nexus(brief: str, mission_id: str = "") -> dict:
    """
    Orchestre la résolution d'un bug via Nexus agentique.
    1. Vérifie la KB pour pattern similaire
    2. Lance l'agent Nexus (ReAct) si pas en cache
    3. Sauvegarde le rapport
    """
    if not mission_id:
        mission_id = f"XAL-{datetime.now().strftime('%Y%m%d')}-{os.urandom(2).hex()}"

    logger.info("Orchestrateur: mission {} — vérification KB", mission_id)

    # Étape 1 : Vérification KB
    from nexus_kb import kb_search

    kb_result = kb_search(brief, max_results=3)

    if kb_result["count"] > 0:
        best = kb_result["results"][0]
        score = best.get("score", 0)
        if score >= 3:
            cached = best["bug"]
            logger.info("KB cache HIT (score={}) — mission {} résolue depuis cache", score, mission_id)
            return {
                "mission_id": mission_id,
                "status": "cached",
                "summary": f"Bug similaire déjà résolu: {cached.get('summary', '')}",
                "solution": cached.get("solution", ""),
                "kb_reference": cached.get("bug_id", ""),
                "root_cause": cached.get("root_cause", ""),
                "tools_used": ["kb_search"],
                "needs_human": False,
            }

    logger.info("KB cache MISS — lancement agent Nexus pour {}", mission_id)

    # Étape 2 : Lancement de l'agent Nexus
    from nexus_agent import nexus_run

    result = await nexus_run(brief, mission_id=mission_id)

    # Étape 3 : Stockage dans KB si fix réussi
    if result.get("status") in ("fixed", "done"):
        from nexus_kb import kb_store

        try:
            kb_store(
                bug_id=f"BUG-{mission_id[-8:]}",
                category=result.get("bug_category", "unknown"),
                summary=result.get("fix_summary", "") or result.get("summary", ""),
                root_cause=result.get("root_cause", ""),
                solution=result.get("fix_summary", "") or str(result.get("files_modified", [])),
                langage=result.get("langage", ""),
            )
            logger.info("KB mise à jour avec BUG-{}", mission_id[-8:])
        except Exception as exc:
            logger.warning("KB store failed: {}", exc)

    # Étape 4 : Sauvegarde du rapport
    report = {
        "mission_id": mission_id,
        "timestamp": datetime.utcnow().isoformat(),
        "brief": brief[:500],
        "result": result,
    }
    report_path = REPORTS_DIR / f"report_{mission_id}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("Mission {} terminée — rapport: {}", mission_id, report_path)
    return result


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    brief_test = sys.argv[1] if len(sys.argv) > 1 else "Bug test"
    result = asyncio.run(orchestrer_nexus(brief_test))
