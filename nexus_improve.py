"""
nexus_improve.py — Amélioration continue de Nexus-debug
Analyse les feedbacks et la KB pour proposer des améliorations des prompts/skills.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger

# Chemins
FEEDBACK_PATH = Path(os.getenv("NEXUS_FEEDBACK_PATH", os.path.expanduser("~/nexus_feedback.yaml")))
KB_PATH = Path(os.getenv("NEXUS_KB_PATH", os.path.expanduser("~/nexus_kb.yaml")))
SKILL_DIR = Path(os.path.expanduser("~/.hermes/skills/agency/nexus-debug"))
SKILL_FILE = SKILL_DIR / "SKILL.md"
REPORTS_DIR = Path(os.getenv("NEXUS_REPORTS_DIR", os.path.expanduser("~/nexus-reports")))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_feedback() -> list[dict]:
    if not FEEDBACK_PATH.exists():
        return []
    raw = yaml.safe_load(FEEDBACK_PATH.read_text()) or []
    return raw if isinstance(raw, list) else []


def load_kb() -> dict:
    if not KB_PATH.exists():
        return {"bugs": [], "patterns": [], "version": 2}
    try:
        return yaml.safe_load(KB_PATH.read_text()) or {"bugs": [], "patterns": [], "version": 2}
    except Exception:
        return {"bugs": [], "patterns": [], "version": 2}


def analyze_feedback() -> dict:
    """Analyse les feedbacks pour identifier les points faibles."""
    feedbacks = load_feedback()
    if not feedbacks:
        return {"status": "no_feedback", "message": "Aucun feedback à analyser"}

    # Stats
    total = len(feedbacks)
    ratings = [f.get("rating", 3) for f in feedbacks]
    avg_rating = sum(ratings) / max(1, total)
    low_ratings = [f for f in feedbacks if f.get("rating", 5) <= 2]
    common_issues = []

    for fb in low_ratings:
        comment = fb.get("comment", "").lower()
        if "lent" in comment or "long" in comment:
            common_issues.append("temps de réponse trop long")
        if "pas compris" in comment or "inutile" in comment:
            common_issues.append("analyse non pertinente")
        if "bug non résolu" in comment or "encore cassé" in comment:
            common_issues.append("correction inefficace")
        if "sécurité" in comment:
            common_issues.append("manque de vérification sécurité")

    # Suggestion
    suggestions = []
    if avg_rating < 3.0:
        suggestions.append("Revue urgente du prompt system d'Nexus")
    if len(common_issues) >= 2:
        suggestions.append(f"Issues fréquentes: {', '.join(set(common_issues[:3]))}")
    if total >= 5:
        suggestions.append(f"Base suffisante ({total} feedbacks) pour ajuster les poids des outils")

    return {
        "status": "analyzed",
        "total_feedback": total,
        "average_rating": round(avg_rating, 2),
        "low_ratings_count": len(low_ratings),
        "common_issues": list(set(common_issues)),
        "suggestions": suggestions,
    }


def analyze_kb() -> dict:
    """Analyse la base de connaissance pour les patterns récurrents."""
    kb = load_kb()
    bugs = kb.get("bugs", [])
    patterns = kb.get("patterns", [])

    # Top catégories
    categories: dict[str, int] = {}
    for bug in bugs:
        cat = bug.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

    top_categories = sorted(categories.items(), key=lambda x: -x[1])[:5]

    # Langages les plus fréquents
    langages: dict[str, int] = {}
    for bug in bugs:
        lang = bug.get("langage", "unknown")
        langages[lang] = langages.get(lang, 0) + 1

    top_langages = sorted(langages.items(), key=lambda x: -x[1])[:5]

    suggestions = []
    if len(bugs) >= 10:
        suggestions.append(f"Base KB solide ({len(bugs)} bugs). Enrichir les patterns de prévention.")
    if top_categories:
        suggestions.append(f"Top bugs: {', '.join(f'{c}({n})' for c, n in top_categories)}")

    return {
        "status": "analyzed",
        "total_bugs": len(bugs),
        "total_patterns": len(patterns),
        "top_categories": top_categories,
        "top_langages": top_langages,
    }


def generate_report() -> str:
    """Génère un rapport markdown complet."""
    fb = analyze_feedback()
    kb = analyze_kb()

    report = f"""# 📊 Nexus-debug — Rapport d'amélioration continue
*Généré le {datetime.now().strftime("%d/%m/%Y à %H:%M")}*

## Feedback utilisateur
- **Total feedbacks** : {fb.get("total_feedback", 0)}
- **Note moyenne** : {fb.get("average_rating", "N/A")}/5
- **Feedbacks négatifs** : {fb.get("low_ratings_count", 0)}
- **Issues fréquentes** : {", ".join(fb.get("common_issues", ["Aucune"])) or "Aucune"}

## Base de connaissance
- **Bugs résolus** : {kb.get("total_bugs", 0)}
- **Patterns identifiés** : {kb.get("total_patterns", 0)}
- **Top catégories** : {", ".join(f"{c}({n})" for c, n in kb.get("top_categories", [])) or "N/A"}
- **Top langages** : {", ".join(f"{lb}({n})" for lb, n in kb.get("top_langages", [])) or "N/A"}

## Suggestions d'amélioration
"""
    for s in fb.get("suggestions", []) + kb.get("suggestions", []):
        report += f"- {s}\n"

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"improve_report_{now}.md"
    report_path.write_text(report)
    logger.info("Rapport d'amélioration généré: {}", report_path)
    return str(report_path)


def init_git() -> None:
    """Versionne les prompts des agents."""
    if not SKILL_DIR.exists():
        return

    # Init git si pas fait
    git_dir = SKILL_DIR / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=str(SKILL_DIR), capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=str(SKILL_DIR), capture_output=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"Version initiale des prompts Nexus {datetime.now().strftime('%Y%m%d')}",
            ],
            cwd=str(SKILL_DIR),
            capture_output=True,
        )
        logger.info("Git init dans {}", SKILL_DIR)
    else:
        subprocess.run(["git", "add", "-A"], cwd=str(SKILL_DIR), capture_output=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"Mise à jour prompts {datetime.now().strftime('%Y%m%d_%H%M')}",
            ],
            cwd=str(SKILL_DIR),
            capture_output=True,
        )
        logger.info("Prompts versionnés dans {}", SKILL_DIR)


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    if "--report" in sys.argv:
        report_path = generate_report()
    elif "--init-git" in sys.argv:
        init_git()
    elif "--apply" in sys.argv:
        generate_report()
    else:
        generate_report()
