"""
orchestrateur_integration.py — Comment Orchestrateur appelle Nexus agentique
"""

from __future__ import annotations

import asyncio
import uuid

from loguru import logger

from nexus_agent import nexus_run


def sanitize_brief(text: str, max_len: int = 4000) -> str:
    """Sanitization LÉGÈRE — bornes + null byte, sans casser les bugs réels."""
    text = text[:max_len]
    return text.replace("\u0000", "")


async def orchestrateur_delegate_to_nexus(
    brief: str,
    priority: str = "P2",
    project: str = "",
    langage: str = "",
    fichier: str = "",
    erreur: str = "",
    stack: str = "",
) -> dict:
    """
    Orchestrateur construit le brief et délègue à Nexus.
    Nexus prend la main, raisonne librement, résout le bug.
    """
    # Construction du brief structuré
    mission_brief = f"""
PROJET   : {sanitize_brief(project or "Non précisé", 200)}
LANGAGE  : {sanitize_brief(langage or "À détecter", 100)}
FICHIER  : {sanitize_brief(fichier or "À identifier", 500)}
PRIORITÉ : {sanitize_brief(priority, 10)}

DESCRIPTION :
{sanitize_brief(brief)}

ERREUR EXACTE :
{sanitize_brief(erreur or "Voir description")}

STACK TRACE :
{sanitize_brief(stack or "Non fournie")}
    """.strip()

    logger.info("Délégation à Nexus — priorité {}", priority)

    # Appel agentique — Nexus fait le reste
    mission_id = f"DBG-{project[:4].upper() if project else 'AGNT'}-{uuid.uuid4().hex[:8]}"
    result = await nexus_run(brief=mission_brief, mission_id=mission_id)

    # Synthèse pour l'utilisateur
    status_emoji = {"fixed": "✅", "partial": "⚠️", "escalate": "🚨", "error": "❌"}.get(
        result.get("status", "error"), "❓"
    )

    f"""
{status_emoji} Mission Nexus terminée
{"─" * 40}
Statut    : {result.get("status", "inconnu")}
Cause     : {result.get("root_cause", "N/A")[:100]}
Fix       : {result.get("fix_summary", "N/A")[:100]}
Confiance : {result.get("confidence", 0) * 100:.0f}%
Outils    : {", ".join(result.get("tools_used", []))}
    """.strip()

    logger.info("Rapport de débogage reçu — statut: {}", result.get("status", "?"))
    return result


# ─── Exemple d'usage ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(
        orchestrateur_delegate_to_nexus(
            brief="L'API de profil utilisateur plante quand on n'est pas connecté",
            priority="P1",
            project="fisspro-app",
            langage="Python 3.11",
            fichier="src/auth/user.py",
            erreur="AttributeError: 'NoneType' object has no attribute 'id'",
            stack="File 'src/auth/user.py', line 42, in get_user_profile\n  return user.id",
        )
    )
